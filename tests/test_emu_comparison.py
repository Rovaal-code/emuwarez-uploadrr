"""Tests for services/emu_catalog.get_item_comparison — the detail-card
"Comparación con eMuwarez" panel. Before this, an install that had NEVER
synced the eMuwarez catalog (an empty emu_catalog table) was indistinguishable
from one that HAD synced and genuinely found no match — both produced
`matches: []`, so every single item confidently showed "No está en eMuwarez ·
Contenido único" even though nothing had ever really been compared.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import set_state
from emuwarez_uploadrr.services.emu_catalog import (
    SYNC_COMPLETED_STATE_KEY,
    SYNC_STATE_KEY,
    get_item_comparison,
)


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _movie(conn, title, tmdb_id, **extra):
    fields = {
        "resolution": "1080p", "source": "WEB-DL", "video_codec": "H.264",
        "audio_languages": None, "size_bytes": 1_000_000_000,
    }
    fields.update(extra)
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status,
            tmdb_id, resolution, source, video_codec, audio_languages, size_bytes, updated_at)
           VALUES ('movie', ?, 'Disponible', 'Sin petición', 'N/A', ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (title, str(tmdb_id), fields["resolution"], fields["source"], fields["video_codec"],
         fields["audio_languages"], fields["size_bytes"]),
    )
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _catalog_movie(conn, tmdb_id, name="Movie 1080p WEB-DL"):
    conn.execute(
        """INSERT INTO emu_catalog
           (torrent_id, category, tmdb_id, resolution, source, codec, has_spanish, size, name)
           VALUES (?, 'Peliculas', ?, '1080p', 'WEB-DL', 'H.264', 1, 1000000000, ?)""",
        (f"t{tmdb_id}", str(tmdb_id), name),
    )
    conn.commit()


def test_never_synced_reports_unavailable_not_unique(db_conn):
    """The exact bug: an empty emu_catalog table (never synced) must NOT be
    read as "genuinely not in eMuwarez" — it must say so isn't comparable yet."""
    item_id = _movie(db_conn, "Some Movie", tmdb_id=555)
    result = get_item_comparison(db_conn, item_id)
    assert result["available"] is False
    assert "sincroniza" in result["message"].lower()
    assert result["matches"] == []


def test_synced_and_genuinely_not_in_catalog(db_conn):
    item_id = _movie(db_conn, "Unique Movie", tmdb_id=556)
    set_state(db_conn, SYNC_COMPLETED_STATE_KEY, "2026-01-01T00:00:00Z")
    db_conn.commit()
    result = get_item_comparison(db_conn, item_id)
    assert result["available"] is True
    assert result["in_catalog"] == 0
    assert result["matches"] == []


def test_synced_and_match_found(db_conn):
    item_id = _movie(db_conn, "Matched Movie", tmdb_id=557)
    _catalog_movie(db_conn, tmdb_id=557)
    set_state(db_conn, SYNC_COMPLETED_STATE_KEY, "2026-01-01T00:00:00Z")
    db_conn.commit()
    result = get_item_comparison(db_conn, item_id)
    assert result["available"] is True
    assert result["in_catalog"] == 1
    assert len(result["matches"]) == 1
    assert result["matches"][0]["name"] == "Movie 1080p WEB-DL"


def test_started_but_never_finished_reports_unavailable_not_unique(db_conn):
    """The exact real-world bug: a sync that STARTS (stamping the throttle
    marker immediately, before downloading anything) but then stalls/crashes
    mid-download must NOT be read as "synced" just because SYNC_STATE_KEY is
    set — that key only means "an attempt began", not "one finished". Every
    item must keep showing "not yet compared", not a false "contenido único"
    against a catalog table that's still empty."""
    item_id = _movie(db_conn, "Some Movie", tmdb_id=558)
    set_state(db_conn, SYNC_STATE_KEY, "2026-01-01T00:00:00Z")  # attempt started...
    db_conn.commit()                                             # ...but never finished
    result = get_item_comparison(db_conn, item_id)
    assert result["available"] is False
    assert "sincroniza" in result["message"].lower()
    assert result["matches"] == []


def _catalogo_con(conn, tmdb_id, resolucion, fuente, nombre, codec="H.264"):
    conn.execute(
        """INSERT INTO emu_catalog
           (torrent_id, category, tmdb_id, resolution, source, codec, has_spanish, size, name)
           VALUES (?, 'Peliculas', ?, ?, ?, ?, 1, 1000000000, ?)""",
        (nombre, str(tmdb_id), resolucion, fuente, codec, nombre),
    )
    conn.commit()


def test_cada_torrent_dice_si_el_tuyo_es_mejor_igual_o_peor(db_conn):
    """El asistente de subida enseña «mejor / igual / peor» por torrent, así que sale ya calculado."""
    item_id = _movie(db_conn, "Película", tmdb_id=560, resolution="1080p", source="WEB-DL")
    _catalogo_con(db_conn, 560, "720p", "HDTV", "Película 720p HDTV")
    _catalogo_con(db_conn, 560, "1080p", "WEB-DL", "Película 1080p WEB-DL")
    _catalogo_con(db_conn, 560, "2160p", "WEB-DL", "Película 2160p WEB-DL")
    set_state(db_conn, SYNC_COMPLETED_STATE_KEY, "2026-01-01T00:00:00Z")
    db_conn.commit()
    veredictos = {m["name"]: m["veredicto"] for m in get_item_comparison(db_conn, item_id)["matches"]}
    assert veredictos == {
        "Película 720p HDTV": "mejor", "Película 1080p WEB-DL": "igual", "Película 2160p WEB-DL": "peor",
    }


def test_a_igual_resolucion_decide_el_source(db_conn):
    item_id = _movie(db_conn, "Película", tmdb_id=561, resolution="1080p", source="BluRay")
    _catalogo_con(db_conn, 561, "1080p", "WEB-DL", "Película 1080p WEB-DL")
    set_state(db_conn, SYNC_COMPLETED_STATE_KEY, "2026-01-01T00:00:00Z")
    db_conn.commit()
    assert get_item_comparison(db_conn, item_id)["matches"][0]["veredicto"] == "mejor"


def test_sin_nada_que_comparar_no_hay_veredicto(db_conn):
    """Si la copia no dice resolución, source ni códec, no se inventa un «igual»."""
    item_id = _movie(db_conn, "Película", tmdb_id=562, resolution=None, source=None, video_codec=None)
    _catalogo_con(db_conn, 562, "1080p", "WEB-DL", "Película 1080p WEB-DL")
    set_state(db_conn, SYNC_COMPLETED_STATE_KEY, "2026-01-01T00:00:00Z")
    db_conn.commit()
    assert get_item_comparison(db_conn, item_id)["matches"][0]["veredicto"] is None


def test_la_resolucion_y_el_source_del_asistente_sustituyen_a_los_de_la_copia(db_conn):
    """Lo que se sube es lo que el asistente pone en el nombre, no lo que dijo Radarr."""
    item_id = _movie(db_conn, "Película", tmdb_id=563, resolution="720p", source="HDTV")
    _catalogo_con(db_conn, 563, "1080p", "WEB-DL", "Película 1080p WEB-DL")
    set_state(db_conn, SYNC_COMPLETED_STATE_KEY, "2026-01-01T00:00:00Z")
    db_conn.commit()
    assert get_item_comparison(db_conn, item_id)["matches"][0]["veredicto"] == "peor"
    resultado = get_item_comparison(db_conn, item_id, resolution="2160p", source="WEB-DL")
    assert resultado["matches"][0]["veredicto"] == "mejor"
    assert resultado["mine"]["resolution"] == "2160p"


def test_el_endpoint_pasa_resolucion_y_source_a_la_comparacion(client, auth_headers):
    from unittest.mock import patch
    with patch("emuwarez_uploadrr.services.emu_catalog.get_item_comparison",
               return_value={"available": False, "message": None, "matches": []}) as comparar:
        resp = client.get("/api/library/7/emu-comparison?resolution=2160p&source=WEB-DL", headers=auth_headers)
        assert resp.status_code == 200
        assert comparar.call_args.kwargs == {"resolution": "2160p", "source": "WEB-DL"}
        client.get("/api/library/7/emu-comparison", headers=auth_headers)
        assert comparar.call_args.kwargs == {"resolution": None, "source": None}


def test_un_capitulo_suelto_no_se_compara_con_el_pack_de_la_temporada(db_conn):
    ins = ("INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status, "
           "tvdb_id, tmdb_id, season_number, parent_id, resolution, source, video_codec, updated_at) "
           "VALUES (?, ?, 'Disponible', 'Sin petición', 'N/A', '8', '9', ?, ?, '1080p', 'WEB-DL', 'H.264', CURRENT_TIMESTAMP)")
    db_conn.execute(ins, ("series", "Serie", None, None))
    serie = db_conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]
    db_conn.execute(ins, ("season", "Serie - Temporada 1", 1, serie))
    temporada = db_conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]
    db_conn.execute("INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status, parent_id, "
                    "resolution, source, video_codec, size_bytes, updated_at) VALUES ('episode', 'Serie S01E01', 'Disponible', "
                    "'Sin petición', 'N/A', ?, '720p', 'WEB-DL', 'H.264', 1, CURRENT_TIMESTAMP)", (temporada,))
    for tid, nombre in (("p", "Serie S01 720p WEB-DL"), ("e", "Serie S01E01 720p WEB-DL")):
        db_conn.execute(
            "INSERT INTO emu_catalog (torrent_id, category, tvdb_id, tmdb_id, season_number, resolution, source, codec, "
            "has_spanish, size, name) VALUES (?, 'Series', '8', '9', 1, '720p', 'WEB-DL', 'H.264', 1, 1, ?)", (tid, nombre))
    set_state(db_conn, SYNC_COMPLETED_STATE_KEY, "2026-01-01T00:00:00Z")
    db_conn.commit()
    veredictos = {m["name"]: m["veredicto"] for m in get_item_comparison(db_conn, temporada)["matches"]}
    assert veredictos == {"Serie S01 720p WEB-DL": "igual", "Serie S01E01 720p WEB-DL": None}


@pytest.mark.parametrize("nombre,esperado", [
    ("Peli (2020) 1080p WEB-DL x265-Ryodan", "Ryodan"),
    ("Peli (2020) 1080p BluRay DUAL-eMu", "eMu"),
    ("Peli (2020) 1080p WEB-DL", None),           # el «DL» de WEB-DL no es un grupo
    ("Peli 2020 1080p BDRemux", None),
    ("Peli (2020) 1080p Blu-Ray", None),           # «Ray» es de Blu-Ray, no un grupo
    ("Peli (2020) 1080p Blu-Ray x264-eMu", "eMu"),
    ("Peli (2020) 1080p x264-", None),
    ("", None), (None, None),
])
def test_grupo_del_nombre(nombre, esperado):
    from emuwarez_uploadrr.services.emu_catalog import grupo_del_nombre
    assert grupo_del_nombre(nombre) == esperado


def test_la_comparacion_lleva_el_grupo_de_tu_copia_y_el_de_cada_torrent(db_conn):
    item_id = _movie(db_conn, "Grupo Movie", tmdb_id=560)
    db_conn.execute("UPDATE library_items SET release_group = 'Ryodan' WHERE id = ?", (item_id,))
    _catalog_movie(db_conn, tmdb_id=560, name="Grupo Movie (2020) 1080p WEB-DL x264-eMu")
    set_state(db_conn, SYNC_COMPLETED_STATE_KEY, "2026-01-01T00:00:00Z")
    db_conn.commit()
    result = get_item_comparison(db_conn, item_id)
    assert result["mine"]["release_groups"] == ["Ryodan"]
    assert [m["release_group"] for m in result["matches"]] == ["eMu"]
