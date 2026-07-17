"""Tests for services/season_pack.py — one season-pack release for a whole
Temporada, ported from legacy.py::build_plan()'s season_pack branch, now
extended with: live progress, blocking (not warning) on an incomplete
season, cross-episode consistency validation, a rename-in-place fallback
when hardlinks are disabled but every episode already shares one folder,
and the per-episode read views (names/mediainfo/remux) backing the wizard.

conftest.py provides isolated_db (autouse) pointing CONFIG_DIR to a tmp dir.
"""
from __future__ import annotations

from emuwarez_uploadrr.database import init_db, connect
from emuwarez_uploadrr.services.season_pack import (
    build_season_pack_plan,
    apply_season_hardlinks,
    get_season_plan_progress,
    get_season_episode_names,
    get_season_episode_mediainfo,
    get_season_episode_remux_previews,
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


def _set_use_hardlinks(conn, enabled: bool):
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('nomenclature.use_hardlinks', ?)",
        ("true" if enabled else "false",),
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


def _seed_episode(conn, season_id, *, number, title, path=None, available=True, quality=None,
                   video_codec=None, audio_codec=None, audio_languages=None, subtitle_languages=None):
    status = "Disponible" if available else "Faltante"
    cur = conn.execute(
        """INSERT INTO library_items
           (item_type, title, year, local_status, request_status, nomenclature_status,
            parent_id, season_number, episode_number, path, quality,
            video_codec, audio_codec, audio_languages, subtitle_languages, updated_at)
           VALUES ('episode', ?, 1999, ?, 'Sin petición', 'No adaptada', ?, 1, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (title, status, season_id, number, path, quality,
         video_codec, audio_codec, audio_languages, subtitle_languages),
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


def test_plan_blocks_on_partial_season(isolated_db, tmp_path):
    # An incomplete season is a hard block now, not a warning — silently
    # uploading a partial season as if it were the whole thing is wrong.
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

    assert plan["status"] == "blocked"
    assert any("incompleta" in e for e in plan["errors"])
    conn.close()


def test_plan_blocked_without_hardlink_base(isolated_db, tmp_path):
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    src = tmp_path / "S01E01.mkv"
    src.write_bytes(b"video")
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path=str(src), quality="WEBDL-1080p")
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "blocked"
    assert any("hardlink_base" in e for e in plan["errors"])
    assert plan.get("mode") is None
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
    assert plan["mode"] == "hardlink"
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


def test_plan_blocks_on_codec_mismatch(isolated_db, tmp_path):
    conn = _open(isolated_db)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    _series_id, season_id = _seed_series_season(conn)
    src1 = tmp_path / "S01E01.mkv"
    src1.write_bytes(b"video")
    src2 = tmp_path / "S01E02.mkv"
    src2.write_bytes(b"video")
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path=str(src1),
                  quality="WEBDL-1080p", video_codec="AVC", audio_codec="DTS")
    _seed_episode(conn, season_id, number=2, title="One Piece S01E02", path=str(src2),
                  quality="WEBDL-1080p", video_codec="AVC", audio_codec="AC3")

    plan = build_season_pack_plan(season_id, conn=conn)

    assert plan["status"] == "blocked"
    assert any("capítulo 2" in e and "códec de audio" in e for e in plan["errors"])
    conn.close()


def test_plan_rename_mode_when_hardlinks_off_and_shared_folder(isolated_db, tmp_path):
    # Hardlinks disabled but every available episode already lives in the
    # same folder (the common Sonarr/Radarr convention) — the pack still
    # works, renaming each episode in place instead of hardlinking.
    conn = _open(isolated_db)
    _set_use_hardlinks(conn, False)
    _series_id, season_id = _seed_series_season(conn)
    season_dir = tmp_path / "Season 1"
    season_dir.mkdir()
    for i in (1, 2):
        src = season_dir / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    plan = build_season_pack_plan(season_id, conn=conn)

    assert plan["status"] == "valid"
    assert plan["mode"] == "rename"
    assert plan["hardlink_folder"] == str(season_dir)
    assert plan["hardlink_base"] is None
    conn.close()


def test_plan_blocked_when_hardlinks_off_and_episodes_scattered(isolated_db, tmp_path):
    conn = _open(isolated_db)
    _set_use_hardlinks(conn, False)
    _series_id, season_id = _seed_series_season(conn)
    dir1 = tmp_path / "dir1"; dir1.mkdir()
    dir2 = tmp_path / "dir2"; dir2.mkdir()
    src1 = dir1 / "S01E01.mkv"; src1.write_bytes(b"video")
    src2 = dir2 / "S01E02.mkv"; src2.write_bytes(b"video")
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path=str(src1), quality="WEBDL-1080p")
    _seed_episode(conn, season_id, number=2, title="One Piece S01E02", path=str(src2), quality="WEBDL-1080p")

    plan = build_season_pack_plan(season_id, conn=conn)

    assert plan["status"] == "blocked"
    assert any("no están todos en la misma carpeta" in e for e in plan["errors"])
    conn.close()


def test_plan_progress_reaches_total(isolated_db, tmp_path):
    conn = _open(isolated_db)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    _series_id, season_id = _seed_series_season(conn)
    for i in (1, 2, 3):
        src = tmp_path / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    build_season_pack_plan(season_id, conn=conn)

    progress = get_season_plan_progress(season_id)
    assert progress["done"] == 3
    assert progress["total"] == 3
    conn.close()


# ---------------------------------------------------------------------------
# apply_season_hardlinks
# ---------------------------------------------------------------------------

def test_apply_hardlinks_creates_files_and_sets_prepared_path(isolated_db, tmp_path):
    conn = _open(isolated_db)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    _set_hardlink_base(conn, prepared)
    _series_id, season_id = _seed_series_season(conn)
    sources = []
    ep_ids = []
    for i in (1, 2):
        src = tmp_path / f"S01E0{i}.mkv"
        src.write_bytes(f"video {i}".encode())
        sources.append(src)
        ep_ids.append(_seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p"))

    result = apply_season_hardlinks(season_id, conn)

    assert result["status"] == "applied"
    assert len(result["episodes"]) == 2
    created_files = list(prepared.rglob("*.mkv"))
    assert len(created_files) == 2
    # All in the SAME shared season folder.
    assert len({f.parent for f in created_files}) == 1
    # Originals never modified.
    for src in sources:
        assert src.exists()
    # Each episode's prepared_path now points at its hardlinked copy — this
    # is what mkv_remux._get_target_path needs to find the right file for
    # the remux step that runs right after this one in upload_queue.py.
    for ep_id in ep_ids:
        row = conn.execute("SELECT prepared_path, nomenclature_status FROM library_items WHERE id = ?", (ep_id,)).fetchone()
        assert row["prepared_path"] is not None
        assert row["prepared_path"] in [str(f) for f in created_files]
        assert row["nomenclature_status"] == "Correcta"
    conn.close()


def test_apply_hardlinks_blocked_when_plan_invalid(isolated_db, tmp_path):
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", available=False)

    result = apply_season_hardlinks(season_id, conn)

    assert result["status"] == "blocked"
    assert result["episodes"] == []
    conn.close()


def test_apply_rename_mode_moves_files_in_place_and_updates_path(isolated_db, tmp_path):
    conn = _open(isolated_db)
    _set_use_hardlinks(conn, False)
    _series_id, season_id = _seed_series_season(conn)
    season_dir = tmp_path / "Season 1"
    season_dir.mkdir()
    ep_ids = []
    for i in (1, 2):
        src = season_dir / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        ep_ids.append(_seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p"))

    result = apply_season_hardlinks(season_id, conn)

    assert result["status"] == "applied"
    renamed_files = list(season_dir.glob("*.mkv"))
    assert len(renamed_files) == 2  # originals renamed in place, none duplicated
    for ep_id in ep_ids:
        row = conn.execute("SELECT path, prepared_path FROM library_items WHERE id = ?", (ep_id,)).fetchone()
        assert row["path"] in [str(f) for f in renamed_files]
        assert row["prepared_path"] == row["path"]
    conn.close()


# ---------------------------------------------------------------------------
# Per-episode read views (backing the wizard's "Ver nombre de todos los
# capítulos" / "Ver MediaInfo" / "Ver Remux" for a season target)
# ---------------------------------------------------------------------------

def test_get_season_episode_names_returns_one_entry_per_available_episode(isolated_db, tmp_path):
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    for i in (1, 2):
        src = tmp_path / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")
    _seed_episode(conn, season_id, number=3, title="One Piece S01E03", available=False)

    result = get_season_episode_names(season_id, conn=conn)

    assert len(result["episodes"]) == 2
    for ep in result["episodes"]:
        assert ep["torrent_name"]
        assert ep["internal_mkv_title"]
    conn.close()


def test_get_season_episode_mediainfo_reports_unavailable_for_bad_path(isolated_db):
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path="/nope/does/not/exist.mkv")

    result = get_season_episode_mediainfo(season_id, conn=conn)

    assert len(result["episodes"]) == 1
    assert result["episodes"][0]["report"]["available"] is False
    conn.close()


def test_get_season_episode_remux_previews_one_per_episode(isolated_db, tmp_path):
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    src = tmp_path / "S01E01.mkv"
    src.write_bytes(b"not a real mkv")
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path=str(src), quality="WEBDL-1080p")

    result = get_season_episode_remux_previews(season_id, conn=conn)

    assert len(result["episodes"]) == 1
    assert "plan" in result["episodes"][0]
    conn.close()
