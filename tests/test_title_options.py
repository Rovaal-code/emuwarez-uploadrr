"""Tests for the Título dropdown: the Spanish/original option pair, and the
title override reaching a season pack's real release name (a season has no
nomenclature proposal row of its own to carry it)."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.source_assistant import build_title_options


# --- The option pair ---------------------------------------------------------

def test_spanish_comes_first_and_is_the_default():
    options = build_title_options("Los Tudor", "The Tudors")
    assert [o["value"] for o in options] == ["Los Tudor", "The Tudors"]
    assert options[0]["kind"] == "spanish"


def test_identical_titles_collapse_to_one_option():
    """One Piece was never retitled in Spanish — offering the same string twice
    would suggest a choice that doesn't exist."""
    assert build_title_options("One Piece", "One Piece") == [
        {"value": "One Piece", "kind": "spanish", "label": "Español"}
    ]


@pytest.mark.parametrize("spanish,original,expected", [
    ("Solo español", None, ["Solo español"]),
    (None, "Only original", ["Only original"]),
    ("Con espacios  ", "  Con espacios", ["Con espacios"]),
    (None, None, []),
    ("", "", []),
])
def test_blank_and_duplicate_values_are_dropped(spanish, original, expected):
    assert [o["value"] for o in build_title_options(spanish, original)] == expected


# --- The override actually reaching the release name -------------------------

@pytest.fixture
def season(isolated_db, tmp_path):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    cur = conn.execute(
        """INSERT INTO library_items
           (item_type, title, original_title, year, local_status, request_status,
            nomenclature_status, updated_at)
           VALUES ('series', 'Los Tudor', 'The Tudors', 2007, 'Parcial', 'Sin petición',
                   'N/A', CURRENT_TIMESTAMP)"""
    )
    series_id = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO library_items
           (item_type, title, year, local_status, request_status, nomenclature_status,
            parent_id, season_number, updated_at)
           VALUES ('season', 'Los Tudor - Temporada 2', 2007, 'Disponible', 'Sin petición',
                   'N/A', ?, 2, CURRENT_TIMESTAMP)""",
        (series_id,),
    )
    season_id = cur.lastrowid
    folder = tmp_path / "Los Tudor" / "Season 2"
    folder.mkdir(parents=True)
    for n in (1, 2):
        f = folder / f"S02E0{n}.mkv"
        f.write_bytes(b"video")
        conn.execute(
            """INSERT INTO library_items
               (item_type, title, year, local_status, request_status, nomenclature_status,
                parent_id, season_number, episode_number, path, quality, video_codec,
                audio_codec, audio_languages, subtitle_languages, source, updated_at)
               VALUES ('episode', ?, 2007, 'Disponible', 'Sin petición', 'No adaptada',
                       ?, 2, ?, ?, 'WEBDL-1080p', 'x264', 'AC3', 'spa / eng', 'spa',
                       'WEB-DL', CURRENT_TIMESTAMP)""",
            (f"Los Tudor S02E0{n}", season_id, n, str(f)),
        )
    conn.commit()
    return conn, season_id


def test_pack_preview_offers_both_titles(season):
    from emuwarez_uploadrr.services.season_pack import build_season_pack_plan
    conn, season_id = season
    plan = build_season_pack_plan(season_id, conn=conn)
    assert [o["value"] for o in plan["title_options"]] == ["Los Tudor", "The Tudors"]


def test_pack_defaults_to_the_spanish_title(season):
    from emuwarez_uploadrr.services.season_pack import build_season_pack_plan
    conn, season_id = season
    plan = build_season_pack_plan(season_id, conn=conn)
    assert plan["series_title"] == "Los Tudor"
    assert plan["season_pack_title"].startswith("Los Tudor S02")


def test_title_override_changes_the_release_name(season):
    from emuwarez_uploadrr.services.season_pack import build_season_pack_plan
    conn, season_id = season
    plan = build_season_pack_plan(season_id, conn=conn, title_override="The Tudors")
    assert plan["series_title"] == "The Tudors"
    assert plan["season_pack_title"].startswith("The Tudors S02")


def test_blank_title_override_falls_back_to_the_stored_title(season):
    """An empty string must not produce a pack literally named " S02 …"."""
    from emuwarez_uploadrr.services.season_pack import build_season_pack_plan
    conn, season_id = season
    plan = build_season_pack_plan(season_id, conn=conn, title_override="   ")
    assert plan["season_pack_title"].startswith("Los Tudor S02")


def test_override_reaches_the_renamed_files(season, monkeypatch):
    """The whole point of routing it through season_overrides: the files on
    disk must end up named after the chosen title, not just the preview."""
    from emuwarez_uploadrr.services.season_pack import apply_season_pack
    conn, season_id = season
    result = apply_season_pack(season_id, conn=conn, title_override="The Tudors")
    assert result["status"] != "blocked", result.get("errors")
    import os
    # Filenames are dotted, the pack title is spaced — both must carry the pick.
    renamed = [os.path.basename(e["destination_path"]) for e in result["episodes"]]
    assert renamed and all(n.startswith("The.Tudors.S02E0") for n in renamed), renamed
    assert result["season_pack_title"].startswith("The Tudors S02")


def test_pack_title_and_filenames_agree_on_the_chosen_title(season):
    """The bug this guards: the override used to reach only the pack title, so
    the torrent read "The Tudors S02" while the files inside it stayed
    "Los.Tudor.S02E01"."""
    from emuwarez_uploadrr.services.season_pack import build_season_pack_plan
    conn, season_id = season
    plan = build_season_pack_plan(season_id, conn=conn, title_override="The Tudors")
    assert plan["season_pack_title"].startswith("The Tudors S02")
    for ep in plan["episodes"]:
        assert ep["proposed_filename"].startswith("The.Tudors.S02E0"), ep["proposed_filename"]


def test_single_item_fields_offer_both_titles(isolated_db, tmp_path, monkeypatch):
    """A movie/episode gets its options from build_editable_nomenclature_fields
    (the season path has its own, cheaper builder)."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services import source_assistant

    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"video")
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, original_title, year, local_status, request_status,
            nomenclature_status, path, quality, updated_at)
           VALUES ('movie', 'La Gran Evasión', 'The Great Escape', 1963, 'Disponible',
                   'Sin petición', 'No adaptada', ?, 'Bluray-1080p', CURRENT_TIMESTAMP)""",
        (str(f),),
    )
    conn.commit()
    item_id = conn.execute("SELECT id FROM library_items").fetchone()["id"]

    result = source_assistant.build_editable_nomenclature_fields(item_id, conn=conn)
    assert [o["value"] for o in result["title_options"]] == ["La Gran Evasión", "The Great Escape"]
    # The default stays the Spanish one.
    assert result["fields"]["title"] == "La Gran Evasión"
