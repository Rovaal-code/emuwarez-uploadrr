"""Demo seed service for Phase 9B controlled E2E testing.

SAFETY CONTRACT:
- Requires explicit confirm_token to prevent accidental execution on real data.
- Only writes to the SQLite DB (via conn) and to paths explicitly passed as
  media_root / prepared_root parameters.
- Never touches Uploadrr/, real ARR APIs, eMuwarez APIs, or user media.
- All demo records are identifiable (emu_id='demo-emu-001', name='Radarr Demo').
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEMO_CONFIRM_TOKEN = "DEMO_SEED"
DEMO_RESET_TOKEN = "DEMO_RESET"

DEMO_TITLE = "Demo Movie"
DEMO_YEAR = 2024
DEMO_TMDB_ID = "tt0000001"
DEMO_IMDB_ID = "tt0000001"
DEMO_RESOLUTION = "1080p"
DEMO_SOURCE = "webdl"
DEMO_QUALITY = "WEBDL-1080p"
DEMO_FILENAME = f"{DEMO_TITLE} ({DEMO_YEAR}) WEBDL-1080p.mkv"
DEMO_FOLDER = f"{DEMO_TITLE} ({DEMO_YEAR})"
DEMO_EMU_ID = "demo-emu-001"
DEMO_INSTANCE_NAME = "Radarr Demo"


def seed_demo_data(
    conn: sqlite3.Connection,
    media_root: str,
    prepared_root: str,
    confirm_token: str,
) -> dict:
    """Seed demo data into the database and create a fake media file.

    Raises ValueError if confirm_token != 'DEMO_SEED'.
    Only writes to CONFIG_DIR DB and to media_root / prepared_root.
    """
    if confirm_token != DEMO_CONFIRM_TOKEN:
        raise ValueError(
            f"Token de confirmación incorrecto. Debes pasar --confirm {DEMO_CONFIRM_TOKEN}"
        )

    # Create fake media file (text file with .mkv extension — verifiers check existence/extension)
    media_path = Path(media_root) / "movies" / DEMO_FOLDER / DEMO_FILENAME
    media_path.parent.mkdir(parents=True, exist_ok=True)
    if not media_path.exists():
        media_path.write_text("FAKE MKV DEMO — eMuwarez Uploadrr E2E test fixture\n")

    Path(prepared_root).mkdir(parents=True, exist_ok=True)

    # Insert fake disabled ARR instance (enabled=0)
    conn.execute(
        """
        INSERT OR IGNORE INTO instances
            (type, name, url, api_key, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        ("radarr", DEMO_INSTANCE_NAME, "http://fake-radarr.local", "demo_key_fake", 0),
    )

    instance_row = conn.execute(
        "SELECT id FROM instances WHERE name = ? AND type = 'radarr'",
        (DEMO_INSTANCE_NAME,),
    ).fetchone()
    instance_id = instance_row["id"] if instance_row else None

    # Insert library item — check first because NULL external_id doesn't trigger UNIQUE constraint
    existing_lib = conn.execute(
        "SELECT id FROM library_items WHERE title = ? AND year = ? AND item_type = 'movie'",
        (DEMO_TITLE, DEMO_YEAR),
    ).fetchone()
    if not existing_lib:
        conn.execute(
            """
            INSERT INTO library_items
                (item_type, title, year, instance_id, instance_type, instance_name,
                 tmdb_id, imdb_id, path, quality, resolution, source,
                 local_status, request_status, nomenclature_status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                "movie", DEMO_TITLE, DEMO_YEAR,
                instance_id, "radarr", DEMO_INSTANCE_NAME,
                DEMO_TMDB_ID, DEMO_IMDB_ID,
                str(media_path),
                DEMO_QUALITY, DEMO_RESOLUTION, DEMO_SOURCE,
                "Disponible", "Compatible", "No adaptada",
            ),
        )

    lib_row = existing_lib or conn.execute(
        "SELECT id FROM library_items WHERE title = ? AND year = ? AND item_type = 'movie'",
        (DEMO_TITLE, DEMO_YEAR),
    ).fetchone()
    library_item_id = lib_row["id"] if lib_row else None

    # Insert request item
    conn.execute(
        """
        INSERT OR IGNORE INTO request_items
            (emu_id, title, category, requested_source, requested_resolution,
             emu_status, points, comments, tmdb_id, imdb_id, url, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            DEMO_EMU_ID, DEMO_TITLE, "peliculas",
            DEMO_SOURCE, DEMO_RESOLUTION,
            "approved", 10, 2,
            DEMO_TMDB_ID, DEMO_IMDB_ID,
            "https://emuwarez.example/requests/demo-001",
        ),
    )

    req_row = conn.execute(
        "SELECT id FROM request_items WHERE emu_id = ?", (DEMO_EMU_ID,)
    ).fetchone()
    request_item_id = req_row["id"] if req_row else None

    # Insert request match linking library item and request item
    if library_item_id and request_item_id:
        conn.execute(
            """
            INSERT OR IGNORE INTO request_matches
                (library_item_id, request_item_id, status, confidence,
                 resolution_match, source_match, type_match, reasons, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                library_item_id, request_item_id,
                "Compatible", 90.0,
                1, 1, 1,
                "ID TMDb coincide\nResolución compatible\nFuente compatible",
            ),
        )

    conn.commit()

    return {
        "ok": True,
        "library_item_id": library_item_id,
        "request_item_id": request_item_id,
        "media_file": str(media_path),
        "prepared_root": str(prepared_root),
    }


def reset_demo_data(conn: sqlite3.Connection, confirm_token: str) -> dict:
    """Remove demo seed data from the database.

    Raises ValueError if confirm_token != 'DEMO_RESET'.
    Does not remove files from disk — only clears DB records.
    """
    if confirm_token != DEMO_RESET_TOKEN:
        raise ValueError(
            f"Token de confirmación incorrecto. Debes pasar --confirm {DEMO_RESET_TOKEN}"
        )

    conn.execute("DELETE FROM request_items WHERE emu_id = ?", (DEMO_EMU_ID,))
    conn.execute(
        "DELETE FROM library_items WHERE title = ? AND year = ? AND item_type = 'movie'",
        (DEMO_TITLE, DEMO_YEAR),
    )
    conn.execute(
        "DELETE FROM instances WHERE name = ? AND type = 'radarr'",
        (DEMO_INSTANCE_NAME,),
    )
    conn.commit()

    return {"ok": True, "reset": True}
