"""Tests for the "Español" column: the Castilian-audio predicate, the
season/series rollups, and the backend-side filter + size sort that go with it.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.emu_format import has_castellano_audio


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _insert(conn, title, **kwargs):
    """Insert one library row and return its id."""
    defaults = {
        "item_type": "movie", "local_status": "Disponible",
        "request_status": "Sin petición", "nomenclature_status": "N/A",
        "instance_type": "radarr", "audio_languages": None,
        "parent_id": None, "size_bytes": None,
    }
    defaults.update(kwargs)
    cur = conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status,
            instance_type, audio_languages, parent_id, size_bytes, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
        (defaults["item_type"], title, defaults["local_status"],
         defaults["request_status"], defaults["nomenclature_status"],
         defaults["instance_type"], defaults["audio_languages"],
         defaults["parent_id"], defaults["size_bytes"]),
    )
    conn.commit()
    return int(cur.lastrowid)


def _value(conn, item_id):
    return conn.execute(
        "SELECT has_spanish_audio FROM library_items WHERE id = ?", (item_id,)
    ).fetchone()["has_spanish_audio"]


# --- The predicate -----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("spa", 1),
    ("spa / eng", 1),
    ("eng/jpn/spa", 1),
    ("castellano", 1),
    ("es-ES", 1),
    ("eng", 0),
    ("jpn / eng", 0),
    (None, None),
    ("", None),
    ("   ", None),
])
def test_has_castellano_audio(raw, expected):
    assert has_castellano_audio(raw) == expected


@pytest.mark.parametrize("raw", ["es-419", "latino", "spa-lat"])
def test_latin_american_spanish_is_not_castellano(raw):
    """The tracker wants Castilian, so LAT alone must answer No, not Sí."""
    assert has_castellano_audio(raw) == 0


def test_latin_plus_castellano_is_yes():
    assert has_castellano_audio("es-419 / spa") == 1


# --- Rollups -----------------------------------------------------------------

def test_movie_reads_its_own_audio(db_conn):
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    yes = _insert(db_conn, "Con castellano", audio_languages="spa / eng")
    no = _insert(db_conn, "Sin castellano", audio_languages="eng")
    unknown = _insert(db_conn, "Sin MediaInfo")
    recompute_spanish_audio(db_conn)
    assert _value(db_conn, yes) == 1
    assert _value(db_conn, no) == 0
    assert _value(db_conn, unknown) is None


def _series_with(db_conn, episodes):
    """Build series → season → episodes. `episodes` is a list of
    (audio_languages, local_status). Returns (series_id, season_id)."""
    series = _insert(db_conn, "Serie", item_type="series", instance_type="sonarr")
    season = _insert(db_conn, "Temporada 1", item_type="season", parent_id=series,
                     instance_type="sonarr")
    for i, (langs, status) in enumerate(episodes, start=1):
        _insert(db_conn, f"Episodio {i}", item_type="episode", parent_id=season,
                audio_languages=langs, local_status=status, instance_type="sonarr")
    return series, season


def test_season_yes_only_when_every_held_episode_is_yes(db_conn):
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    series, season = _series_with(db_conn, [("spa", "Disponible"), ("spa / eng", "Disponible")])
    recompute_spanish_audio(db_conn)
    assert _value(db_conn, season) == 1
    assert _value(db_conn, series) == 1


def test_one_episode_without_castellano_makes_the_whole_season_no(db_conn):
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    series, season = _series_with(db_conn, [("spa", "Disponible"), ("eng", "Disponible")])
    recompute_spanish_audio(db_conn)
    assert _value(db_conn, season) == 0
    assert _value(db_conn, series) == 0


def test_a_confirmed_no_beats_a_pending_unknown(db_conn):
    """A single known "no" already breaks "all yes", so unknowns alongside it
    must not soften the verdict back to unknown."""
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    _, season = _series_with(db_conn, [("eng", "Disponible"), (None, "Disponible")])
    recompute_spanish_audio(db_conn)
    assert _value(db_conn, season) == 0


def test_an_unknown_episode_blocks_a_yes(db_conn):
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    _, season = _series_with(db_conn, [("spa", "Disponible"), (None, "Disponible")])
    recompute_spanish_audio(db_conn)
    assert _value(db_conn, season) is None


def test_missing_episodes_do_not_count(db_conn):
    """Only files you actually hold matter — an episode you haven't downloaded
    can't be judged, and shouldn't drag the season to unknown."""
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    _, season = _series_with(db_conn, [("spa", "Disponible"), (None, "Faltante")])
    recompute_spanish_audio(db_conn)
    assert _value(db_conn, season) == 1


def test_uploaded_and_uploading_count_as_held(db_conn):
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    _, season = _series_with(db_conn, [("spa", "Subido"), ("eng", "Subiendo")])
    recompute_spanish_audio(db_conn)
    assert _value(db_conn, season) == 0


def test_season_with_nothing_held_is_unknown_not_yes(db_conn):
    """Vacuous truth would render a season you own nothing of as "Sí"."""
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    _, season = _series_with(db_conn, [(None, "Faltante")])
    recompute_spanish_audio(db_conn)
    assert _value(db_conn, season) is None


def test_series_is_no_when_any_season_is_no(db_conn):
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    series = _insert(db_conn, "Serie", item_type="series", instance_type="sonarr")
    s1 = _insert(db_conn, "T1", item_type="season", parent_id=series, instance_type="sonarr")
    s2 = _insert(db_conn, "T2", item_type="season", parent_id=series, instance_type="sonarr")
    _insert(db_conn, "E1", item_type="episode", parent_id=s1, audio_languages="spa", instance_type="sonarr")
    _insert(db_conn, "E2", item_type="episode", parent_id=s2, audio_languages="eng", instance_type="sonarr")
    recompute_spanish_audio(db_conn)
    assert _value(db_conn, s1) == 1
    assert _value(db_conn, s2) == 0
    assert _value(db_conn, series) == 0


def test_a_season_with_nothing_held_does_not_sink_the_series(db_conn):
    """An empty season is skipped, not propagated as unknown — otherwise every
    series with an unaired season would read "—"."""
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    series = _insert(db_conn, "Serie", item_type="series", instance_type="sonarr")
    s1 = _insert(db_conn, "T1", item_type="season", parent_id=series, instance_type="sonarr")
    s2 = _insert(db_conn, "T2", item_type="season", parent_id=series, instance_type="sonarr")
    _insert(db_conn, "E1", item_type="episode", parent_id=s1, audio_languages="spa", instance_type="sonarr")
    _insert(db_conn, "E2", item_type="episode", parent_id=s2, local_status="Faltante", instance_type="sonarr")
    recompute_spanish_audio(db_conn)
    assert _value(db_conn, s2) is None
    assert _value(db_conn, series) == 1


def test_recompute_clears_a_stale_value(db_conn):
    """Re-running after an episode's audio changed must overwrite the rollup,
    not leave the previous verdict behind."""
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    _, season = _series_with(db_conn, [("spa", "Disponible")])
    recompute_spanish_audio(db_conn)
    assert _value(db_conn, season) == 1
    db_conn.execute("UPDATE library_items SET audio_languages = 'eng' WHERE item_type = 'episode'")
    db_conn.commit()
    recompute_spanish_audio(db_conn)
    assert _value(db_conn, season) == 0


# --- Filter + sort -----------------------------------------------------------

def test_filter_by_spanish_state(db_conn):
    from emuwarez_uploadrr.services.library import list_library, count_library, recompute_spanish_audio
    _insert(db_conn, "Con", audio_languages="spa")
    _insert(db_conn, "Sin", audio_languages="eng")
    _insert(db_conn, "Ni idea")
    recompute_spanish_audio(db_conn)

    for state, expected in [("yes", ["Con"]), ("no", ["Sin"]), ("unknown", ["Ni idea"])]:
        items = list_library(db_conn, spanish=state)
        assert [i["title"] for i in items] == expected, state
        # count_library must apply the very same WHERE, or `total` lies.
        assert count_library(db_conn, spanish=state) == len(expected), state


def test_unrecognized_spanish_value_does_not_filter(db_conn):
    from emuwarez_uploadrr.services.library import list_library
    _insert(db_conn, "A", audio_languages="spa")
    _insert(db_conn, "B", audio_languages="eng")
    assert len(list_library(db_conn, spanish="cualquiera")) == 2


def test_sort_by_size(db_conn):
    from emuwarez_uploadrr.services.library import list_library
    _insert(db_conn, "Pequeña", size_bytes=100)
    _insert(db_conn, "Grande", size_bytes=900)
    _insert(db_conn, "Mediana", size_bytes=500)
    _insert(db_conn, "Sin tamaño")

    desc = [i["title"] for i in list_library(db_conn, sort="size_desc")]
    asc = [i["title"] for i in list_library(db_conn, sort="size_asc")]
    assert desc[:3] == ["Grande", "Mediana", "Pequeña"]
    assert asc[:3] == ["Pequeña", "Mediana", "Grande"]
    # Rows with no size sort last in BOTH directions, never at the top of the
    # ascending one.
    assert desc[-1] == "Sin tamaño"
    assert asc[-1] == "Sin tamaño"


# --- API surface -------------------------------------------------------------

def test_endpoint_exposes_and_filters_the_column(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    _insert(conn, "Con castellano", audio_languages="spa")
    _insert(conn, "Sin castellano", audio_languages="eng")
    recompute_spanish_audio(conn)

    body = client.get("/api/library", headers=auth_headers).json()
    by_title = {i["title"]: i for i in body["items"]}
    assert by_title["Con castellano"]["has_spanish_audio"] == 1
    assert by_title["Sin castellano"]["has_spanish_audio"] == 0

    filtered = client.get("/api/library?spanish=no", headers=auth_headers).json()
    assert [i["title"] for i in filtered["items"]] == ["Sin castellano"]
    assert filtered["total"] == 1


def test_endpoint_rejects_an_invalid_spanish_value(client, auth_headers):
    assert client.get("/api/library?spanish=puede", headers=auth_headers).status_code == 422


def test_filter_options_only_offer_states_that_occur(client, auth_headers, isolated_db):
    from emuwarez_uploadrr.database import connect
    from emuwarez_uploadrr.services.library import recompute_spanish_audio
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    _insert(conn, "Con castellano", audio_languages="spa")
    recompute_spanish_audio(conn)
    options = client.get("/api/library/filter-options", headers=auth_headers).json()
    assert options["spanish_states"] == ["yes"]
