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

import pytest

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


def test_a_codec_mismatch_no_longer_blocks_it_just_empties_the_field(isolated_db, tmp_path):
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

    # Antes esto bloqueaba. Sigue siendo la misma temporada: se sube, y el
    # códec simplemente no se anuncia, porque no hay uno solo que sea cierto.
    assert plan["status"] == "valid"
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
    # Los ficheros se renombran EN SU SITIO: la carpeta de la temporada sigue
    # siendo la misma y con el mismo nombre (ver
    # test_apply_pack_no_toca_la_carpeta_de_sonarr).
    pack_folder = Path(result["pack_folder"])
    assert pack_folder == season_dir
    assert season_dir.exists()
    renamed_files = list(pack_folder.glob("*.mkv"))
    assert len(renamed_files) == 2  # originals renamed in place, none duplicated
    for ep_id in ep_ids:
        row = conn.execute("SELECT path, prepared_path, nomenclature_status FROM library_items WHERE id = ?", (ep_id,)).fetchone()
        assert row["path"] in [str(f) for f in renamed_files]
        assert row["prepared_path"] == row["path"]
        assert row["nomenclature_status"] == "Correcta"
    conn.close()


def test_apply_pack_no_toca_la_carpeta_de_sonarr(isolated_db, tmp_path):
    """La carpeta de la temporada se queda EXACTAMENTE donde estaba.

    Antes se renombraba al título del release, porque torf toma el nombre del
    torrent del nombre de la carpeta. Funcionaba, pero tocaba la biblioteca del
    usuario —Sonarr gestiona esa carpeta— y dejaba rutas guardadas apuntando a
    un sitio que ya no existía, de donde salían nombres calculados con datos de
    Radarr/Sonarr en vez de con el fichero.

    Ahora lo que se le entrega a Uploadrr es una carpeta de ENLACES aparte, y
    se crea después del remux (upload_queue.py), no aquí: el remux sustituye
    cada fichero con os.replace y un enlace anterior apuntaría a los datos
    viejos.
    """
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
    assert Path(result["pack_folder"]) == season_dir
    assert season_dir.is_dir(), "la carpeta original tiene que seguir existiendo"
    assert season_dir.name == "Season 1", "el nombre de la carpeta no se toca"
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


@pytest.mark.usefixtures("ficheros_de_mentira")
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


@pytest.mark.usefixtures("ficheros_de_mentira")
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
        patch.object(media_info_service.media_probe, "run_mediainfo_json", return_value=info),
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
        patch.object(media_info_service.media_probe, "run_mediainfo_json", return_value=info),
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
        patch.object(media_info_service.media_probe, "run_mediainfo_json", return_value=info),
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
    """"Ver MediaInfo"/"Ver Pistas" accordion headers must use the exact same
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


def test_episode_names_selector_uses_the_short_canonical_title(isolated_db, tmp_path):
    """El desplegable de "Ver nombre de todos los capítulos" usa el mismo
    título que las cabeceras de Ver MediaInfo y Ver Pistas, para que las tres
    pantallas nombren igual al mismo capítulo."""
    from emuwarez_uploadrr.services.season_pack import get_season_episode_names
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn, series_title="One Piece", year=1999)
    src = tmp_path / "S01E05.mkv"
    src.write_bytes(b"video")
    _seed_episode(
        conn, season_id, number=5,
        title="One Piece S01E05 - El Placer De Su Majestad",
        path=str(src), quality="WEBDL-1080p",
    )

    result = get_season_episode_names(season_id, conn=conn)
    assert result["episodes"][0]["display_title"] == "One Piece (1999) - S01E05 - El Placer De Su Majestad"
    conn.close()


# ---------------------------------------------------------------------------
# preview_season_pack_title — cheap live-preview while editing Source/
# Proveedor/Tag in the wizard (no DB/disk I/O at all).
# ---------------------------------------------------------------------------

def _pack_de_dos(conn, tmp_path, **por_capitulo):
    """Dos capítulos iguales salvo las columnas de `por_capitulo` (listas)."""
    _series_id, season_id = _seed_series_season(conn)
    folder = tmp_path / "One Piece" / "Season 1"
    folder.mkdir(parents=True)
    for i in (1, 2):
        f = folder / f"S01E0{i}.mkv"
        f.write_bytes(b"video")
        ep = _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(f),
                           quality="WEBDL-1080p", video_codec="x264", audio_codec="AC3",
                           audio_languages="spa", source="WEB-DL")
        for col, valores in por_capitulo.items():
            conn.execute(f"UPDATE library_items SET {col} = ? WHERE id = ?", (valores[i - 1], ep))
    conn.commit()
    return season_id


def test_un_pack_con_fuentes_distintas_se_bloquea(isolated_db, tmp_path):
    """Antes el título se quedaba sin Fuente y el pack salía "válido"."""
    conn = _open(isolated_db)
    plan = build_season_pack_plan(_pack_de_dos(conn, tmp_path, source=["WEB-DL", "BluRay"]), conn=conn)
    assert plan["status"] == "blocked"
    assert any("source distinto (BluRay)" in e for e in plan["errors"]), plan["errors"]
    conn.close()


def test_un_pack_con_hdr_y_sdr_se_bloquea(isolated_db, tmp_path):
    conn = _open(isolated_db)
    plan = build_season_pack_plan(_pack_de_dos(conn, tmp_path, dynamic_range=["HDR10", None]), conn=conn)
    assert plan["status"] == "blocked"
    assert any("HDR/DV distinto (sin HDR)" in e for e in plan["errors"]), plan["errors"]
    conn.close()


def test_un_pack_con_proveedores_distintos_se_bloquea(isolated_db, tmp_path):
    """El título decía el proveedor del primer capítulo aunque otro fuera de NF."""
    conn = _open(isolated_db)
    season_id = _pack_de_dos(conn, tmp_path)
    for i, nombre in ((1, "S01E01.AMZN.WEB-DL.mkv"), (2, "S01E02.NF.WEB-DL.mkv")):
        viejo = tmp_path / "One Piece" / "Season 1" / f"S01E0{i}.mkv"
        nuevo = viejo.with_name(nombre)
        viejo.rename(nuevo)
        conn.execute("UPDATE library_items SET path = ? WHERE path = ?", (str(nuevo), str(viejo)))
    conn.commit()
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "blocked"
    assert any("proveedores distintos (AMZN, NF)" in e for e in plan["errors"]), plan["errors"]
    conn.close()


def test_el_titulo_del_pack_lleva_el_hdr_de_sus_capitulos(isolated_db, tmp_path):
    conn = _open(isolated_db)
    plan = build_season_pack_plan(_pack_de_dos(conn, tmp_path, dynamic_range=["HDR10", "HDR10"]), conn=conn)
    assert plan["status"] == "valid", plan["errors"]
    assert "WEB-DL HDR x264" in plan["season_pack_title"]
    assert plan["dynamic_range"] == "HDR"
    conn.close()


def test_el_pack_se_escribe_igual_que_sus_capitulos():
    """2160p lleva "4K UHD" y el DV/HDR va delante del códec, como en cada
    capítulo; y «Fate/Zero» se queda en «Fate Zero», no «FateZero»."""
    result = preview_season_pack_title({
        "title": "Fate/Zero", "year": 2011, "season_number": 1, "resolution": "2160p",
        "source": "WEB-DL", "provider": "NF", "dynamic_range": "Dolby Vision / SMPTE ST 2086",
        "video_codec": "HEVC", "audio_summary": "ESP-JAP DD+ 5.1", "subtitle_summary": "SUBS",
        "tag": "EMUWAREZ",
    })
    assert result["torrent_name"] == (
        "Fate Zero S01 2011 2160p 4K UHD NF WEB-DL DV HDR HEVC ESP-JAP DD+ 5.1 SUBS-EMUWAREZ")


def test_un_pack_con_un_nombre_demasiado_largo_se_bloquea(isolated_db, tmp_path):
    conn = _open(isolated_db)
    season_id = _pack_de_dos(conn, tmp_path)
    plan = build_season_pack_plan(season_id, conn=conn, title_override="Título larguísimo " * 14)
    assert plan["status"] == "blocked"
    assert any("255" in e for e in plan["errors"]), plan["errors"]
    conn.close()


def test_la_carpeta_del_pack_no_lleva_caracteres_que_windows_rechaza():
    assert _sanitize_pack_folder_name(r'Anacleto: ¿Quién? S01 "x" a|b*c<d>e/f\g.') == (
        "Anacleto ¿Quién S01 x a b c d e f g")


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


def test_different_audio_languages_are_summed_not_blocked(isolated_db, tmp_path):
    """Un capítulo con una pista de audio extra ya no tumba el pack: el pack
    CONTIENE los dos idiomas, así que el nombre los anuncia los dos — pero
    marcándolo CUSTOM, porque el inglés solo está en uno de los dos capítulos
    y decir DUAL a secas prometería que está en todos."""
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
    assert plan["status"] == "valid"
    titulo = plan["season_pack_title"]
    # Los dos idiomas se anuncian, pero explícitos y con el aviso: DUAL diría
    # que los dos capítulos traen castellano e inglés, y no es verdad.
    assert "ESP-ING" in titulo and "DUAL" not in titulo, titulo
    assert "CUSTOM" in titulo, titulo
    assert plan["custom"] is True
    conn.close()


def test_a_resolution_mismatch_still_blocks(isolated_db, tmp_path):
    """La resolución es lo único que sigue teniendo que coincidir: un pack con
    capítulos a 1080p y a 720p no es una calidad, son dos."""
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    folder = tmp_path / "One Piece" / "Season 1"
    folder.mkdir(parents=True)
    for i, quality in enumerate(["WEBDL-1080p", "WEBDL-720p"], start=1):
        f = folder / f"S01E0{i}.mkv"
        f.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(f),
                      quality=quality, video_codec="x264", audio_codec="AC3",
                      audio_languages="spa", subtitle_languages="spa", source="WEB-DL")
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "blocked"
    assert any("resolución" in e for e in plan["errors"]), plan["errors"]
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
    # Dos capítulos con resoluciones distintas: eso sí tumba el pack, que es
    # lo único que sigue siendo obligatorio. Pero cada uno tiene castellano.
    for i, quality in enumerate(["WEBDL-1080p", "WEBDL-720p"], start=1):
        f = folder / f"S01E0{i}.mkv"
        f.write_bytes(b"video")
        ids.append(_seed_episode(
            conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(f),
            quality=quality, video_codec="x264", audio_codec="AC3",
            audio_languages="spa", subtitle_languages="spa", source="WEB-DL",
        ))

    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["status"] == "blocked"
    assert any("resolución" in e for e in plan["errors"])

    # …yet neither episode fails on its own account: no check about the season's
    # consistency, and the Castilian one passes for both.
    for episode_id in ids:
        checks = run_upload_checks(conn, episode_id)
        failed = [c for c in checks["checks"] if c["status"] == "fail"]
        assert not any(c["id"] == "spanish" for c in failed), failed
        assert not any("temporada" in (c.get("message") or "").lower() for c in failed), failed
    conn.close()


def test_pack_fields_are_emptied_when_they_differ_and_audios_are_summed(isolated_db, tmp_path):
    """El nombre del pack, con capítulos que ya no tienen por qué coincidir:

    - los idiomas de audio se SUMAN, porque el pack contiene los dos, y el
      pack se marca CUSTOM cuando no todos los capítulos traen lo mismo;
    - lo que no tiene que coincidir y difiere se queda FUERA, porque
      anunciar uno solo sería mentir y anunciar los dos no describe nada.
    """
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn, series_title="One Piece", year=1999)
    folder = tmp_path / "One Piece" / "Season 1"
    folder.mkdir(parents=True)
    # El códec de vídeo y el source SÍ tienen que coincidir; lo que varía
    # son los idiomas.
    datos = [("x264", "WEB-DL", "spa"), ("x264", "WEB-DL", "spa / eng")]
    for i, (codec, source, audio) in enumerate(datos, start=1):
        f = folder / f"S01E0{i}.mkv"
        f.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(f),
                      quality="WEBDL-1080p", video_codec=codec, audio_codec="AC3",
                      audio_languages=audio, subtitle_languages="spa", source=source)

    plan = build_season_pack_plan(season_id, conn=conn)
    titulo = plan["season_pack_title"]
    assert plan["status"] == "valid", plan["errors"]

    # La resolución sí, que es lo único obligatorio.
    assert "1080p" in titulo, titulo
    assert "WEB-DL x264" in titulo, titulo
    # Y los idiomas sumados, explícitos y con CUSTOM: el inglés solo está en
    # el segundo capítulo, así que DUAL a secas prometería de más.
    assert "ESP-ING" in titulo and "DUAL" not in titulo, titulo
    assert "CUSTOM" in titulo, titulo
    conn.close()


def test_rollup_all_sums_what_the_episodes_have(isolated_db, tmp_path):
    """La ficha de una temporada enseña TODO lo que hay debajo ("x264, x265"),
    no un guion. Las columnas de la fila siguen guardando el valor único o
    NULL, que es la señal de acuerdo que usa la regla del pack: si se sumaran
    ahí, `resolution IS NOT NULL` dejaría de significar "coinciden" y la regla
    entera se rompería."""
    from emuwarez_uploadrr.services.library import rollup_all_values
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    for i, (codec, source) in enumerate([("x264", "WEB-DL"), ("x265", "BluRay"), ("x264", "WEB-DL")], start=1):
        f = tmp_path / f"S01E0{i}.mkv"
        f.write_bytes(b"video")
        ep_id = _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(f),
                              quality="WEBDL-1080p", video_codec=codec, audio_codec="AC3",
                              audio_languages="spa", subtitle_languages="spa", source=source)
        # El sembrador guarda `quality`, no `resolution`: aquí interesa la
        # columna que la ficha enseña.
        conn.execute("UPDATE library_items SET resolution = '1080p' WHERE id = ?", (ep_id,))
    conn.commit()

    season = dict(conn.execute("SELECT * FROM library_items WHERE id = ?", (season_id,)).fetchone())
    todos = rollup_all_values(conn, season)

    assert todos["video_codec"] == "x264, x265"      # sin repetir el x264 del tercero
    assert todos["source"] == "WEB-DL, BluRay"
    assert todos["resolution"] == "1080p"            # coinciden: un solo valor
    # Y la columna de la fila NO se toca: sigue siendo la señal de acuerdo.
    assert season["video_codec"] is None
    conn.close()


def test_rollup_all_merges_languages_instead_of_listing_them(isolated_db, tmp_path):
    """Un capítulo ya guarda varios idiomas en un mismo campo ("jpn/spa"), así
    que tratarlos como un valor entero daba "jpn/spa, jpn/spa/eng": el mismo
    idioma repetido y nada legible. Se funden en una sola lista."""
    from emuwarez_uploadrr.services.library import rollup_all_values
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    for i, (audio, subs) in enumerate([("jpn/spa", "spa"), ("jpn/spa/eng", "spa/eng")], start=1):
        f = tmp_path / f"S01E0{i}.mkv"
        f.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(f),
                      quality="WEBDL-1080p", video_codec="x264", audio_codec="AC3",
                      audio_languages=audio, subtitle_languages=subs, source="WEB-DL")

    season = dict(conn.execute("SELECT * FROM library_items WHERE id = ?", (season_id,)).fetchone())
    todos = rollup_all_values(conn, season)

    assert todos["audio_languages"] == "jpn, spa, eng"
    assert todos["subtitle_languages"] == "spa, eng"
    # Los campos de un solo valor NO se parten: un códec no es una lista.
    assert todos["video_codec"] == "x264"
    conn.close()


def test_rollup_all_is_none_for_a_movie(isolated_db, tmp_path):
    """Una película no resume nada: sus valores son los suyos."""
    from emuwarez_uploadrr.services.library import rollup_all_values
    conn = _open(isolated_db)
    assert rollup_all_values(conn, {"id": 1, "item_type": "movie"}) is None
    conn.close()


def test_the_sql_fragment_matches_the_python_rule():
    """Los tres filtros de library.py (tarjeta Contenido único, cuenta de
    episodios y Recomendaciones) tienen que aplicar la MISMA condición que
    can_pack_from_rollup. Se generan desde _PACK_ROLLUP_FIELDS justo para eso;
    este test comprueba que el generador no se queda corto."""
    from emuwarez_uploadrr.services.season_pack import pack_rollup_sql, _PACK_ROLLUP_FIELDS
    fragmento = pack_rollup_sql("li")
    for campo in _PACK_ROLLUP_FIELDS:
        assert f"li.{campo} IS NOT NULL" in fragmento, campo
    # Y ni un campo de más: los que ya no bloquean no pueden colarse.
    assert fragmento.count("IS NOT NULL") == len(_PACK_ROLLUP_FIELDS)
    assert "source" not in fragmento and "audio" not in fragmento


def test_the_dashboard_only_counts_seasons_that_could_really_be_packed(isolated_db, tmp_path):
    """La tarjeta Contenido único y Recomendaciones no pueden ofrecer una
    temporada que la subida va a rechazar."""
    from emuwarez_uploadrr.services.library import get_dashboard_summary
    from emuwarez_uploadrr.services.season_pack import can_pack_from_rollup
    conn = _open(isolated_db)
    conn.execute("INSERT INTO library_items (title, item_type, local_status, emu_in_catalog) "
                 "VALUES ('Serie', 'series', 'Disponible', 1)")
    series_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    casos = [
        ("Sube",              "1080p", "x264", 1),
        ("Resol. mezclada",   None,    "x264", 1),
        ("Códec mezclado",    "1080p", None,   1),
        ("Sin castellano",    "1080p", "x264", 0),
    ]
    for titulo, res, codec, spanish in casos:
        conn.execute(
            "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, "
            "resolution, video_codec, has_spanish_ok) VALUES (?, 'season', 'Disponible', 0, ?, ?, ?, ?)",
            (titulo, series_id, res, codec, spanish))
    conn.commit()

    # El SQL de la tarjeta y la regla de Python tienen que contar lo mismo.
    esperado = sum(1 for _t, res, codec, sp in casos
                   if can_pack_from_rollup({"resolution": res, "video_codec": codec, "has_spanish_ok": sp}))
    assert esperado == 1
    assert get_dashboard_summary(conn)["unique_seasons"] == esperado
    conn.close()


def test_rollup_all_returns_provider_codes_not_a_joined_string(isolated_db, tmp_path):
    """La ficha pinta un ProviderTag por proveedor, con su icono y su nombre
    completo, y para eso necesita los códigos sueltos. Pegarlos en "AMZN, NF"
    obligaba a enseñarlos en texto pelado, sin icono."""
    from emuwarez_uploadrr.services.library import rollup_all_values
    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    for i, ruta in enumerate(["/data/S01E01.AMZN.WEB-DL.mkv", "/data/S01E02.NF.WEB-DL.mkv"], start=1):
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=ruta,
                      quality="WEBDL-1080p", video_codec="x264", audio_codec="AC3",
                      audio_languages="spa", subtitle_languages="spa", source="WEB-DL")

    season = dict(conn.execute("SELECT * FROM library_items WHERE id = ?", (season_id,)).fetchone())
    todos = rollup_all_values(conn, season)

    codigos = todos.get("provider_codes")
    assert isinstance(codigos, list), todos
    assert set(codigos) == {"AMZN", "NF"}, codigos
    conn.close()


# --- La suma de audios del pack y el CUSTOM -------------------------------
# Se prueba _aggregate_pack_audio directamente, con la pista de cada idioma ya
# leída: montar MKVs reales con 3 pistas por capítulo para comprobar una regla
# de texto costaría minutos y no probaría nada más.

def _audios(monkeypatch, capitulos: list[dict]):
    from emuwarez_uploadrr.services import season_pack as sp
    monkeypatch.setattr(sp, "_episode_audio_by_language", lambda ep, conn: ep)
    return sp._aggregate_pack_audio([{"episode": c} for c in capitulos])


def test_an_audio_every_episode_has_is_named_without_custom(monkeypatch):
    """Si todos los capítulos traen la misma pista, nombrarla no miente."""
    texto, custom = _audios(monkeypatch, [
        {"ESP": "DD+ 5.1", "ING": "TrueHD Atmos 7.1"},
        {"ESP": "DD+ 5.1", "ING": "TrueHD Atmos 7.1"},
    ])
    assert custom is False
    # De mejor a peor, igual que dentro de un capítulo.
    assert texto == "ING TrueHD Atmos 7.1 ESP DD+ 5.1"


def test_an_audio_that_changes_between_episodes_lists_both_and_marks_custom(monkeypatch):
    """El caso de Arcane: 5 capítulos con Atmos en inglés y 5 sin él. Anunciar
    solo el Atmos mentiría sobre la mitad del pack, así que salen los dos y el
    nombre avisa con CUSTOM."""
    texto, custom = _audios(monkeypatch, [
        {"ING": "DD+ Atmos 5.1", "ESP": "DD+ 5.1", "JAP": "DD+ 5.1"},
        {"ING": "DD+ 5.1", "ESP": "DD+ 5.1", "JAP": "DD+ 5.1"},
    ])
    assert custom is True
    assert texto == "ING DD+ Atmos 5.1 ING-ESP-JAP DD+ 5.1"


def test_an_audio_missing_from_some_episodes_also_marks_custom(monkeypatch):
    """Un idioma que solo está en algunos capítulos es el mismo problema:
    falta en los demás."""
    texto, custom = _audios(monkeypatch, [
        {"ESP": "DD+ 5.1", "JAP": "FLAC 2.0"},
        {"ESP": "DD+ 5.1"},
    ])
    assert custom is True
    assert "JAP" in texto and "ESP" in texto


def test_the_same_codec_with_different_channels_is_a_different_track(monkeypatch):
    """5.1 en unos capítulos y 2.0 en otros no es la misma pista: quien baja el
    pack no recibe 5.1 en todos."""
    _texto, custom = _audios(monkeypatch, [
        {"ESP": "DD+ 5.1"}, {"ESP": "DD+ 2.0"},
    ])
    assert custom is True


def test_dual_survives_when_the_pack_really_is_dual(monkeypatch):
    """DUAL/MULTI siguen valiendo cuando NO hay CUSTOM: ahí sí es verdad que
    todos los capítulos traen esos idiomas."""
    texto, custom = _audios(monkeypatch, [
        {"ESP": "DD 5.1", "ING": "DD 5.1"}, {"ESP": "DD 5.1", "ING": "DD 5.1"},
    ])
    assert custom is False and texto == "DUAL DD 5.1"


def test_a_worse_track_of_a_language_every_episode_has_is_not_named(monkeypatch):
    """Dentro de un capítulo ya se elige la mejor pista de cada idioma (eso lo
    hace media_info_service). Si TODOS la traen, nombrar la mejor no miente y
    el pack no es CUSTOM."""
    texto, custom = _audios(monkeypatch, [
        {"ESP": "TrueHD 5.1"}, {"ESP": "TrueHD 5.1"},
    ])
    assert custom is False and texto == "ESP TrueHD 5.1"


# --- El progreso mientras se genera la nomenclatura ------------------------

def test_the_progress_names_the_episode_being_worked_on(isolated_db, tmp_path, monkeypatch):
    """La barra publicaba el progreso DESPUÉS de cada capítulo, así que durante
    todo el primero (el más lento: es el que paga la consulta del título a
    TMDb) se quedaba en "0 de N" y sin ningún nombre, y a partir de ahí
    enseñaba el capítulo YA TERMINADO mientras trabajaba en el siguiente."""
    from emuwarez_uploadrr.services import season_pack as sp

    conn = _open(isolated_db)
    _series_id, season_id = _seed_series_season(conn)
    folder = tmp_path / "One Piece" / "Season 1"
    folder.mkdir(parents=True)
    for i in (1, 2, 3):
        f = folder / f"S01E0{i}.mkv"
        f.write_bytes(b"video")
        _seed_episode(conn, season_id, number=i, title=f"One Piece S01E0{i}", path=str(f),
                      quality="WEBDL-1080p", video_codec="x264", audio_codec="AC3",
                      audio_languages="spa", subtitle_languages="spa", source="WEB-DL")

    visto = []
    real = sp.build_nomenclature_proposal

    def espia(item_id, **kw):
        # Lo que vería el asistente justo mientras se trabaja este capítulo.
        visto.append(dict(sp.get_season_plan_progress(season_id)))
        return real(item_id, **kw)

    monkeypatch.setattr(sp, "build_nomenclature_proposal", espia)
    sp.build_season_pack_plan(season_id, conn=conn)

    assert [p["done"] for p in visto] == [0, 1, 2], visto
    # Y el nombre es el del capítulo EN CURSO, no el del anterior.
    assert [p["current_title"] for p in visto] == [
        "One Piece S01E01", "One Piece S01E02", "One Piece S01E03",
    ], visto
    # Al acabar, la cuenta cuadra con el total.
    final = sp.get_season_plan_progress(season_id)
    assert final["done"] == final["total"] == 3
    conn.close()
