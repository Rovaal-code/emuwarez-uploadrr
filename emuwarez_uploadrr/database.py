"""SQLite persistence shared by the CLI and the future web backend."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional

from .constants import CONFIG_DIR

DB_FILE = CONFIG_DIR / "emuwarez_uploadrr.db"

SCHEMA_VERSION = 5


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
        _migrate_requests(conn)
        _migrate_nomenclature(conn)
        _migrate_upload_jobs(conn)
        _migrate_filesystem_operations(conn)
        _migrate_library_items_phase6b(conn)
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
]
