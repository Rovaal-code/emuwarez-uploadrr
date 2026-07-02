"""SQLite persistence shared by the CLI and the future web backend."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional

from .constants import CONFIG_DIR

DB_FILE = CONFIG_DIR / "emuwarez_uploadrr.db"

SCHEMA_VERSION = 14

# Phase 10E: canonical settings namespace fix.
#
# The setup wizard / UI (web/services/setup_service.py) writes dotted keys
# (uploadrr.path, tmdb.api_key, emu.api_key). Older code paths (and several
# existing test fixtures) read/write the legacy underscore form
# (uploadrr_path, tmdb_api_key, emu_api_key). Both forms can coexist in the
# `settings` table; the dotted key always wins when both are present.
CANONICAL_SETTING_ALIASES: dict[str, str] = {
    "uploadrr.path": "uploadrr_path",
    "uploadrr.python_path": "uploadrr_python_path",
    "uploadrr.runtime_type": "uploadrr_runtime_type",
    "uploadrr.timeout": "uploadrr_timeout",
    "uploadrr.allowed_roots": "uploadrr_allowed_roots",
    "tmdb.api_key": "tmdb_api_key",
    "emu.api_key": "emu_api_key",
}


def db_path() -> Path:
    """Return the active database path, respecting CONFIG_DIR env var at call time."""
    env_config = os.environ.get("CONFIG_DIR")
    base = Path(env_config) if env_config else CONFIG_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / "emuwarez_uploadrr.db"


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _migrate_instances(conn: sqlite3.Connection) -> None:
    """Add columns to instances that were not present in schema v2."""
    new_cols = [
        ("is_4k", "INTEGER NOT NULL DEFAULT 0"),
        ("is_anime", "INTEGER NOT NULL DEFAULT 0"),
        ("last_test_status", "TEXT"),
        ("last_test_at", "TEXT"),
    ]
    for col, col_def in new_cols:
        try:
            conn.execute(f"ALTER TABLE instances ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass  # column already exists


def _migrate_instances_widen_type_check(conn: sqlite3.Connection) -> None:
    """Widen instances.type CHECK to include 'seerr' (Phase 11B).

    SQLite cannot ALTER a CHECK constraint directly — this is the first
    table-rebuild migration in the project: create a new table with the
    wider constraint, copy all rows over an explicit column list (never
    `SELECT *`, to stay correct regardless of physical column order after
    years of ALTER TABLE ADD COLUMN), drop the old table, rename. Idempotent:
    skipped if the constraint already includes 'seerr'. No FK/index cleanup
    needed — `instances` has no FKs pointing to it and its only index is the
    UNIQUE(type, name) constraint, recreated verbatim on the new table.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'instances'"
    ).fetchone()
    if not row or not row["sql"] or "'seerr'" in row["sql"]:
        return

    conn.executescript("""
        CREATE TABLE instances_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('radarr','sonarr','seerr')),
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            api_key TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            is_4k INTEGER NOT NULL DEFAULT 0,
            is_anime INTEGER NOT NULL DEFAULT 0,
            last_test_status TEXT,
            last_test_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(type, name)
        );
        INSERT INTO instances_new (
            id, type, name, url, api_key, enabled, is_4k, is_anime,
            last_test_status, last_test_at, created_at, updated_at
        )
        SELECT
            id, type, name, url, api_key, enabled, is_4k, is_anime,
            last_test_status, last_test_at, created_at, updated_at
        FROM instances;
        DROP TABLE instances;
        ALTER TABLE instances_new RENAME TO instances;
    """)


def _migrate_nomenclature(conn: sqlite3.Connection) -> None:
    """Create nomenclature_proposals table (Phase 6A) and add Phase 6B columns."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nomenclature_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_item_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            current_name TEXT,
            current_path TEXT,
            proposed_title TEXT,
            proposed_filename TEXT,
            proposed_folder TEXT,
            proposed_path TEXT,
            media_type TEXT,
            tmdb_id TEXT,
            imdb_id TEXT,
            resolution TEXT,
            source TEXT,
            video_codec TEXT,
            audio_summary TEXT,
            subtitle_summary TEXT,
            release_tag TEXT,
            warnings_json TEXT,
            errors_json TEXT,
            raw_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Phase 6B columns (idempotent)
    for col, col_def in [
        ("applied_path", "TEXT"),
        ("applied_at", "TEXT"),
        ("operation_id", "INTEGER"),
    ]:
        try:
            conn.execute(f"ALTER TABLE nomenclature_proposals ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_filesystem_operations(conn: sqlite3.Connection) -> None:
    """Create filesystem_operations table (Phase 6B)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS filesystem_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            library_item_id INTEGER,
            proposal_id INTEGER,
            upload_job_id INTEGER,
            source_path TEXT,
            destination_path TEXT,
            base_path TEXT,
            dry_run INTEGER NOT NULL DEFAULT 1,
            warnings_json TEXT,
            errors_json TEXT,
            result_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            applied_at TEXT
        )
    """)


def _migrate_library_items_phase6b(conn: sqlite3.Connection) -> None:
    """Add Phase 6B columns to library_items."""
    for col, col_def in [
        ("prepared_path", "TEXT"),
        ("nomenclature_applied_at", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE library_items ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_upload_jobs(conn: sqlite3.Connection) -> None:
    """Add Phase 6A columns to upload_jobs."""
    new_cols = [
        ("request_item_id", "INTEGER"),
        ("stage", "TEXT"),
        ("source_path", "TEXT"),
        ("prepared_path", "TEXT"),
        ("uploadrr_command_json", "TEXT"),
        ("preflight_json", "TEXT"),
        ("progress_json", "TEXT"),
        ("error_message", "TEXT"),
        ("started_at", "TEXT"),
        ("finished_at", "TEXT"),
    ]
    for col, col_def in new_cols:
        try:
            conn.execute(f"ALTER TABLE upload_jobs ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_upload_jobs_phase6c(conn: sqlite3.Connection) -> None:
    """Add Phase 6C columns to upload_jobs."""
    new_cols = [
        ("exit_code", "INTEGER"),
        ("process_id", "INTEGER"),
    ]
    for col, col_def in new_cols:
        try:
            conn.execute(f"ALTER TABLE upload_jobs ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_upload_job_logs(conn: sqlite3.Connection) -> None:
    """Create upload_job_logs table (Phase 6C) and add Phase 6D columns."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS upload_job_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_job_id INTEGER NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            stream TEXT,
            created_at TEXT NOT NULL,
            raw_json TEXT,
            FOREIGN KEY (upload_job_id) REFERENCES upload_jobs(id)
        )
    """)
    # Phase 6D columns (idempotent)
    for col, col_def in [
        ("sequence", "INTEGER"),
        ("is_secret_redacted", "INTEGER NOT NULL DEFAULT 1"),
    ]:
        try:
            conn.execute(f"ALTER TABLE upload_job_logs ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_upload_jobs_phase6d(conn: sqlite3.Connection) -> None:
    """Add Phase 6D columns to upload_jobs and create upload_artifacts table."""
    new_cols = [
        ("result_url", "TEXT"),
        ("result_torrent_id", "TEXT"),
        ("result_tracker", "TEXT"),
        ("result_category", "TEXT"),
        ("duration_seconds", "INTEGER"),
        ("retry_of_job_id", "INTEGER"),
        ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_log_at", "TEXT"),
        ("last_error_at", "TEXT"),
        ("last_success_at", "TEXT"),
        ("safe_command_json", "TEXT"),
    ]
    for col, col_def in new_cols:
        try:
            conn.execute(f"ALTER TABLE upload_jobs ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS upload_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_job_id INTEGER NOT NULL,
            artifact_type TEXT NOT NULL,
            name TEXT,
            path TEXT,
            url TEXT,
            value TEXT,
            created_at TEXT NOT NULL,
            raw_json TEXT,
            FOREIGN KEY (upload_job_id) REFERENCES upload_jobs(id)
        )
    """)


def _migrate_requests(conn: sqlite3.Connection) -> None:
    """Add Phase 5B columns to request_items and request_matches."""
    for col, col_def in [
        ("reviewed_at", "TEXT"),
        ("last_sync_at", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE request_items ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_request_items_phase8b(conn: sqlite3.Connection) -> None:
    """Add Phase 8B readiness columns to request_items."""
    new_cols = [
        ("readiness_status", "TEXT"),
        ("readiness_action", "TEXT"),
        ("readiness_priority_score", "INTEGER"),
        ("readiness_priority_bucket", "TEXT"),
        ("readiness_best_library_item_id", "INTEGER"),
        ("readiness_updated_at", "TEXT"),
    ]
    for col, col_def in new_cols:
        try:
            conn.execute(f"ALTER TABLE request_items ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_request_readiness_tables(conn: sqlite3.Connection) -> None:
    """Create Phase 8B request readiness and candidates tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS request_readiness (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_item_id INTEGER NOT NULL UNIQUE,
            best_library_item_id INTEGER,
            status TEXT NOT NULL,
            recommended_action TEXT,
            priority_score INTEGER NOT NULL DEFAULT 0,
            priority_bucket TEXT NOT NULL DEFAULT 'low',
            compatibility_score REAL,
            upload_readiness_score REAL,
            blockers_json TEXT,
            reasons_json TEXT,
            candidate_summary_json TEXT,
            last_evaluated_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rr_request_item ON request_readiness(request_item_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rr_best_lib ON request_readiness(best_library_item_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rr_status ON request_readiness(status)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rr_action ON request_readiness(recommended_action)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rr_bucket ON request_readiness(priority_bucket)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS request_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_item_id INTEGER NOT NULL,
            library_item_id INTEGER NOT NULL,
            candidate_rank INTEGER NOT NULL,
            match_status TEXT NOT NULL,
            match_score REAL,
            compatibility_status TEXT,
            compatibility_score REAL,
            readiness_status TEXT,
            readiness_score REAL,
            blockers_json TEXT,
            reasons_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rc_request ON request_candidates(request_item_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rc_library ON request_candidates(library_item_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rc_rank ON request_candidates(candidate_rank)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_rc_readiness ON request_candidates(readiness_status)
    """)


def _migrate_operational_queue_tables(conn: sqlite3.Connection) -> None:
    """Create Phase 8C operational queue tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS operational_queue_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            queue_key TEXT NOT NULL UNIQUE,
            item_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            request_item_id INTEGER,
            library_item_id INTEGER,
            upload_job_id INTEGER,
            title TEXT,
            subtitle TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            action TEXT NOT NULL DEFAULT 'none',
            priority_score INTEGER NOT NULL DEFAULT 0,
            priority_bucket TEXT NOT NULL DEFAULT 'low',
            blockers_json TEXT,
            reasons_json TEXT,
            context_json TEXT,
            target_url TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_oq_queue_key ON operational_queue_items(queue_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_oq_status ON operational_queue_items(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_oq_action ON operational_queue_items(action)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_oq_bucket ON operational_queue_items(priority_bucket)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_oq_request ON operational_queue_items(request_item_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_oq_library ON operational_queue_items(library_item_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_oq_upload ON operational_queue_items(upload_job_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_oq_updated ON operational_queue_items(updated_at)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS operational_queue_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_type TEXT NOT NULL,
            status TEXT NOT NULL,
            items_built INTEGER NOT NULL DEFAULT 0,
            items_open INTEGER NOT NULL DEFAULT 0,
            items_ready INTEGER NOT NULL DEFAULT 0,
            items_blocked INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            summary_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _migrate_operational_actions_tables(conn: sqlite3.Connection) -> None:
    """Create Phase 9A operational action events table and add action tracking columns."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS operational_action_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            queue_item_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            details_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_oae_queue_item ON operational_action_events(queue_item_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_oae_created ON operational_action_events(created_at)"
    )
    for col, col_type in [
        ("last_action_at", "TEXT"),
        ("last_action_status", "TEXT"),
        ("last_action_message", "TEXT"),
    ]:
        try:
            conn.execute(
                f"ALTER TABLE operational_queue_items ADD COLUMN {col} {col_type}"
            )
        except Exception:
            pass


def _migrate_library_items_phase8a(conn: sqlite3.Connection) -> None:
    """Add Phase 8A diagnostic/filesystem columns to library_items."""
    new_cols = [
        ("file_exists", "INTEGER"),
        ("file_is_video", "INTEGER"),
        ("file_size_on_disk", "INTEGER"),
        ("file_verified_at", "TEXT"),
        ("file_verification_error", "TEXT"),
        ("arr_queue_status", "TEXT"),
        ("arr_queue_title", "TEXT"),
        ("arr_queue_progress", "REAL"),
        ("arr_queue_timeleft", "TEXT"),
        ("arr_queue_error", "TEXT"),
        ("arr_queue_raw_json", "TEXT"),
        ("arr_history_status", "TEXT"),
        ("arr_history_event_type", "TEXT"),
        ("arr_history_error", "TEXT"),
        ("arr_history_source_title", "TEXT"),
        ("arr_history_raw_json", "TEXT"),
        ("diagnostic_status", "TEXT"),
        ("diagnostic_summary", "TEXT"),
        ("diagnostic_reasons_json", "TEXT"),
        ("recommended_action", "TEXT"),
        ("recommendation_reasons_json", "TEXT"),
        ("recommendation_updated_at", "TEXT"),
    ]
    for col, col_def in new_cols:
        try:
            conn.execute(f"ALTER TABLE library_items ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_nomenclature_phase10a(conn: sqlite3.Connection) -> None:
    """Add Phase 10A editable fields and MKV title columns to nomenclature_proposals."""
    new_cols = [
        ("fields_json",                   "TEXT"),
        ("source_final",                  "TEXT"),
        ("provider_final",                "TEXT"),
        ("provider_options_json",         "TEXT"),
        ("tmdb_available_providers_json", "TEXT"),
        ("internal_mkv_title",            "TEXT"),
        ("internal_title_status",         "TEXT"),
        ("internal_title_applied_at",     "TEXT"),
        ("internal_title_error",          "TEXT"),
    ]
    for col, col_def in new_cols:
        try:
            conn.execute(f"ALTER TABLE nomenclature_proposals ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_settings_phase10a(conn: sqlite3.Connection) -> None:
    """Insert default Phase 10A settings if not already present."""
    defaults = [
        ("default_release_tag",      "EMUWAREZ",                              0),
        ("provider_priority_order",  '["AMZN","NF","DSNP","MAX","ATVP"]',     0),
        ("tmdb_watch_region",        "ES",                                     0),
    ]
    for key, value, is_secret in defaults:
        conn.execute(
            """INSERT OR IGNORE INTO settings (key, value, is_secret)
               VALUES (?, ?, ?)""",
            (key, value, is_secret),
        )


def _migrate_settings_phase10e(conn: sqlite3.Connection) -> None:
    """Insert default Phase 10E Uploadrr-EMU runtime settings if not already present.

    Defaults are conservative and require operator review: python_path
    assumes the Docker image layout (/usr/local/bin/python); host/manual
    deployments must override it with the path to Uploadrr-EMU's own venv.
    allowed_roots starts empty, which means "fall back to hardlink_base"
    (see services/uploadrr_contract.py::get_allowed_roots).
    """
    defaults = [
        ("uploadrr.runtime_type", "uploadrr_emu", 0),
        ("uploadrr.python_path", "/usr/local/bin/python", 0),
        ("uploadrr.timeout", "7200", 0),
        ("uploadrr.allowed_roots", "[]", 0),
    ]
    for key, value, is_secret in defaults:
        conn.execute(
            """INSERT OR IGNORE INTO settings (key, value, is_secret)
               VALUES (?, ?, ?)""",
            (key, value, is_secret),
        )


def _migrate_diagnostic_tables(conn: sqlite3.Connection) -> None:
    """Create Phase 8A diagnostic run and item diagnostic tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS library_diagnostic_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_type TEXT NOT NULL,
            status TEXT NOT NULL,
            items_checked INTEGER NOT NULL DEFAULT 0,
            items_updated INTEGER NOT NULL DEFAULT 0,
            warnings_count INTEGER NOT NULL DEFAULT 0,
            errors_count INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            summary_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS library_item_diagnostics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_item_id INTEGER NOT NULL,
            run_id INTEGER,
            severity TEXT NOT NULL,
            code TEXT NOT NULL,
            message TEXT NOT NULL,
            details_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


def init_db(conn: Optional[sqlite3.Connection] = None) -> None:
    own = conn is None
    conn = conn or connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK(type IN ('radarr','sonarr')),
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                api_key TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                is_4k INTEGER NOT NULL DEFAULT 0,
                is_anime INTEGER NOT NULL DEFAULT 0,
                last_test_status TEXT,
                last_test_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(type, name)
            );

            CREATE TABLE IF NOT EXISTS library_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL,
                title TEXT NOT NULL,
                year INTEGER,
                original_title TEXT,
                instance_id INTEGER,
                instance_type TEXT,
                instance_name TEXT,
                external_id TEXT,
                tmdb_id TEXT,
                imdb_id TEXT,
                tvdb_id TEXT,
                path TEXT,
                quality TEXT,
                resolution TEXT,
                source TEXT,
                size_bytes INTEGER,
                local_status TEXT NOT NULL,
                request_status TEXT NOT NULL DEFAULT 'Sin petición',
                nomenclature_status TEXT NOT NULL DEFAULT 'N/A',
                request_id INTEGER,
                added_at TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                raw_json TEXT,
                UNIQUE(instance_id, item_type, external_id)
            );

            CREATE INDEX IF NOT EXISTS idx_library_status ON library_items(local_status);
            CREATE INDEX IF NOT EXISTS idx_library_request_status ON library_items(request_status);
            CREATE INDEX IF NOT EXISTS idx_library_nomenclature ON library_items(nomenclature_status);
            CREATE INDEX IF NOT EXISTS idx_library_tmdb ON library_items(tmdb_id);
            CREATE INDEX IF NOT EXISTS idx_library_imdb ON library_items(imdb_id);

            CREATE TABLE IF NOT EXISTS request_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                emu_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                category TEXT,
                requested_source TEXT,
                requested_resolution TEXT,
                emu_status TEXT,
                points INTEGER,
                comments INTEGER,
                created_at TEXT,
                tmdb_id TEXT,
                imdb_id TEXT,
                url TEXT,
                author TEXT,
                author_visible INTEGER NOT NULL DEFAULT 0,
                raw_json TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_requests_tmdb ON request_items(tmdb_id);
            CREATE INDEX IF NOT EXISTS idx_requests_imdb ON request_items(imdb_id);
            CREATE INDEX IF NOT EXISTS idx_requests_title ON request_items(title);

            CREATE TABLE IF NOT EXISTS request_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                library_item_id INTEGER NOT NULL REFERENCES library_items(id) ON DELETE CASCADE,
                request_item_id INTEGER NOT NULL REFERENCES request_items(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0,
                resolution_match INTEGER,
                source_match INTEGER,
                type_match INTEGER,
                reasons TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(library_item_id, request_item_id)
            );

            CREATE TABLE IF NOT EXISTS task_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                summary TEXT,
                details TEXT
            );

            CREATE TABLE IF NOT EXISTS upload_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                library_item_id INTEGER REFERENCES library_items(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                dupe_status TEXT NOT NULL DEFAULT 'No comprobado',
                dupe_message TEXT,
                uploadrr_description TEXT,
                trailer_url TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- v3: web auth and settings tables
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS auth_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT,
                revoked_at TEXT,
                user_agent TEXT,
                ip_address TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_token ON auth_sessions(token_hash);
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON auth_sessions(user_id);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                is_secret INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        _migrate_instances(conn)
        _migrate_instances_widen_type_check(conn)
        _migrate_requests(conn)
        _migrate_nomenclature(conn)
        _migrate_upload_jobs(conn)
        _migrate_upload_jobs_phase6c(conn)
        _migrate_upload_job_logs(conn)
        _migrate_filesystem_operations(conn)
        _migrate_library_items_phase6b(conn)
        _migrate_upload_jobs_phase6d(conn)
        _migrate_library_items_phase8a(conn)
        _migrate_diagnostic_tables(conn)
        _migrate_request_items_phase8b(conn)
        _migrate_request_readiness_tables(conn)
        _migrate_operational_queue_tables(conn)
        _migrate_operational_actions_tables(conn)
        _migrate_nomenclature_phase10a(conn)
        _migrate_settings_phase10a(conn)
        _migrate_settings_phase10e(conn)
        set_state(conn, "schema_version", str(SCHEMA_VERSION))
        conn.commit()
    finally:
        if own:
            conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def get_state(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def get_setting_canonical(
    conn: sqlite3.Connection, dotted_key: str, default: Optional[str] = None
) -> Optional[str]:
    """Read a `settings` value by its canonical dotted key.

    Falls back to the legacy underscore alias (see CANONICAL_SETTING_ALIASES)
    when the dotted key is unset or empty. The dotted key always wins when
    both are present, since setup/UI only ever write the dotted form.
    """
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (dotted_key,)).fetchone()
        if row and row["value"] not in (None, ""):
            return row["value"]
        legacy_key = CANONICAL_SETTING_ALIASES.get(dotted_key)
        if legacy_key:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (legacy_key,)).fetchone()
            if row and row["value"] not in (None, ""):
                return row["value"]
    except sqlite3.OperationalError:
        pass
    return default


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_state(key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
        """,
        (key, value),
    )


def get_json_state(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    value = get_state(conn, key)
    if value is None:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def set_json_state(conn: sqlite3.Connection, key: str, value: Any) -> None:
    set_state(conn, key, json.dumps(value, ensure_ascii=False, sort_keys=True))


__all__ = [
    "DB_FILE", "SCHEMA_VERSION", "db_path", "connect", "init_db",
    "row_to_dict", "rows_to_dicts", "get_state", "set_state",
    "get_json_state", "set_json_state",
    "CANONICAL_SETTING_ALIASES", "get_setting_canonical",
]
