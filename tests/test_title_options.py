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


def test_override_reaches_the_file_names(season, monkeypatch):
    """The whole point of routing it through season_overrides: the files in the
    uploads folder must end up named after the chosen title, not just the preview."""
    from emuwarez_uploadrr.services.season_pack import build_season_pack_plan
    conn, season_id = season
    result = build_season_pack_plan(season_id, conn=conn, title_override="The Tudors")
    assert result["status"] != "blocked", result.get("errors")
    # Filenames are dotted, the pack title is spaced — both must carry the pick.
    nombres = [e["nombre"] for e in result["episodes"]]
    assert nombres and all(n.startswith("The.Tudors.S02E0") for n in nombres), nombres
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


@pytest.mark.usefixtures("ficheros_de_mentira")
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


# --- The original title for a SERIES has to come from TMDb -------------------

def test_series_original_title_comes_from_tmdb(isolated_db, monkeypatch):
    """The bug this guards: Sonarr's series payload has no originalTitle field,
    so library_items.original_title is always NULL for a series and the Título
    dropdown collapsed to a single, unusable option."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services import tmdb_titles
    from emuwarez_uploadrr.services.tmdb_titles import resolve_english_title

    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    from emuwarez_uploadrr.services.settings import set_setting
    set_setting(conn, "tmdb.api_key", "fake-key")
    conn.commit()

    calls = []
    monkeypatch.setattr(tmdb_titles.tmdb, "get_tv_title",
                        lambda tid, **kw: calls.append(tid) or "The Tudors")

    # Stored original is NULL (the real Sonarr situation) → TMDb fills it.
    assert resolve_english_title(conn, "tv", "1399", None) == "The Tudors"
    # And the answer is cached, so a whole multi-season batch hits TMDb once.
    assert resolve_english_title(conn, "tv", "1399", None) == "The Tudors"
    assert calls == [1399]


def test_original_title_falls_back_when_tmdb_cannot_answer(isolated_db, monkeypatch):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services import tmdb_titles
    from emuwarez_uploadrr.services.tmdb_titles import resolve_english_title

    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    from emuwarez_uploadrr.services.settings import set_setting
    set_setting(conn, "tmdb.api_key", "fake-key")
    conn.commit()

    def boom(*a, **k):
        raise RuntimeError("TMDb caído")
    monkeypatch.setattr(tmdb_titles.tmdb, "get_tv_title", boom)
    # Keeps whatever the library row had, and does NOT cache the miss.
    assert resolve_english_title(conn, "tv", "1399", "Guardado") == "Guardado"
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM tmdb_title_cache WHERE language = 'original'"
    ).fetchone()["n"] == 0


def test_no_tmdb_key_keeps_the_stored_original(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.tmdb_titles import resolve_english_title
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    assert resolve_english_title(conn, "movie", "550", "Fight Club") == "Fight Club"


def test_season_pack_offers_the_tmdb_original_when_sonarr_has_none(season, monkeypatch):
    """End to end: a series row with original_title NULL still gets two real
    options in the pack's Título dropdown."""
    from emuwarez_uploadrr.services import tmdb_titles
    from emuwarez_uploadrr.services.season_pack import build_season_pack_plan
    from emuwarez_uploadrr.services.settings import set_setting
    conn, season_id = season
    conn.execute("UPDATE library_items SET original_title = NULL WHERE item_type = 'series'")
    conn.execute("UPDATE library_items SET tmdb_id = '1399' WHERE item_type = 'series'")
    set_setting(conn, "tmdb.api_key", "fake-key")
    conn.commit()
    monkeypatch.setattr(tmdb_titles.tmdb, "get_tv_title", lambda tid, **kw: "The Tudors")

    plan = build_season_pack_plan(season_id, conn=conn)
    assert [o["value"] for o in plan["title_options"]] == ["Los Tudor", "The Tudors"]


def test_second_option_is_the_english_title_not_the_original_language_one(isolated_db, monkeypatch):
    """The dropdown's second option must be the ENGLISH title. TMDb's
    `original_name` would be the original-LANGUAGE one, which for an anime is
    Japanese (ワンピース) and is never what an eMuwarez release name wants."""
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services import tmdb_titles
    from emuwarez_uploadrr.services.tmdb_titles import resolve_english_title
    from emuwarez_uploadrr.services.settings import set_setting

    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    set_setting(conn, "tmdb.api_key", "fake-key")
    conn.commit()

    asked = {}

    def fake_get_tv_title(tid, *, language="es-ES", **kw):
        asked["language"] = language
        # What TMDb would answer for One Piece at each language.
        return {"en-US": "One Piece", "es-ES": "One Piece"}.get(language)

    monkeypatch.setattr(tmdb_titles.tmdb, "get_tv_title", fake_get_tv_title)
    assert resolve_english_title(conn, "tv", "37854", None) == "One Piece"
    assert asked["language"] == "en-US"


def _comando_de_la_cola(season, tmp_path, season_overrides=None):
    """El uploadrr_command_json que deja la cola para el pack: lo único que lee la ejecución."""
    import json

    from emuwarez_uploadrr.services import upload_queue as uq
    from emuwarez_uploadrr.services.settings import set_setting

    conn, season_id = season
    (tmp_path / "U").mkdir()
    (tmp_path / "U" / "upload.py").write_text("")
    for k, v in (("emu.api_key", "a"), ("tmdb.api_key", "b"), ("uploadrr.path", str(tmp_path / "U"))):
        set_setting(conn, k, v)
    job_id = conn.execute(
        "INSERT INTO upload_jobs (library_item_id, status, stage, title, path, created_at, updated_at)"
        " VALUES (?, 'preparing', 'verificacion_presubida', 'X', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (season_id,),
    ).lastrowid
    conn.commit()

    assert uq._populate_ready(job_id, season_id, conn, season_overrides=season_overrides)

    return json.loads(conn.execute(
        "SELECT uploadrr_command_json FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()[0])


def test_el_titulo_elegido_llega_al_comando_de_uploadrr(season, tmp_path):
    """La cola rehacía el plan del pack sin lo editado en el asistente, así que
    el nombre del torrent (-mt) salía siempre con el título por defecto."""
    comando = _comando_de_la_cola(season, tmp_path, season_overrides={"title": "The Tudors"})
    assert comando["title"].startswith("The Tudors S02")


def test_el_formato_y_la_temporada_del_pack_llegan_al_comando_de_uploadrr(season, tmp_path):
    args = _comando_de_la_cola(season, tmp_path)["command_args"]
    assert args[args.index("-season") + 1] == "S02"
    assert args[args.index("-t") + 1] == "webdl"
