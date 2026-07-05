"""Tests for services/season_pack.py (Phase 6 of the Series/Season/Episode
hierarchy batch) — one season-pack release for a whole Temporada, ported
from legacy.py::build_plan()'s season_pack branch.

conftest.py provides isolated_db (autouse) pointing CONFIG_DIR to a tmp dir.
"""
from __future__ import annotations

from emuwarez_uploadrr.database import init_db, connect
from emuwarez_uploadrr.services.season_pack import (
    build_season_pack_plan,
    apply_season_pack,
    CONFIRMATION_TOKEN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db(isolated_db):
    return isolated_db / "emuwarez_uploadrr.db"


def _open(isolated_db):
    conn = connect(_db(isolated_db))
    init_db(conn)
    return conn


def _set_hardlink_base(conn, base_path):
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('hardlink_base', ?)",
        (str(base_path),),
    )
    conn.commit()


def _seed_series_season(conn, *, series_title="One Piece", year=1999):
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status, updated_at)
           VALUES ('series', ?, ?, 'Parcial', 'Sin petición', 'N/A', CURRENT_TIMESTAMP)""",
        (series_title, year),
    )
    series_id = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO library_items
           (item_type, title, year, local_status, request_status, nomenclature_status, parent_id, season_number, updated_at)
           VALUES ('season', ?, ?, 'Parcial', 'Sin petición', 'N/A', ?, 1, CURRENT_TIMESTAMP)""",
        (f"{series_title} - Temporada 1", year, series_id),
    )
    season_id = cur.lastrowid
    conn.commit()
    return series_id, season_id


def _seed_episode(conn, season_id, *, number, title, path=None, available=True, quality=None):
    status = "Disponible" if available else "Faltante"
    cur = conn.execute(
        """INSERT INTO library_items
           (item_type, title, year, local_status, request_status, nomenclature_status,
            parent_id, season_number, episode_number, path, quality, updated_at)
           VALUES ('episode', ?, 1999, ?, 'Sin petición', 'No adaptada', ?, 1, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (title, status, season_id, number, path, quality),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# build_season_pack_plan
# ---------------------------------------------------------------------------

def test_plan_not_found(isolated_db):
    conn = _open(isolated_db)
    plan = build_season_pack_plan(99999, conn=conn)
    assert plan["status"] == "blocked"
    assert "no encontrada" in plan["errors"][0].lower()
    conn.close()


def test_plan_blocked_without_hardlink_base(isolated_db, tmp_path):
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    src = tmp_path / "S01E01.mkv"
    src.write_bytes(b"video")
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path=str(src))
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "blocked"
    assert any("hardlink_base" in e for e in plan["errors"])
    conn.close()


def test_plan_blocked_no_available_episodes(isolated_db, tmp_path):
    conn = _open(isolated_db)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    _series_id, season_id = _seed_series_season(conn)
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", available=False)
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "blocked"
    assert any("ningún episodio disponible" in e for e in plan["errors"])
    conn.close()


def test_plan_warns_on_partial_season(isolated_db, tmp_path):
    conn = _open(isolated_db)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    _series_id, season_id = _seed_series_season(conn)
    src1 = tmp_path / "S01E01.mkv"
    src1.write_bytes(b"video")
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path=str(src1), quality="WEBDL-1080p")
    _seed_episode(conn, season_id, number=2, title="One Piece S01E02", available=False)

    plan = build_season_pack_plan(season_id, conn=conn)

    assert plan["status"] == "warning"
    assert any("incompleta" in w for w in plan["warnings"])
    assert len(plan["episodes"]) == 1
    conn.close()


def test_plan_full_season_all_episodes_present(isolated_db, tmp_path):
    conn = _open(isolated_db)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    _series_id, season_id = _seed_series_season(conn)
    for i in (1, 2):
        src = tmp_path / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    plan = build_season_pack_plan(season_id, conn=conn)

    assert plan["status"] == "valid"
    assert plan["warnings"] == []
    assert len(plan["episodes"]) == 2
    assert plan["season_pack_title"].startswith("One Piece S01")
    assert plan["hardlink_folder"].startswith(str(prepared))
    # Each episode gets its own individually-named destination inside the
    # SAME shared season folder — not the season pack title verbatim.
    folders = {ep["destination_path"].rsplit("/", 1)[0] for ep in plan["episodes"]}
    assert len(folders) == 1
    filenames = {ep["proposed_filename"] for ep in plan["episodes"]}
    assert len(filenames) == 2
    conn.close()


# ---------------------------------------------------------------------------
# apply_season_pack
# ---------------------------------------------------------------------------

def test_apply_dry_run_creates_no_files(isolated_db, tmp_path):
    conn = _open(isolated_db)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    _series_id, season_id = _seed_series_season(conn)
    src = tmp_path / "S01E01.mkv"
    src.write_bytes(b"video")
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path=str(src), quality="WEBDL-1080p")

    result = apply_season_pack(season_id, dry_run=True, conn=conn)

    assert result["dry_run"] is True
    assert result["status"] == "ready"
    assert len(result["episodes"]) == 1
    assert not list(prepared.rglob("*.mkv"))
    conn.close()


def test_apply_blocked_without_confirmation(isolated_db, tmp_path):
    conn = _open(isolated_db)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    _series_id, season_id = _seed_series_season(conn)
    src = tmp_path / "S01E01.mkv"
    src.write_bytes(b"video")
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path=str(src), quality="WEBDL-1080p")

    result = apply_season_pack(season_id, dry_run=False, apply=True, confirmation=None, conn=conn)

    assert result["status"] == "blocked"
    assert not list(prepared.rglob("*.mkv"))
    conn.close()


def test_apply_real_creates_hardlinks_for_each_episode(isolated_db, tmp_path):
    conn = _open(isolated_db)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    _series_id, season_id = _seed_series_season(conn)
    sources = []
    for i in (1, 2):
        src = tmp_path / f"S01E0{i}.mkv"
        src.write_bytes(f"video {i}".encode())
        sources.append(src)
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    result = apply_season_pack(season_id, dry_run=False, apply=True, confirmation=CONFIRMATION_TOKEN, conn=conn)

    assert result["status"] == "applied"
    assert len(result["episodes"]) == 2
    created_files = list(prepared.rglob("*.mkv"))
    assert len(created_files) == 2
    # All in the SAME shared season folder.
    assert len({f.parent for f in created_files}) == 1
    # Originals never modified.
    for src in sources:
        assert src.exists()
    conn.close()


def test_apply_partial_season_only_hardlinks_available_episodes(isolated_db, tmp_path):
    conn = _open(isolated_db)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    _series_id, season_id = _seed_series_season(conn)
    src = tmp_path / "S01E01.mkv"
    src.write_bytes(b"video")
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path=str(src), quality="WEBDL-1080p")
    _seed_episode(conn, season_id, number=2, title="One Piece S01E02", available=False)

    result = apply_season_pack(season_id, dry_run=False, apply=True, confirmation=CONFIRMATION_TOKEN, conn=conn)

    assert result["status"] == "applied"
    assert any("incompleta" in w for w in result["warnings"])
    assert len(result["episodes"]) == 1
    conn.close()


def test_confirmation_token_value():
    assert CONFIRMATION_TOKEN == "APLICAR_SEASON_PACK"


# ---------------------------------------------------------------------------
# upload_jobs wiring — one job for the whole season pack
# ---------------------------------------------------------------------------

def test_apply_real_creates_one_upload_job_referencing_the_season(isolated_db, tmp_path):
    import json as _json
    conn = _open(isolated_db)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    _series_id, season_id = _seed_series_season(conn)
    for i in (1, 2):
        src = tmp_path / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    result = apply_season_pack(season_id, dry_run=False, apply=True, confirmation=CONFIRMATION_TOKEN, conn=conn)

    assert result["upload_job_id"] is not None
    job = conn.execute("SELECT * FROM upload_jobs WHERE id = ?", (result["upload_job_id"],)).fetchone()
    assert job is not None
    # library_item_id points at the SEASON row itself — a normal scalar FK,
    # no bundling/junction table.
    assert job["library_item_id"] == season_id
    assert job["source_path"] == result["hardlink_folder"]

    cmd = _json.loads(job["uploadrr_command_json"])
    assert cmd["category"] == "tv"
    assert cmd["season"] == 1
    assert cmd["episode"] is None
    conn.close()


def test_apply_dry_run_creates_no_upload_job(isolated_db, tmp_path):
    conn = _open(isolated_db)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    _series_id, season_id = _seed_series_season(conn)
    src = tmp_path / "S01E01.mkv"
    src.write_bytes(b"video")
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path=str(src), quality="WEBDL-1080p")

    result = apply_season_pack(season_id, dry_run=True, conn=conn)

    assert "upload_job_id" not in result or result.get("upload_job_id") is None
    assert conn.execute("SELECT COUNT(*) FROM upload_jobs").fetchone()[0] == 0
    conn.close()
