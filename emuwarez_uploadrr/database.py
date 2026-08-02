"""SQLite persistence shared by the CLI and the future web backend."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional

from .constants import CONFIG_DIR

logger = logging.getLogger(__name__)

DB_FILE = CONFIG_DIR / "emuwarez_uploadrr.db"

SCHEMA_VERSION = 38

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
    # Concurrent requests each open their own connection (see require_auth,
    # every endpoint's _get_conn()). Without this, two connections racing to
    # write at the same moment (e.g. a table-rebuild migration) get an
    # immediate "database is locked"/"table already exists" error instead of
    # one simply waiting its turn.
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.create_collation("TITLE_SORT", _title_sort_collation)
    return conn


def _title_sort_key(s: Optional[str]) -> str:
    """Sort key for library titles: símbolos < números < letras, con los
    acentos plegados a su vocal base (Émesis ordena junto a las «E», no al
    final). NOCASE de SQLite solo ignora mayúsculas, no acentos, y deja los
    caracteres de código alto (á, ¡, ¿) fuera de sitio."""
    import unicodedata
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    out: list[str] = []
    for c in s:
        # Category prefix per character so the ordering symbol<number<letter
        # holds at every position, not just the first char.
        cat = "2" if c.isalpha() else "1" if c.isdigit() else "0"
        out.append(cat)
        out.append(c)
    return "".join(out)


def _title_sort_collation(a: str, b: str) -> int:
    ka, kb = _title_sort_key(a), _title_sort_key(b)
    return (ka > kb) - (ka < kb)


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


def _rebuild_instances_table(
    conn: sqlite3.Connection, type_check_values: str, unique_clause: str = "UNIQUE(type, name)"
) -> None:
    """Shared table-rebuild step for the widen/narrow/unique-name migrations
    below. Caller is responsible for the transaction (BEGIN/COMMIT/ROLLBACK)
    and the idempotency guard — this just issues the DDL/DML statements one
    at a time (never `executescript()`, which issues its own implicit commit
    and would break a caller-managed transaction)."""
    conn.execute(f"""
        CREATE TABLE instances_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ({type_check_values})),
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
            {unique_clause}
        )
    """)
    conn.execute("""
        INSERT INTO instances_new (
            id, type, name, url, api_key, enabled, is_4k, is_anime,
            last_test_status, last_test_at, created_at, updated_at
        )
        SELECT
            id, type, name, url, api_key, enabled, is_4k, is_anime,
            last_test_status, last_test_at, created_at, updated_at
        FROM instances
    """)
    conn.execute("DROP TABLE instances")
    conn.execute("ALTER TABLE instances_new RENAME TO instances")


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

    Concurrency: every request opens its own connection (require_auth, each
    endpoint's _get_conn()), and this runs on every one of them via
    init_db(). Without an explicit lock, two connections can both pass the
    guard check before either finishes rebuilding, and the second's
    `CREATE TABLE instances_new` fails with "table already exists" — caught
    nowhere, which for require_auth meant a live 401 on a perfectly valid
    token. BEGIN IMMEDIATE + the busy_timeout set in connect() serialize
    this: the second caller waits for the lock, then re-checks the guard
    (already migrated) and no-ops.
    """
    prior_isolation = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'instances'"
        ).fetchone()
        if not row or not row["sql"] or "'seerr'" in row["sql"]:
            conn.execute("COMMIT")
            return
        _rebuild_instances_table(conn, "'radarr','sonarr','seerr'")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.isolation_level = prior_isolation


def _migrate_instances_narrow_type_check(conn: sqlite3.Connection) -> None:
    """Narrow instances.type CHECK back to ('radarr','sonarr'), removing
    'seerr' (Seerr integration removed — it never had a working request
    sync, see removal notes for this phase).

    Deletes any existing 'seerr' rows first (their request-sync was never
    implemented, so there is no real data to preserve) and the now-orphaned
    scheduled task row, then rebuilds the table with the narrower CHECK —
    same table-rebuild pattern as `_migrate_instances_widen_type_check`,
    including the same BEGIN IMMEDIATE locking for the same concurrency
    reason (see that function's docstring). Idempotent: skipped if the
    constraint no longer contains 'seerr'.
    """
    prior_isolation = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'instances'"
        ).fetchone()
        if not row or not row["sql"] or "'seerr'" not in row["sql"]:
            conn.execute("COMMIT")
            return
        conn.execute("DELETE FROM instances WHERE type = 'seerr'")
        conn.execute("DELETE FROM scheduled_tasks WHERE task_key = 'seerr_requests_sync'")
        _rebuild_instances_table(conn, "'radarr','sonarr'")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.isolation_level = prior_isolation


def _migrate_instances_unique_name(conn: sqlite3.Connection) -> None:
    """Make instances.name globally unique (was UNIQUE(type, name) — two
    instances of different types could share a name, e.g. a Radarr and a
    Sonarr both named "Main"). Requested so the Biblioteca origin filter and
    Radarr/Sonarr deep links can identify an instance by name unambiguously.

    Same BEGIN IMMEDIATE + table-rebuild pattern as
    _migrate_instances_widen_type_check/_migrate_instances_narrow_type_check
    (SQLite can't ALTER a table-level UNIQUE constraint directly).

    Nothing before this migration stopped two different-typed instances
    from sharing a name, so real conflicts must be resolved before the
    rebuild, not just prevented going forward — `init_db()` must always
    converge, never fail startup over pre-existing data:
      1. Keep the lowest-id (earliest-created) row's name unchanged.
      2. Every other row sharing that name is renamed to "{name} ({type})".
      3. If that disambiguated name is itself already taken (pathological
         case — matches an already-decided name), append " #{id}" as a
         final, deterministic tie-breaker (id is unique by construction).
    Every rename is logged so an operator can see what happened.
    """
    prior_isolation = conn.isolation_level
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'instances'"
        ).fetchone()
        if not row or not row["sql"] or "UNIQUE(name)" in row["sql"]:
            conn.execute("COMMIT")
            return

        rows = conn.execute("SELECT id, type, name FROM instances ORDER BY id").fetchall()
        claimed: dict[str, int] = {}
        for r in rows:
            name = r["name"]
            if name not in claimed:
                claimed[name] = r["id"]
                continue
            new_name = f"{name} ({r['type']})"
            if new_name in claimed:
                new_name = f"{new_name} #{r['id']}"
            claimed[new_name] = r["id"]
            conn.execute("UPDATE instances SET name = ? WHERE id = ?", (new_name, r["id"]))
            logger.warning(
                "Migración de nombre único: renombrada instancia #%s (%s) de '%s' a '%s' "
                "por conflicto con otra instancia de distinto tipo.",
                r["id"], r["type"], name, new_name,
            )

        _rebuild_instances_table(conn, "'radarr','sonarr'", unique_clause="UNIQUE(name)")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.isolation_level = prior_isolation


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
        # Audio channels (e.g. "5.1") and HDR/DV range, from Radarr/Sonarr
        # mediaInfo — needed to build the eMuwarez audio/HDR segments.
        ("audio_channels", "TEXT"),
        ("dynamic_range", "TEXT"),
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


def _migrate_upload_jobs_queue(conn: sqlite3.Connection) -> None:
    """Add queued_until to upload_jobs — the queued (grace-period) job created
    the instant the user clicks "Subir a eMuwarez" carries this so the UI can
    show a countdown and a Cancel button before the server actually starts
    renaming/remuxing/uploading."""
    try:
        conn.execute("ALTER TABLE upload_jobs ADD COLUMN queued_until TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_upload_jobs_snapshots(conn: sqlite3.Connection) -> None:
    """Add nomenclature/remux snapshot columns to upload_jobs — persisted
    read-only copies of the field breakdown and track plan actually applied,
    so the job detail page can show them after the fact even though the
    live nomenclature/remux services never keep this data themselves."""
    for col, col_def in [
        ("nomenclature_snapshot_json", "TEXT"),
        ("remux_snapshot_json", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE upload_jobs ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_upload_jobs_manual_refs(conn: sqlite3.Connection) -> None:
    """Add nomenclature_proposal_id/remux_overrides_json to upload_jobs — for
    a manual upload, these pin the exact nomenclature proposal the user
    confirmed in the wizard (so a retry can reuse it instead of falling back
    to "whichever is latest") and persist the per-track remux overrides
    (previously only kept in the in-memory _PENDING_REMUX_OVERRIDES dict,
    lost on a process restart and unavailable to a retry's new job row).
    An automatic (staging-pipeline) job never sets nomenclature_proposal_id —
    its absence is what queue_retry_for_job() uses to tell manual from
    automatic jobs apart."""
    try:
        conn.execute("ALTER TABLE upload_jobs ADD COLUMN nomenclature_proposal_id INTEGER")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE upload_jobs ADD COLUMN remux_overrides_json TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_upload_jobs_checks_snapshot(conn: sqlite3.Connection) -> None:
    """Add checks_snapshot_json — the pre-upload checks (renameable/hardlink
    or season_pack, output dir, qBittorrent, image hosts, eMuwarez) result at
    the moment the job was queued. For a manual upload these are the exact
    results the wizard already computed and showed the user before they
    confirmed; run_upload_checks() itself never persists anything, so without
    this the job detail page would have nothing to show for this section."""
    try:
        conn.execute("ALTER TABLE upload_jobs ADD COLUMN checks_snapshot_json TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_upload_jobs_season_overrides(conn: sqlite3.Connection) -> None:
    """Add season_overrides_json — Source/Proveedor/Tag edited by hand for a
    season pack in the wizard's editable season fields, applied uniformly
    across every episode. Previously this choice only ever reached the preview
    snapshot: the real apply step (season_pack.apply_season_pack) recomputed
    from scratch with no override at all, silently discarding it."""
    try:
        conn.execute("ALTER TABLE upload_jobs ADD COLUMN season_overrides_json TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_requests(conn: sqlite3.Connection) -> None:
    """Add Phase 5B columns to request_items and request_matches."""
    for col, col_def in [
        ("reviewed_at", "TEXT"),
        ("last_sync_at", "TEXT"),
        # eMuwarez requests table shows a 👍 "votes" count (how many other users
        # want it) alongside points/comments.
        ("votes", "INTEGER"),
        # Series/documentary scope: whole series ('all'), one season ('season')
        # or a single episode ('episode'), with the season/episode numbers.
        ("req_scope", "TEXT"),
        ("req_season", "INTEGER"),
        ("req_episode", "INTEGER"),
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
        ("readiness_best_library_item_id", "INTEGER"),
        ("readiness_updated_at", "TEXT"),
    ]
    for col, col_def in new_cols:
        try:
            conn.execute(f"ALTER TABLE request_items ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_request_items_emu_catalog_check(conn: sqlite3.Connection) -> None:
    """Add columns to cache a direct eMuwarez catalog (torrents/filter) duplicate check.

    This is independent from request_matches (library vs request matching):
    it records whether eMuwarez's own torrent catalog already has content for
    this request's tmdb_id, queried directly via emu_search_existing().
    """
    new_cols = [
        ("emu_catalog_checked_at", "TEXT"),
        ("emu_catalog_result", "TEXT"),
    ]
    for col, col_def in new_cols:
        try:
            conn.execute(f"ALTER TABLE request_items ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_drop_priority_columns(conn: sqlite3.Connection) -> None:
    """Remove the numeric "priority" ranking system (score + high/medium/low
    bucket) from request_readiness/operational_queue_items/request_items —
    the user explicitly asked for no "priority" concept anywhere in
    requests/queue. The 'blocked' classification is KEPT, but it already
    lives on the independent `status` column (e.g. status='file_missing' or
    'import_error' both already imply blocked) — priority_bucket was always a
    redundant derived label on top of that, never the source of truth.

    Plain ALTER TABLE DROP COLUMN (SQLite >= 3.35, confirmed available here)
    is enough — unlike the instances.type migrations, these columns carry no
    CHECK/UNIQUE constraint, so no table-rebuild is needed. SQLite refuses to
    drop a column that still has an index on it, so idx_rr_bucket/idx_oq_bucket
    must be dropped first. Idempotent: DROP INDEX/DROP COLUMN both raise
    OperationalError if already gone, caught and ignored.
    """
    for index_name in ("idx_rr_bucket", "idx_oq_bucket"):
        try:
            conn.execute(f"DROP INDEX {index_name}")
        except sqlite3.OperationalError:
            pass
    for table, columns in (
        ("request_readiness", ("priority_score", "priority_bucket")),
        ("operational_queue_items", ("priority_score", "priority_bucket")),
        ("request_items", ("readiness_priority_score", "readiness_priority_bucket")),
    ):
        for col in columns:
            try:
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {col}")
            except sqlite3.OperationalError:
                pass


def _migrate_request_items_extra_ids(conn: sqlite3.Connection) -> None:
    """Add mal_id / tvdb_id to request_items (populated at sync from the eMuwarez
    request when present — mal_id mainly for anime requests)."""
    for col in ("mal_id", "tvdb_id"):
        try:
            conn.execute(f"ALTER TABLE request_items ADD COLUMN {col} TEXT")
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


def _migrate_library_items_phase11e(conn: sqlite3.Connection) -> None:
    """Add poster_url to library_items (Phase 11E — grid/poster view)."""
    try:
        conn.execute("ALTER TABLE library_items ADD COLUMN poster_url TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_library_items_title_slug(conn: sqlite3.Connection) -> None:
    """Add title_slug to library_items — Sonarr's own web UI deep-link
    convention is /series/{titleSlug} (Radarr's is /movie/{tmdbId}, which
    tmdb_id already covers). Sonarr's raw API response already includes
    titleSlug (saved whole into raw_json since day one), this just gives it
    a dedicated, queryable column like tmdb_id/imdb_id/tvdb_id already have."""
    try:
        conn.execute("ALTER TABLE library_items ADD COLUMN title_slug TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_library_items_media_info(conn: sqlite3.Connection) -> None:
    """Add video_codec/audio_codec/audio_languages/subtitle_languages to
    library_items — parsed from Radarr/Sonarr's own movieFile/episodeFile
    `mediaInfo` sub-object (Phase 6A of the nomenclature/MediaInfo batch),
    replacing the old crude guess of video_codec from a substring match
    against the quality profile NAME."""
    new_cols = [
        ("video_codec", "TEXT"),
        ("audio_codec", "TEXT"),
        ("audio_languages", "TEXT"),
        ("subtitle_languages", "TEXT"),
        # Nomenclature strict check (MediaInfo): the expected name and when it
        # was last checked, so the UI can show the diff. Status uses the
        # existing nomenclature_status column ('No comprobada' by default now).
        ("nomenclature_expected", "TEXT"),
        ("nomenclature_checked_at", "TEXT"),
    ]
    for col, col_type in new_cols:
        try:
            conn.execute(f"ALTER TABLE library_items ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    # Clear stale verdicts from the OLD tag-based heuristic. Nomenclature can
    # now only be judged by reading MediaInfo, so anything the new checker has
    # NOT actually run (nomenclature_checked_at IS NULL) must fall back to the
    # honest default: 'No comprobada' when a file is on disk, 'N/A' otherwise.
    # Idempotent — checked items (checked_at set) are never touched.
    try:
        conn.execute(
            "UPDATE library_items SET nomenclature_status = CASE "
            "  WHEN local_status IN ('Disponible','Subido','Subiendo') AND path IS NOT NULL "
            "  THEN 'No comprobada' ELSE 'N/A' END "
            "WHERE nomenclature_checked_at IS NULL "
            "  AND nomenclature_status IS NOT 'No comprobada' "
            "  AND nomenclature_status IS NOT 'N/A'"
        )
    except sqlite3.OperationalError:
        pass


def _migrate_library_items_hierarchy(conn: sqlite3.Connection) -> None:
    """Add parent_id/season_number/episode_number to library_items — lets
    episodes point at their season row and seasons at their series row
    (adjacency list, one column reused at both levels), and gives
    season/episode numbers real queryable columns instead of only being
    baked into the display title string. Purely additive."""
    new_cols = [
        ("parent_id", "INTEGER"),
        ("season_number", "INTEGER"),
        ("episode_number", "INTEGER"),
        # Título en inglés resuelto en la sincronización (esquema 37). Las
        # bibliotecas sincronizadas antes lo tienen vacío y el asistente sigue
        # preguntando a TMDb hasta la siguiente sincronización.
        ("english_title", "TEXT"),
    ]
    for col, col_type in new_cols:
        try:
            conn.execute(f"ALTER TABLE library_items ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_library_parent ON library_items(parent_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_library_tvdb ON library_items(tvdb_id)")


def _migrate_ui_recibe_aviso_de_version(conn: sqlite3.Connection) -> None:
    """Esquema 38: el aviso de versión nueva, activado en la campana.

    Un canal sin configurar recibe todo, así que para una instalación nueva no
    hace falta nada. Pero quien ya guardó su selección de eventos tiene una
    lista cerrada, y el evento nuevo se quedaría fuera: se le añade, porque en
    la campana va activado por defecto.

    A los bots NO se les toca: ahí este aviso es opt-in a propósito."""
    try:
        fila = conn.execute(
            "SELECT value FROM settings WHERE key = 'notify.ui.events'").fetchone()
    except sqlite3.OperationalError:
        return
    if not fila or not fila["value"]:
        return                      # sin configurar: ya lo recibe todo
    codigos = [c.strip() for c in fila["value"].split(",") if c.strip()]
    if "version_available" in codigos:
        return
    codigos.append("version_available")
    conn.execute("UPDATE settings SET value = ? WHERE key = 'notify.ui.events'",
                 (",".join(codigos),))


def _migrate_tmdb_title_cache(conn: sqlite3.Connection) -> None:
    """Cache of TMDb-resolved titles by (tmdb_id, media_type, language), so the
    Sonarr title localization only hits TMDb once per series instead of on every
    library sync. Purely additive."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tmdb_title_cache (
            tmdb_id TEXT NOT NULL,
            media_type TEXT NOT NULL,      -- 'tv' | 'movie'
            language TEXT NOT NULL,
            title TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tmdb_id, media_type, language)
        )
    """)


def _migrate_source_engine_cache(conn: sqlite3.Connection) -> None:
    """Cache for services/source_engine (the multi-tool source detector) —
    keyed by the file's own identity (path+size+mtime) plus the engine's own
    version, so a code/rule change invalidates old rows automatically.
    Purely additive."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS source_engine_cache (
            path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mtime INTEGER NOT NULL,
            engine_version TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (path, size_bytes, mtime, engine_version)
        )
    """)


def _migrate_library_items_track_remux(conn: sqlite3.Connection) -> None:
    """Track reorder/rename via mkvmerge (Phase 12A) — status of the last
    remux applied to this item's file, so the UI can show a badge without
    re-running mkvmerge -J on every page load. Purely additive."""
    new_cols = [
        ("track_remux_status", "TEXT"),        # 'aplicado' | 'error' | NULL
        ("track_remux_applied_at", "TEXT"),
        ("track_remux_error", "TEXT"),
    ]
    for col, col_type in new_cols:
        try:
            conn.execute(f"ALTER TABLE library_items ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass


def _migrate_library_items_mal_id(conn: sqlite3.Connection) -> None:
    """MAL (MyAnimeList) id, resolved from the Fribb/anime-lists table against
    tvdb_id/tmdb_id at upsert time (see services/anime_lists.py) — Radarr/
    Sonarr never provide this themselves. Purely additive."""
    try:
        conn.execute("ALTER TABLE library_items ADD COLUMN mal_id TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_library_items_tvmaze_id(conn: sqlite3.Connection) -> None:
    """TVmaze id, que Sonarr ya trae en su payload (`tvMazeId`) y no se estaba
    guardando. 50 de 52 series lo traen con valor.

    No se añade tvRageId, que Sonarr también manda: solo lo trae la mitad y
    sus fichas devuelven 404 (comprobado con dos ids reales), así que el
    enlace no llevaría a ninguna parte. Purely additive."""
    try:
        conn.execute("ALTER TABLE library_items ADD COLUMN tvmaze_id TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_library_items_backdrop_url(conn: sqlite3.Connection) -> None:
    """Add backdrop_url to library_items — the fanart/backdrop counterpart to
    poster_url (Phase 11E), same Radarr/Sonarr `images` array, just
    coverType=fanart instead of poster (see integrations/base.py::
    extract_backdrop_url). Used as the dedicated page's hero background."""
    try:
        conn.execute("ALTER TABLE library_items ADD COLUMN backdrop_url TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_library_items_missing_since(conn: sqlite3.Connection) -> None:
    """Add missing_since to library_items — the timestamp of the most recent
    transition INTO local_status='Faltante' (set by upsert_library_item,
    never bumped by a resync that leaves it Faltante). Recomendaciones'
    "Faltante" group used to sort by Radarr/Sonarr's own `added` date (when
    the item was added to Radarr/Sonarr), which can be much older than when
    it actually became a missing/recommendable candidate (e.g. added months
    ago as an unreleased pre-order, only just released) — an item added
    recently for an unrelated reason could then wrongly outrank a genuinely
    newer missing detection."""
    try:
        conn.execute("ALTER TABLE library_items ADD COLUMN missing_since TEXT")
    except sqlite3.OperationalError:
        pass

    # Backfill for content that was already Faltante before this column
    # existed: added_at (when we first synced/inserted this row) is an
    # imperfect but far better proxy than leaving it NULL, which would keep
    # falling back to Radarr/Sonarr's own "added" date — an unrelated event
    # (see get_dashboard_recommendations). From here on, upsert_library_item
    # keeps it accurate on every real transition.
    #
    # Deliberately NOT gated behind "column didn't already exist" — this ran
    # once already on a deploy that only had the ALTER TABLE above (no
    # backfill yet), so the column already existing here must NOT skip this
    # UPDATE, or anyone who deployed that version first would have their
    # Faltante rows stuck at missing_since=NULL forever. The WHERE clause
    # alone (only rows still NULL) already makes this safe to run on every
    # migration pass.
    conn.execute(
        "UPDATE library_items SET missing_since = added_at "
        "WHERE local_status = 'Faltante' AND missing_since IS NULL"
    )


def _migrate_anime_id_map(conn: sqlite3.Connection) -> None:
    """Local mirror of the Fribb/anime-lists table (tvdb_id/season -> mal_id,
    tmdb movie id -> mal_id) — see services/anime_lists.py. Downloaded/
    refreshed on demand, same "external catalog mirrored into a local table"
    shape as emu_catalog above. Purely additive."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS anime_id_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tvdb_id TEXT,
            season_number INTEGER,
            tmdb_movie_id TEXT,
            mal_id TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_anime_id_map_tvdb ON anime_id_map(tvdb_id, season_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_anime_id_map_tmdb_movie ON anime_id_map(tmdb_movie_id)")


def _migrate_emu_catalog(conn: sqlite3.Connection) -> None:
    """eMuwarez torrent catalog index (populated by the on-demand eMuwarez
    sync) + the per-library-item comparison result. Purely additive."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS emu_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            torrent_id TEXT,
            category TEXT,
            tmdb_id TEXT,
            tvdb_id TEXT,
            season_number INTEGER,
            resolution TEXT,
            source TEXT,
            codec TEXT,
            has_spanish INTEGER,          -- 1 yes, 0 no, NULL unknown
            size INTEGER,
            name TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emu_catalog_tmdb ON emu_catalog(tmdb_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emu_catalog_tvdb ON emu_catalog(tvdb_id, season_number)")
    # Per-item comparison result (movies + seasons).
    for col, col_def in [
        ("emu_in_catalog", "INTEGER"),   # 1 present, 0 not, NULL not computed
        ("emu_aportes", "TEXT"),          # JSON list of {dim,detail}
    ]:
        try:
            conn.execute(f"ALTER TABLE library_items ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def _migrate_request_items_is_example(conn: sqlite3.Connection) -> None:
    """Marks the demo requests generated from the user's own library while
    eMuwarez hasn't handed over the real requests endpoint.

    The flag exists FOR THE REMOVAL more than for the feature: sync_requests
    only upserts and never deletes rows the tracker doesn't send, so the day
    the real endpoint ships, any leftover examples would sit in the table
    alongside real requests with no way to tell them apart. The version that
    brings that endpoint deletes them from its own migration
    (DELETE FROM request_items WHERE is_example = 1) instead of trusting that
    somebody remembered to press Borrar first."""
    try:
        conn.execute("ALTER TABLE request_items ADD COLUMN is_example INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _migrate_qbit_port_into_url(conn: sqlite3.Connection) -> None:
    """El puerto de qBittorrent deja de tener campo propio y pasa a ir dentro
    de la URL.

    Tenerlo aparte solo servía para escribirlo dos veces y para que "el puerto
    de la URL no coincide con el puerto en el que escucha su WebUI" fuera un
    error de verdad, difícil de ver desde la interfaz.

    Aquí se dobla el valor ya guardado dentro de la URL, para que a quien lo
    tuviera configurado no se le caiga la conexión en silencio en cuanto el
    campo desaparezca. Se usa el MISMO build_base_url que usa la conexión
    real, así que la URL migrada es exactamente la que se estaba llamando
    antes, no una reconstrucción parecida.
    """
    row = conn.execute("SELECT value FROM settings WHERE key = 'qbit.port'").fetchone()
    port = ((row["value"] if row else None) or "").strip()
    if port:
        url_row = conn.execute("SELECT value FROM settings WHERE key = 'qbit.url'").fetchone()
        url = ((url_row["value"] if url_row else None) or "").strip()
        if url:
            from .integrations.qbittorrent import build_base_url
            conn.execute(
                "UPDATE settings SET value = ? WHERE key = 'qbit.url'",
                (build_base_url(url, port),),
            )
    # Fuera en cualquier caso: una sola fuente de verdad, o el día de mañana
    # alguien lee el puerto viejo y no cuadra con el de la URL.
    conn.execute("DELETE FROM settings WHERE key = 'qbit.port'")


def _migrate_library_items_spanish_audio(conn: sqlite3.Connection) -> None:
    """Per-item Castilian flags. `has_spanish_audio` is the Español column in
    Biblioteca; `has_spanish_subs` is the same question for subtitle tracks;
    `has_spanish_ok` is the one the upload rules actually gate on: Castilian
    present EITHER way, since dubbed content needs no subtitles at all (see
    services/season_pack.py::_spanish_errors).

    All three are rolled up for seasons/series (see
    services/library.py::recompute_spanish_flags), so none can be a plain
    expression over the *_languages columns — only movie/episode leaves carry
    those, and a season's verdict is "every episode I hold satisfies it", which
    is not the same as OR-ing the two separate rollups. Purely additive."""
    for col in ("has_spanish_audio", "has_spanish_subs", "has_spanish_ok"):
        try:
            conn.execute(f"ALTER TABLE library_items ADD COLUMN {col} INTEGER")
        except sqlite3.OperationalError:
            pass  # 1 yes, 0 no, NULL unknown/not computed


def _migrate_notifications_table(conn: sqlite3.Connection) -> None:
    """In-app notification feed backing the topbar bell. Each row is one event
    (request published, upload completed, request match found, …). read_at is
    NULL until the user opens/reads it. Purely additive."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            link TEXT,
            level TEXT NOT NULL DEFAULT 'info',
            entity_type TEXT,
            entity_id INTEGER,
            poster_url TEXT,
            content_title TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            read_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(read_at)")
    # Existing installs predate poster_url/content_title — CREATE TABLE IF NOT
    # EXISTS above is a no-op for them, so add the columns here too.
    for col in ("poster_url", "content_title"):
        try:
            conn.execute(f"ALTER TABLE notifications ADD COLUMN {col} TEXT")
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


def _migrate_nomenclature_year_series(conn: sqlite3.Connection) -> None:
    """Add year/series_title/season_number to nomenclature_proposals — the
    proposal dict always used the real year to build proposed_title/
    proposed_filename, but never stored it as its own column, so anything
    reading the saved proposal (the automated upload job's nomenclature
    snapshot table) saw a blank Año/Serie/Temporada even though the
    generated name itself had it right."""
    new_cols = [
        ("year",           "TEXT"),
        ("series_title",   "TEXT"),
        ("season_number",  "INTEGER"),
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
    allowed_roots is deliberately NOT seeded here — leaving the row absent
    lets get_allowed_roots() apply its own DEFAULT_ALLOWED_ROOTS ("/data")
    as the single source of truth for that default, rather than duplicating
    it here (see services/uploadrr_contract.py::get_allowed_roots).
    """
    defaults = [
        ("uploadrr.runtime_type", "uploadrr_emu", 0),
        ("uploadrr.python_path", "/usr/local/bin/python", 0),
        ("uploadrr.timeout", "7200", 0),
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


def _migrate_scheduled_tasks_table(conn: sqlite3.Connection) -> None:
    """Create the scheduled_tasks table (Phase 11D — automatic tasks).

    Bookkeeping only (interval, last/next run, last status/summary) — the
    actual run history/logs reuse the pre-existing task_runs table (see
    services/tasks.py), keyed by task_key == task_runs.name.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            interval_minutes INTEGER NOT NULL,
            min_interval_minutes INTEGER NOT NULL,
            manual_allowed INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_run_at TEXT,
            last_status TEXT,
            last_summary TEXT,
            next_run_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


def init_db(conn: Optional[sqlite3.Connection] = None) -> None:
    """Create tables and run the migration cascade — idempotent, but NOT
    cheap: ~35 migration functions, several of which rebuild whole tables.

    Called on every authenticated request (require_auth/get_current_user
    each open their own connection and call this before touching anything
    else), so once the schema is already current this MUST short-circuit
    before doing any writes. Without this check, concurrent requests (e.g.
    several fired at once when the upload wizard modal opens) each start
    their own migration pass at the same time — even idempotent migrations
    take a write lock while checking, and under real concurrency that has
    caused `database is locked`-type errors that require_auth silently
    turned into "invalid token", wiping the frontend's session on a request
    that had nothing to do with auth (see the comment in dependencies.py).
    """
    own = conn is None
    conn = conn or connect()
    try:
        try:
            row = conn.execute("SELECT value FROM app_state WHERE key = 'schema_version'").fetchone()
        except sqlite3.OperationalError:
            row = None  # app_state doesn't exist yet — fresh DB, run the full cascade below
        if row is not None and row["value"] == str(SCHEMA_VERSION):
            return
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
                english_title TEXT,
                instance_id INTEGER,
                instance_type TEXT,
                instance_name TEXT,
                external_id TEXT,
                tmdb_id TEXT,
                imdb_id TEXT,
                tvdb_id TEXT,
                title_slug TEXT,
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
        _migrate_scheduled_tasks_table(conn)
        _migrate_library_items_phase11e(conn)
        _migrate_library_items_title_slug(conn)
        _migrate_instances_narrow_type_check(conn)
        _migrate_request_items_emu_catalog_check(conn)
        _migrate_request_items_extra_ids(conn)
        _migrate_drop_priority_columns(conn)
        _migrate_instances_unique_name(conn)
        _migrate_library_items_media_info(conn)
        _migrate_library_items_hierarchy(conn)
        _migrate_notifications_table(conn)
        _migrate_emu_catalog(conn)
        _migrate_tmdb_title_cache(conn)
        _migrate_ui_recibe_aviso_de_version(conn)
        _migrate_library_items_track_remux(conn)
        _migrate_upload_jobs_queue(conn)
        _migrate_upload_jobs_snapshots(conn)
        _migrate_upload_jobs_manual_refs(conn)
        _migrate_upload_jobs_checks_snapshot(conn)
        _migrate_upload_jobs_season_overrides(conn)
        _migrate_nomenclature_year_series(conn)
        _migrate_source_engine_cache(conn)
        _migrate_library_items_mal_id(conn)
        _migrate_anime_id_map(conn)
        _migrate_library_items_backdrop_url(conn)
        _migrate_library_items_missing_since(conn)
        _migrate_library_items_spanish_audio(conn)
        _migrate_request_items_is_example(conn)
        _migrate_qbit_port_into_url(conn)
        _migrate_library_items_tvmaze_id(conn)
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
