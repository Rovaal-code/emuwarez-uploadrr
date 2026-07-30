"""Tests for services/season_pack.py — one season-pack release for a whole
Temporada, ported from legacy.py::build_plan()'s season_pack branch, now
extended with: live progress, blocking (not warning) on an incomplete
season, cross-episode consistency validation, a rename-in-place technique
requiring every episode to already share one folder, and the per-episode
read views (names/mediainfo/remux) backing the wizard.

conftest.py provides isolated_db (autouse) pointing CONFIG_DIR to a tmp dir.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from emuwarez_uploadrr.database import init_db, connect
from emuwarez_uploadrr.services import media_info_service
from emuwarez_uploadrr.services.season_pack import (
    build_season_pack_plan,
    apply_season_pack,
    get_season_plan_progress,
    get_season_episode_names,
    get_season_episode_mediainfo,
    get_season_episode_remux_previews,
    preview_season_pack_title,
    _build_safe_folder_rename_plan,
    _apply_folder_rename,
    _sanitize_pack_folder_name,
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


# subtitle_languages defaults to Castilian because a season pack now REQUIRES
# it on every episode (season_pack.py::_subtitle_errors) — an episode with no
# subtitle info is not a pack-eligible episode, so it can't be the default for
# tests that aren't about subtitles at all. The subtitle tests pass it
# explicitly.
def _seed_episode(conn, season_id, *, number, title, path=None, available=True, quality=None,
                   video_codec=None, audio_codec=None, audio_languages=None,
                   subtitle_languages="spa", source=None):
    status = "Disponible" if available else "Faltante"
    cur = conn.execute(
        """INSERT INTO library_items
           (item_type, title, year, local_status, request_status, nomenclature_status,
            parent_id, season_number, episode_number, path, quality,
            video_codec, audio_codec, audio_languages, subtitle_languages, source, updated_at)
           VALUES ('episode', ?, 1999, ?, 'Sin petición', 'No adaptada', ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (title, status, season_id, number, path, quality,
         video_codec, audio_codec, audio_languages, subtitle_languages, source),
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
    _series_id, season_id = _seed_series_season(conn)
    src1 = tmp_path / "S01E01.mkv"
    src1.write_bytes(b"video")
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path=str(src1), quality="WEBDL-1080p")
    _seed_episode(conn, season_id, number=2, title="One Piece S01E02", available=False)

    plan = build_season_pack_plan(season_id, conn=conn)

    assert plan["status"] == "blocked"
    assert any("incompleta" in e for e in plan["errors"])
    conn.close()


def test_plan_full_season_all_episodes_present(isolated_db, tmp_path):
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    for i in (1, 2):
        src = tmp_path / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    plan = build_season_pack_plan(season_id, conn=conn)

    assert plan["status"] == "valid"
    assert len(plan["episodes"]) == 2
    assert plan["season_pack_title"].startswith("One Piece S01")
    # All available episodes already share tmp_path — that becomes the pack folder.
    assert plan["pack_folder"] == str(tmp_path)
    # Each episode gets its own individually-named destination inside the
    # SAME shared season folder — not the season pack title verbatim.
    folders = {ep["destination_path"].rsplit("/", 1)[0] for ep in plan["episodes"]}
    assert len(folders) == 1
    filenames = {ep["proposed_filename"] for ep in plan["episodes"]}
    assert len(filenames) == 2
    conn.close()


def test_plan_blocks_on_codec_mismatch(isolated_db, tmp_path):
    conn = _open(isolated_db)
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


def test_plan_valid_when_shared_folder(isolated_db, tmp_path):
    # Every available episode already lives in the same folder (the common
    # Sonarr/Radarr convention) — the pack works, renaming each episode in
    # place there.
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    season_dir = tmp_path / "Season 1"
    season_dir.mkdir()
    for i in (1, 2):
        src = season_dir / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    plan = build_season_pack_plan(season_id, conn=conn)

    assert plan["status"] == "valid"
    assert plan["pack_folder"] == str(season_dir)
    conn.close()


def test_plan_blocked_when_episodes_scattered(isolated_db, tmp_path):
    conn = _open(isolated_db)
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


def test_plan_tag_override_used_in_title(isolated_db, tmp_path):
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    season_dir = tmp_path / "Season 1"
    season_dir.mkdir()
    for i in (1, 2):
        src = season_dir / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    plan = build_season_pack_plan(season_id, conn=conn, tag_override="MYTAG")

    assert plan["status"] == "valid"
    assert plan["release_tag"] == "MYTAG"
    assert plan["season_pack_title"].endswith("-MYTAG")
    conn.close()


def test_plan_title_includes_provider_with_source_override(isolated_db, tmp_path):
    """_build_season_pack_title() previously never combined provider with
    source at all — a season pack's title never showed AMZN/NF/DSNP… even
    when its source was WEB-DL from a specific platform, unlike a single
    movie/episode's own title builder."""
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    season_dir = tmp_path / "Season 1"
    season_dir.mkdir()
    for i in (1, 2):
        src = season_dir / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    plan = build_season_pack_plan(season_id, conn=conn, source_override="WEB-DL", provider_override="AMZN")

    assert plan["status"] == "valid"
    assert "AMZN WEB-DL" in plan["season_pack_title"]
    conn.close()


def test_plan_includes_source_comparison_from_first_episode(isolated_db, tmp_path):
    """Backs the wizard's Source field blinking "compare" link at the season
    level too (previously only shown once you opened "Ver MediaInfo")."""
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    season_dir = tmp_path / "Season 1"
    season_dir.mkdir()
    for i in (1, 2):
        src = season_dir / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    fake_comparison = {"from_name": "WEB-DL", "from_radarr": "WEB-DL", "from_mediainfo": "WEB-DL",
                        "mediainfo_confirmed": True, "agree": True, "engine": None}
    with patch("emuwarez_uploadrr.services.source_assistant.build_editable_nomenclature_fields",
               return_value={"source_comparison": fake_comparison}) as mocked:
        plan = build_season_pack_plan(season_id, conn=conn)

    assert mocked.call_count == 1
    assert plan["source_comparison"] == fake_comparison
    conn.close()


def test_plan_progress_reaches_total(isolated_db, tmp_path):
    conn = _open(isolated_db)
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
# apply_season_pack
# ---------------------------------------------------------------------------

def test_apply_pack_blocked_when_plan_invalid(isolated_db, tmp_path):
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    _seed_episode(conn, season_id, number=1, title="One Piece S01E01", available=False)

    result = apply_season_pack(season_id, conn)

    assert result["status"] == "blocked"
    assert result["episodes"] == []
    conn.close()


def test_apply_pack_renames_files_in_place_and_updates_path(isolated_db, tmp_path):
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    season_dir = tmp_path / "Season 1"
    season_dir.mkdir()
    ep_ids = []
    for i in (1, 2):
        src = season_dir / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        ep_ids.append(_seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p"))

    result = apply_season_pack(season_id, conn)

    assert result["status"] == "applied"
    # The shared folder itself gets renamed to the pack's own release title
    # as the final step (so the torrent Uploadrr-EMU builds from it isn't
    # literally named "Season 1") — files end up under that NEW folder, not
    # the original Sonarr-named one.
    new_pack_folder = Path(result["pack_folder"])
    assert new_pack_folder != season_dir
    assert not season_dir.exists()
    renamed_files = list(new_pack_folder.glob("*.mkv"))
    assert len(renamed_files) == 2  # originals renamed in place, none duplicated
    for ep_id in ep_ids:
        row = conn.execute("SELECT path, prepared_path, nomenclature_status FROM library_items WHERE id = ?", (ep_id,)).fetchone()
        assert row["path"] in [str(f) for f in renamed_files]
        assert row["prepared_path"] == row["path"]
        assert row["nomenclature_status"] == "Correcta"
    conn.close()


def test_apply_pack_folder_name_matches_release_title(isolated_db, tmp_path):
    """Regression: qBittorrent showed the torrent as literally "Season 2"
    (Sonarr's own folder name) while eMuwarez itself got the correct release
    name — because only the FILES were renamed in place, never the folder
    Uploadrr-EMU is pointed at (torf.Torrent() defaults its name to
    os.path.basename(path))."""
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    season_dir = tmp_path / "Season 1"
    season_dir.mkdir()
    for i in (1, 2):
        src = season_dir / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    result = apply_season_pack(season_id, conn)

    assert result["status"] == "applied"
    new_pack_folder = Path(result["pack_folder"])
    assert new_pack_folder.parent == season_dir.parent  # renamed in place, not moved elsewhere
    assert new_pack_folder.name == _sanitize_pack_folder_name(result["season_pack_title"])
    conn.close()


def test_apply_pack_leaves_folder_untouched_when_a_file_rename_fails(isolated_db, tmp_path):
    """The folder rename is deliberately the LAST step — if any episode file
    fails to rename, the shared folder must be left exactly as it was, so a
    retry doesn't find episodes pointing at a folder name that no longer
    exists on disk."""
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    season_dir = tmp_path / "Season 1"
    season_dir.mkdir()
    ep_ids = []
    for i in (1, 2):
        src = season_dir / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        ep_ids.append(_seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p"))

    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "valid"
    # Pre-create the second episode's own destination filename so its rename
    # is blocked (destination already exists) — simulates a real mid-loop
    # failure without needing to mock the rename primitives.
    colliding_dst = plan["episodes"][1]["destination_path"]
    Path(colliding_dst).write_bytes(b"already here")

    result = apply_season_pack(season_id, conn)

    assert result["status"] == "failed"
    assert season_dir.exists()  # folder rename never attempted
    assert result["pack_folder"] == str(season_dir)
    conn.close()


def test_build_safe_folder_rename_plan(tmp_path):
    src = tmp_path / "Season 1"
    src.mkdir()
    other_parent = tmp_path / "other"
    other_parent.mkdir()

    ok = _build_safe_folder_rename_plan(str(src), str(tmp_path / "Renamed Title"))
    assert ok["status"] == "ready"

    missing = _build_safe_folder_rename_plan(str(tmp_path / "missing"), str(tmp_path / "x"))
    assert missing["status"] == "blocked"

    wrong_parent = _build_safe_folder_rename_plan(str(src), str(other_parent / "Renamed Title"))
    assert wrong_parent["status"] == "blocked"

    dst_exists = tmp_path / "Already Here"
    dst_exists.mkdir()
    collision = _build_safe_folder_rename_plan(str(src), str(dst_exists))
    assert collision["status"] == "blocked"


def test_apply_folder_rename(tmp_path):
    src = tmp_path / "Season 1"
    src.mkdir()
    (src / "file.mkv").write_bytes(b"video")
    dst = tmp_path / "Renamed Title"

    plan = _build_safe_folder_rename_plan(str(src), str(dst))
    result = _apply_folder_rename(plan)

    assert result["status"] == "applied"
    assert dst.is_dir()
    assert (dst / "file.mkv").exists()
    assert not src.exists()


# ---------------------------------------------------------------------------
# Per-episode read views (backing the wizard's "Ver nombre de todos los
# capítulos" / "Ver MediaInfo" / "Ver Remux" for a season target)
# ---------------------------------------------------------------------------

def test_apply_pack_forwards_overrides_to_real_files(isolated_db, tmp_path):
    """Regression: apply_season_pack() used to call build_season_pack_plan()
    with NO overrides at all, silently discarding whatever source/provider/
    tag the caller had already resolved — so even the Automático
    source-disparity gate's choice never actually reached the renamed
    files, only a preview snapshot."""
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    season_dir = tmp_path / "Season 1"
    season_dir.mkdir()
    for i in (1, 2):
        src = season_dir / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    result = apply_season_pack(season_id, conn, source_override="BluRay", tag_override="MYTAG")

    assert result["status"] == "applied"
    assert result["source"] == "BluRay"
    assert result["release_tag"] == "MYTAG"
    assert result["season_pack_title"].endswith("-MYTAG")
    assert "BluRay" in result["season_pack_title"]
    conn.close()


def test_get_season_episode_names_applies_overrides_to_every_episode(isolated_db, tmp_path):
    """Regression: editing Source/Proveedor/Tag in the season wizard changed
    the season pack's own title but NOT each episode's individual name in
    "Ver nombre de todos los capítulos" — every episode kept showing its
    own auto-detected value, visibly disagreeing with the pack title."""
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    for i in (1, 2):
        src = tmp_path / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src), quality="WEBDL-1080p")

    result = get_season_episode_names(
        season_id, conn=conn, source_override="BluRay", tag_override="MYTAG",
    )

    assert len(result["episodes"]) == 2
    for ep in result["episodes"]:
        assert "BluRay" in (ep["torrent_name"] or "")
        assert (ep["torrent_name"] or "").endswith("-MYTAG")
    conn.close()


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


def test_get_season_episode_mediainfo_prefers_prepared_path_over_stale_path(isolated_db, tmp_path):
    """Regression: this read a raw `path` (the Radarr/Sonarr-reported, ORIGINAL
    filename) that goes stale once nomenclature has already been applied once
    (e.g. a prior retry) — "Ver MediaInfo" showed the Source from the OLD
    name (e.g. "WEBRIP") while the real applied/uploaded name (which reads
    prepared_path, the current renamed file) showed something else entirely
    (e.g. "BluRay"). Every other per-episode reader in this module
    (nomenclature.py, mkv_remux.py) already prefers prepared_path — this one
    didn't."""
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    # `path` doesn't exist at all (simulating a stale, already-renamed-away
    # Radarr/Sonarr path) — only prepared_path points at a real file. If the
    # fix reads path instead, this must come back unavailable.
    stale_path = str(tmp_path / "One.Piece.S01E01.WEBRIP.mkv")
    current = tmp_path / "One Piece - S01E01 [1080p].mkv"
    current.write_bytes(b"fake")
    ep_id = _seed_episode(conn, season_id, number=1, title="One Piece S01E01", path=stale_path)
    conn.execute("UPDATE library_items SET prepared_path = ? WHERE id = ?", (str(current), ep_id))
    conn.commit()

    info = {"media": {"track": [
        {"@type": "General"},
        {"@type": "Video", "Format": "AVC", "Width": "1920", "Height": "1080"},
    ]}}
    with (
        patch.object(media_info_service, "mediainfo_available", return_value=True),
        patch.object(media_info_service.legacy, "run_mediainfo_json", return_value=info),
    ):
        result = get_season_episode_mediainfo(season_id, conn=conn)

    assert result["episodes"][0]["report"]["available"] is True
    conn.close()


def test_get_season_episode_mediainfo_uses_radarr_source_not_just_bitrate_guess(isolated_db, tmp_path):
    """Regression: get_season_episode_mediainfo() called build_mediainfo_report()
    without radarr_source at all, so the Source row's "eMuwarez" column
    skipped straight from "nombre del archivo" to the bitrate tool's own
    estimate — disagreeing with the actually-applied nomenclature, which
    DOES fall back to Radarr/Sonarr before the bitrate tool
    (nomenclature.py::_infer_source_from_item). Real case (Los Tudor S02,
    2026-07-30): showed "WEBRip" here while the real season title said
    "BluRay"."""
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    # No source token in the filename, so the name-based check alone can't
    # resolve anything — it has to fall back to Radarr/Sonarr's own value.
    src = tmp_path / "Los_Tudor_2x05_1080p.mkv"
    src.write_bytes(b"video")
    _seed_episode(conn, season_id, number=5, title="Los Tudor 2x05", path=str(src), source="BluRay")

    info = {"media": {"track": [
        {"@type": "General"},
        {"@type": "Video", "Format": "AVC", "Width": "1920", "Height": "1080"},
    ]}}
    with (
        patch.object(media_info_service, "mediainfo_available", return_value=True),
        patch.object(media_info_service.legacy, "run_mediainfo_json", return_value=info),
        patch("emuwarez_uploadrr.services.source_engine.analyze_for_app", return_value=None),
        patch("emuwarez_uploadrr.services.source_engine.winning_app_source", return_value="WEBRip"),
    ):
        result = get_season_episode_mediainfo(season_id, conn=conn)

    source_row = next(r for r in result["episodes"][0]["report"]["rows"] if r["field"] == "Source")
    assert source_row["emu"] == "BluRay"
    conn.close()


def test_get_season_episode_mediainfo_computes_source_comparison_once_and_shares_it(isolated_db, tmp_path):
    """A season pack can only reach this screen once every episode already
    agrees on source (build_season_pack_plan's consistency check blocks the
    upload otherwise) — so the name/Radarr/MediaInfo cross-check (the
    "Internal Source Tool" blinking link) is computed once, from the first
    available episode, and reused for every episode instead of re-running
    the engine's analysis per chapter."""
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    for i in (1, 2):
        src = tmp_path / f"S01E0{i}.mkv"
        src.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(src))

    fake_comparison = {"from_name": "BluRay", "from_radarr": "BluRay", "from_mediainfo": "BluRay",
                        "mediainfo_confirmed": True, "agree": True, "engine": None}
    info = {"media": {"track": [{"@type": "Video", "Format": "AVC"}]}}
    with (
        patch("emuwarez_uploadrr.services.source_assistant.build_editable_nomenclature_fields",
              return_value={"source_comparison": fake_comparison}) as mocked_fields,
        patch.object(media_info_service, "mediainfo_available", return_value=True),
        patch.object(media_info_service.legacy, "run_mediainfo_json", return_value=info),
    ):
        result = get_season_episode_mediainfo(season_id, conn=conn)

    assert mocked_fields.call_count == 1
    assert len(result["episodes"]) == 2
    assert result["episodes"][0]["source_comparison"] == fake_comparison
    assert result["episodes"][1]["source_comparison"] == fake_comparison
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


def test_episode_display_title_matches_canonical_format(isolated_db, tmp_path):
    """"Ver MediaInfo"/"Ver Remux" accordion headers must use the exact same
    "Serie (Año) - SxxEyy - Título" format Biblioteca/Subidas/Peticiones
    already use (library.py's content_display_title + episode_own_name) —
    previously they showed the raw stored title verbatim instead."""
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn, series_title="One Piece", year=1999)
    src1 = tmp_path / "S01E05.mkv"
    src1.write_bytes(b"video")
    _seed_episode(
        conn, season_id, number=5,
        title="One Piece S01E05 - El Placer De Su Majestad",
        path=str(src1), quality="WEBDL-1080p",
    )

    mi_result = get_season_episode_mediainfo(season_id, conn=conn)
    remux_result = get_season_episode_remux_previews(season_id, conn=conn)

    expected = "One Piece (1999) - S01E05 - El Placer De Su Majestad"
    assert mi_result["episodes"][0]["display_title"] == expected
    assert remux_result["episodes"][0]["display_title"] == expected
    conn.close()


# ---------------------------------------------------------------------------
# preview_season_pack_title — cheap live-preview while editing Source/
# Proveedor/Tag in the wizard (no DB/disk I/O at all).
# ---------------------------------------------------------------------------

def test_preview_season_pack_title_basic():
    result = preview_season_pack_title({
        "title": "One Piece", "year": 1999, "season_number": 1,
        "resolution": "1080p", "source": "BluRay", "video_codec": "x264",
        "audio_summary": "DUAL DD 5.1", "subtitle_summary": "SUBS", "tag": "CCX94",
    })
    assert result == {"torrent_name": "One Piece S01 1999 1080p BluRay x264 DUAL DD 5.1 SUBS-CCX94"}


def test_preview_season_pack_title_combines_provider_with_web_dl_source():
    result = preview_season_pack_title({
        "title": "One Piece", "season_number": 1,
        "source": "WEB-DL", "provider": "AMZN", "video_codec": "x264", "tag": "CCX94",
    })
    assert "AMZN WEB-DL" in result["torrent_name"]


def test_preview_season_pack_title_no_season_number_omits_sxx():
    result = preview_season_pack_title({"title": "Movie-ish", "source": "BluRay"})
    assert "S0" not in result["torrent_name"]
    assert result["torrent_name"].startswith("Movie-ish")


# ---------------------------------------------------------------------------
# Subtitles: the one property a pack does NOT require to match across episodes
# ---------------------------------------------------------------------------

def _seed_pack(conn, tmp_path, subs_per_episode, audio="spa / eng"):
    """A complete, otherwise-consistent 2-episode season in a shared folder,
    with the given subtitle_languages per episode. `audio` is shared by every
    episode, as a real pack requires (it is in _CONSISTENCY_FIELDS)."""
    _series_id, season_id = _seed_series_season(conn)
    folder = tmp_path / "One Piece" / "Season 1"
    folder.mkdir(parents=True)
    for i, subs in enumerate(subs_per_episode, start=1):
        f = folder / f"S01E0{i}.mkv"
        f.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(f),
                      quality="WEBDL-1080p", video_codec="x264", audio_codec="AC3",
                      audio_languages=audio, subtitle_languages=subs, source="WEB-DL")
    return season_id


def test_pack_allowed_when_episodes_have_different_subtitles_but_all_castilian(isolated_db, tmp_path):
    """The point of the exception: eMuwarez takes the pack even though episode 1
    also carries English subs and episode 2 doesn't."""
    conn = _open(isolated_db)
    season_id = _seed_pack(conn, tmp_path, ["spa / eng", "spa"])
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] != "blocked", plan["errors"]
    assert not any("subtítulo" in e.lower() for e in plan["errors"])
    conn.close()


def test_pack_blocked_when_an_episode_has_no_castilian_subtitles(isolated_db, tmp_path):
    conn = _open(isolated_db)
    season_id = _seed_pack(conn, tmp_path, ["spa", "eng"], audio="eng")
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "blocked"
    assert any("no tiene castellano" in e for e in plan["errors"])
    # Names the offending episode, not just "something is wrong".
    assert any("capítulo 2" in e for e in plan["errors"])
    conn.close()


def test_pack_blocked_when_an_episode_has_no_subtitles_at_all(isolated_db, tmp_path):
    """"We never read its subtitles" is not evidence that the rule is met."""
    conn = _open(isolated_db)
    season_id = _seed_pack(conn, tmp_path, ["spa", None], audio="eng")
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "blocked"
    assert any("sin subtítulos detectados" in e for e in plan["errors"])
    conn.close()


def test_castilian_audio_makes_subtitles_unnecessary(isolated_db, tmp_path):
    """A dubbed pack with NO subtitle tracks at all is valid: the tracker only
    wants Castilian present, and the audio already carries it."""
    conn = _open(isolated_db)
    season_id = _seed_pack(conn, tmp_path, [None, None], audio="spa / eng")
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] != "blocked", plan["errors"]
    conn.close()


def test_latin_only_audio_does_not_exempt_from_subtitles(isolated_db, tmp_path):
    conn = _open(isolated_db)
    season_id = _seed_pack(conn, tmp_path, [None, None], audio="es-419")
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "blocked"
    assert any("no tiene castellano" in e for e in plan["errors"])
    conn.close()


def test_pack_still_blocked_on_a_non_subtitle_mismatch(isolated_db, tmp_path):
    """The exception is subtitles only — the other five properties stay strict."""
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    folder = tmp_path / "One Piece" / "Season 1"
    folder.mkdir(parents=True)
    for i, audio in enumerate(["spa / eng", "spa"], start=1):
        f = folder / f"S01E0{i}.mkv"
        f.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(f),
                      quality="WEBDL-1080p", video_codec="x264", audio_codec="AC3",
                      audio_languages=audio, subtitle_languages="spa", source="WEB-DL")
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "blocked"
    assert any("idiomas de audio" in e for e in plan["errors"])
    conn.close()


def test_latin_only_subtitles_do_not_satisfy_the_rule(isolated_db, tmp_path):
    conn = _open(isolated_db)
    season_id = _seed_pack(conn, tmp_path, ["spa", "es-419"], audio="eng")
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "blocked"
    assert any("no tiene castellano" in e for e in plan["errors"])
    conn.close()


# ---------------------------------------------------------------------------
# Cancelling an in-flight plan (the wizard was closed)
# ---------------------------------------------------------------------------

def test_plan_stops_early_when_cancelled(isolated_db, tmp_path, monkeypatch):
    """Building a plan is one real nomenclature proposal per episode. Closing
    the wizard has to stop that work, not just stop waiting for it."""
    import emuwarez_uploadrr.services.season_pack as sp

    conn = _open(isolated_db)
    season_id = _seed_pack(conn, tmp_path, ["spa"] * 6)

    real_build = sp.build_nomenclature_proposal
    built = []

    def counting_build(item_id, **kwargs):
        built.append(item_id)
        if len(built) == 2:            # user closes the wizard mid-build
            sp.request_season_plan_cancel(season_id)
        return real_build(item_id, **kwargs)

    monkeypatch.setattr(sp, "build_nomenclature_proposal", counting_build)
    plan = sp.build_season_pack_plan(season_id, conn=conn)

    assert plan["status"] == "cancelled"
    assert plan["errors"] == []          # not a failure, nothing to report
    # Stopped at the next boundary instead of grinding through all 6.
    assert len(built) == 2, built
    conn.close()


def test_cancel_flag_does_not_leak_into_the_next_plan(isolated_db, tmp_path):
    """A stale flag would make the next season the user opens return
    'cancelled' immediately, for no visible reason."""
    from emuwarez_uploadrr.services.season_pack import (
        build_season_pack_plan, request_season_plan_cancel,
    )
    conn = _open(isolated_db)
    season_id = _seed_pack(conn, tmp_path, ["spa", "spa"])
    request_season_plan_cancel(season_id)
    build_season_pack_plan(season_id, conn=conn)          # consumes the flag
    plan = build_season_pack_plan(season_id, conn=conn)   # must run normally
    assert plan["status"] != "cancelled"
    conn.close()


def test_cancel_endpoint_is_safe_with_nothing_running(client, auth_headers):
    r = client.post("/api/library/season/12345/pack-preview/cancel", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelling"


def test_an_inconsistent_season_still_has_individually_uploadable_episodes(isolated_db, tmp_path):
    """The premise the per-episode upload mode rests on: the pack's consistency
    rules exist because a pack ships ONE release name for everything inside it.
    Each episode ships its own, so episodes that can't go together as a pack are
    still perfectly uploadable one by one."""
    from emuwarez_uploadrr.services.upload_checks import run_upload_checks

    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    folder = tmp_path / "One Piece" / "Season 1"
    folder.mkdir(parents=True)
    ids = []
    # Two episodes that disagree on video codec AND audio languages — the pack
    # is blocked twice over — but each one has Castilian on its own.
    for i, (codec, audio) in enumerate([("x264", "spa"), ("x265", "spa / eng")], start=1):
        f = folder / f"S01E0{i}.mkv"
        f.write_bytes(b"video")
        ids.append(_seed_episode(
            conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(f),
            quality="WEBDL-1080p", video_codec=codec, audio_codec="AC3",
            audio_languages=audio, subtitle_languages="spa", source="WEB-DL",
        ))

    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "blocked"
    assert any("códec de vídeo" in e for e in plan["errors"])

    # …yet neither episode fails on its own account: no check about the season's
    # consistency, and the Castilian one passes for both.
    for episode_id in ids:
        checks = run_upload_checks(conn, episode_id)
        failed = [c for c in checks["checks"] if c["status"] == "fail"]
        assert not any(c["id"] == "spanish" for c in failed), failed
        assert not any("temporada" in (c.get("message") or "").lower() for c in failed), failed
    conn.close()
