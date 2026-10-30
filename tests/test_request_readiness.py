"""Tests for the request readiness service (Phase 8B)."""
from __future__ import annotations

import pytest


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _insert_request(conn, **kwargs) -> int:
    defaults = {
        "emu_id": "emu-1",
        "title": "Test Movie",
        "category": "Pelicula",
        "requested_resolution": None,
        "requested_source": None,
        "emu_status": "open",
        "tmdb_id": None,
        "imdb_id": None,
    }
    defaults.update(kwargs)
    conn.execute(
        """
        INSERT INTO request_items
        (emu_id, title, category, requested_resolution, requested_source,
         emu_status, tmdb_id, imdb_id, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            defaults["emu_id"], defaults["title"], defaults["category"],
            defaults["requested_resolution"], defaults["requested_source"],
            defaults["emu_status"], defaults["tmdb_id"], defaults["imdb_id"],
        ),
    )
    conn.commit()
    return conn.execute("SELECT id FROM request_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _insert_library(conn, **kwargs) -> int:
    defaults = {
        "item_type": "movie",
        "title": "Test Movie",
        "local_status": "Disponible",
        "request_status": "Sin petición",
        "nomenclature_status": "N/A",
        "tmdb_id": None,
        "imdb_id": None,
        "file_exists": 1,
        "arr_queue_status": None,
        "arr_history_status": None,
        "arr_history_event_type": None,
        "arr_history_error": None,
        "prepared_path": None,
        "year": 2023,
        "resolution": None,
        "source": None,
    }
    defaults.update(kwargs)
    conn.execute(
        """
        INSERT INTO library_items
        (item_type, title, local_status, request_status, nomenclature_status,
         tmdb_id, imdb_id, file_exists, arr_queue_status, arr_history_status,
         arr_history_event_type, arr_history_error, prepared_path, year,
         resolution, source, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            defaults["item_type"], defaults["title"], defaults["local_status"],
            defaults["request_status"], defaults["nomenclature_status"],
            defaults["tmdb_id"], defaults["imdb_id"], defaults["file_exists"],
            defaults["arr_queue_status"], defaults["arr_history_status"],
            defaults["arr_history_event_type"], defaults["arr_history_error"],
            defaults["prepared_path"], defaults["year"],
            defaults["resolution"], defaults["source"],
        ),
    )
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


# ---------------------------------------------------------------------------
# score_request_candidate
# ---------------------------------------------------------------------------

def test_score_tmdb_match(db_conn):
    from emuwarez_uploadrr.services.request_readiness import score_request_candidate
    req = {"tmdb_id": "12345", "imdb_id": None, "title": "Movie A",
           "category": "Pelicula", "requested_resolution": None, "requested_source": None}
    lib = {"id": 1, "tmdb_id": "12345", "imdb_id": None, "title": "Movie A",
           "item_type": "movie", "year": 2023, "local_status": "Disponible",
           "file_exists": 1, "nomenclature_status": "N/A", "prepared_path": None,
           "resolution": None, "source": None,
           "arr_queue_status": None, "arr_history_status": None,
           "arr_history_event_type": None, "arr_history_error": None}
    result = score_request_candidate(req, lib)
    assert result["compatibility_score"] >= 40
    assert result["compatibility_status"] == "Compatible"


def test_score_no_match_low(db_conn):
    from emuwarez_uploadrr.services.request_readiness import score_request_candidate
    req = {"tmdb_id": "999", "imdb_id": None, "title": "Unrelated Film",
           "category": None, "requested_resolution": None, "requested_source": None}
    lib = {"id": 2, "tmdb_id": "888", "imdb_id": None, "title": "Completely Different",
           "item_type": "series", "year": 2000, "local_status": "Faltante",
           "file_exists": 0, "nomenclature_status": "N/A", "prepared_path": None,
           "resolution": None, "source": None,
           "arr_queue_status": None, "arr_history_status": None,
           "arr_history_event_type": None, "arr_history_error": None}
    result = score_request_candidate(req, lib)
    assert result["compatibility_score"] < 40


# ---------------------------------------------------------------------------
# evaluate_request_readiness — no candidates
# ---------------------------------------------------------------------------

def test_no_library_match_returns_no_local_match(db_conn):
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    req_id = _insert_request(db_conn, emu_id="emu-nm", title="Unknown Film", tmdb_id="zzzz")
    result = evaluate_request_readiness(req_id, db_conn)
    assert result["ok"] is True
    assert result["status"] == "no_local_match"
    assert result["recommended_action"] == "review_arr"


def test_partial_series_not_treated_as_no_local_match(db_conn):
    """A Parcial (some but not all episodes available) series row must be
    distinguished from a true no-match — it has a real local candidate,
    just an incomplete one."""
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    _insert_library(db_conn, title="Partial Show", tmdb_id="ps1",
                     item_type="series", local_status="Parcial", file_exists=None)
    req_id = _insert_request(db_conn, emu_id="emu-ps", title="Partial Show", category="Series", tmdb_id="ps1")
    result = evaluate_request_readiness(req_id, db_conn)
    assert result["status"] == "partially_available"
    assert result["status"] != "no_local_match"


# ---------------------------------------------------------------------------
# downloading / queued → wait_download
# ---------------------------------------------------------------------------

def test_downloading_candidate_wait_download(db_conn):
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    _insert_library(db_conn, title="Dwnl Movie", tmdb_id="dl1",
                    local_status="Faltante", file_exists=0,
                    arr_queue_status="downloading")
    req_id = _insert_request(db_conn, emu_id="emu-dl", title="Dwnl Movie", tmdb_id="dl1")
    result = evaluate_request_readiness(req_id, db_conn)
    assert result["status"] == "downloading"
    assert result["recommended_action"] == "wait_download"


# ---------------------------------------------------------------------------
# pending_import → review_arr / blocked
# ---------------------------------------------------------------------------

def test_pending_import_blocked(db_conn):
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    _insert_library(db_conn, title="Pending Movie", tmdb_id="pi1",
                    local_status="Faltante", file_exists=0,
                    arr_queue_status="pending_import")
    req_id = _insert_request(db_conn, emu_id="emu-pi", title="Pending Movie", tmdb_id="pi1")
    result = evaluate_request_readiness(req_id, db_conn)
    assert result["status"] == "pending_import"
    assert result["recommended_action"] == "review_arr"


# ---------------------------------------------------------------------------
# import_error → blocked
# ---------------------------------------------------------------------------

def test_import_error_blocked(db_conn):
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    _insert_library(db_conn, title="Error Movie", tmdb_id="err1",
                    local_status="Faltante", file_exists=0,
                    arr_queue_status="import_error")
    req_id = _insert_request(db_conn, emu_id="emu-err", title="Error Movie", tmdb_id="err1")
    result = evaluate_request_readiness(req_id, db_conn)
    assert result["status"] == "import_error"


# ---------------------------------------------------------------------------
# file missing → file_missing / blocked
# ---------------------------------------------------------------------------

def test_file_missing_blocked(db_conn):
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    _insert_library(db_conn, title="File Gone", tmdb_id="fg1",
                    local_status="Disponible", file_exists=0)
    req_id = _insert_request(db_conn, emu_id="emu-fg", title="File Gone", tmdb_id="fg1")
    result = evaluate_request_readiness(req_id, db_conn)
    assert result["status"] == "file_missing"


# ---------------------------------------------------------------------------
# needs_nomenclature
# ---------------------------------------------------------------------------

def test_needs_nomenclature(db_conn):
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    _insert_library(db_conn, title="Nom Movie", tmdb_id="nom1",
                    local_status="Disponible", file_exists=1,
                    nomenclature_status="No adaptada")
    req_id = _insert_request(db_conn, emu_id="emu-nom", title="Nom Movie", tmdb_id="nom1")
    result = evaluate_request_readiness(req_id, db_conn)
    assert result["status"] == "needs_nomenclature"
    assert result["recommended_action"] == "adapt_nomenclature"


# ---------------------------------------------------------------------------
# ready_to_upload — nomenclature correct + prepared_path
# ---------------------------------------------------------------------------

def test_ready_to_upload(db_conn):
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    _insert_library(db_conn, title="Upload Ready", tmdb_id="ur1",
                    local_status="Disponible", file_exists=1,
                    nomenclature_status="Correcta",
                    prepared_path="/data/prepared/upload_ready.mkv")
    req_id = _insert_request(db_conn, emu_id="emu-ur", title="Upload Ready", tmdb_id="ur1")
    result = evaluate_request_readiness(req_id, db_conn)
    assert result["status"] == "ready_to_upload"
    assert result["recommended_action"] == "upload"


# ---------------------------------------------------------------------------
# already_exists — ya está en eMuwarez y tu copia no aporta nada
# ---------------------------------------------------------------------------

def _en_emuwarez(conn, lib_id, aportes="[]"):
    conn.execute("UPDATE library_items SET emu_in_catalog = 1, emu_aportes = ? WHERE id = ?", (aportes, lib_id))
    conn.commit()


def test_ya_en_emuwarez_sin_aportes_es_duplicado(db_conn):
    """Se leía una columna que no existe (emu_existence_status), así que salía «Subir» igualmente."""
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    lib_id = _insert_library(db_conn, title="Ya Subida", tmdb_id="ys1", nomenclature_status="Correcta",
                             prepared_path="/data/prepared/ya_subida.mkv")
    _en_emuwarez(db_conn, lib_id)
    req_id = _insert_request(db_conn, emu_id="emu-ys", title="Ya Subida", tmdb_id="ys1")
    result = evaluate_request_readiness(req_id, db_conn)
    assert result["status"] == "already_exists"
    assert result["recommended_action"] == "ignore_already_exists"


def test_ya_en_emuwarez_pero_aporta_se_puede_subir(db_conn):
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    lib_id = _insert_library(db_conn, title="Mejor Copia", tmdb_id="mc1", nomenclature_status="Correcta",
                             prepared_path="/data/prepared/mejor_copia.mkv")
    _en_emuwarez(db_conn, lib_id, aportes='[{"dim": "resolucion", "detail": "2160p"}]')
    req_id = _insert_request(db_conn, emu_id="emu-mc", title="Mejor Copia", tmdb_id="mc1")
    assert evaluate_request_readiness(req_id, db_conn)["status"] == "ready_to_upload"


def test_se_mira_la_temporada_pedida_y_no_la_serie(db_conn):
    """La serie solo marca 1 si están todas sus temporadas; la que pide la petición puede estar aunque la serie no."""
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    serie = _insert_library(db_conn, item_type="series", title="Serie Mitad", tmdb_id="sm1",
                            nomenclature_status="Correcta", prepared_path="/data/prepared/serie_mitad")
    temporada = _insert_library(db_conn, item_type="season", title="Serie Mitad - Temporada 2", tmdb_id="sm1")
    db_conn.execute("UPDATE library_items SET parent_id = ?, season_number = 2 WHERE id = ?", (serie, temporada))
    db_conn.execute("UPDATE library_items SET emu_in_catalog = 2 WHERE id = ?", (serie,))  # parcial
    _en_emuwarez(db_conn, temporada)
    req_id = _insert_request(db_conn, emu_id="emu-sm", title="Serie Mitad", category="Series", tmdb_id="sm1")
    db_conn.execute("UPDATE request_items SET req_scope = 'season', req_season = 2 WHERE id = ?", (req_id,))
    db_conn.commit()
    assert evaluate_request_readiness(req_id, db_conn)["status"] == "already_exists"


def test_una_peticion_de_capitulo_se_puntua_con_el_capitulo(db_conn):
    """Los capítulos no son candidatos: un capítulo listo se puntuaba con el resumen «Parcial» de su serie."""
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    serie = _insert_library(db_conn, item_type="series", title="Serie Larga", tmdb_id="sl1",
                            local_status="Parcial", file_exists=None)
    temporada = _insert_library(db_conn, item_type="season", title="Serie Larga - Temporada 2", tmdb_id="sl1",
                                local_status="Parcial", file_exists=None)
    capitulo = _insert_library(db_conn, item_type="episode", title="Serie Larga S02E05", tmdb_id="sl1",
                               nomenclature_status="Correcta", prepared_path="/data/prepared/s02e05.mkv")
    db_conn.execute("UPDATE library_items SET parent_id = ?, season_number = 2 WHERE id = ?", (serie, temporada))
    db_conn.execute("UPDATE library_items SET parent_id = ?, season_number = 2, episode_number = 5 WHERE id = ?",
                    (temporada, capitulo))
    req_id = _insert_request(db_conn, emu_id="emu-sl", title="Serie Larga", category="Series", tmdb_id="sl1")
    db_conn.execute("UPDATE request_items SET req_scope = 'episode', req_season = 2, req_episode = 5 WHERE id = ?",
                    (req_id,))
    db_conn.commit()
    assert evaluate_request_readiness(req_id, db_conn)["status"] == "ready_to_upload"


def test_una_temporada_que_no_esta_no_se_prepara(db_conn):
    """Pedían la Temporada 3, que no está: salía «listo» por la serie o por la Temporada 1, que sí lo estaban."""
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    serie = _insert_library(db_conn, item_type="series", title="Serie Corta", tmdb_id="sc1",
                            nomenclature_status="Correcta", prepared_path="/data/prepared/serie_corta")
    temporada1 = _insert_library(db_conn, item_type="season", title="Serie Corta - Temporada 1", tmdb_id="sc1",
                                 nomenclature_status="Correcta", prepared_path="/data/prepared/serie_corta_t1")
    db_conn.execute("UPDATE library_items SET parent_id = ?, season_number = 1 WHERE id = ?", (serie, temporada1))
    req_id = _insert_request(db_conn, emu_id="emu-sc", title="Serie Corta", category="Series", tmdb_id="sc1")
    db_conn.execute("UPDATE request_items SET req_scope = 'season', req_season = 3 WHERE id = ?", (req_id,))
    db_conn.commit()
    assert evaluate_request_readiness(req_id, db_conn)["status"] == "no_local_match"


def test_con_dos_instancias_se_prepara_la_copia_que_atiende_la_peticion(db_conn):
    """Una copia de 1080p ya preparada ganaba a la 4K en una petición de 2160p y salía «lista para subir»."""
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    _insert_library(db_conn, title="Doble", tmdb_id="db1", resolution="1080p", source="WEB-DL",
                    nomenclature_status="Correcta", prepared_path="/data/prepared/doble_1080.mkv")
    cuatro_k = _insert_library(db_conn, title="Doble", tmdb_id="db1", resolution="2160p", source="WEB-DL",
                               nomenclature_status="Correcta")
    req_id = _insert_request(db_conn, emu_id="emu-db", title="Doble", tmdb_id="db1", requested_resolution="2160p")
    result = evaluate_request_readiness(req_id, db_conn)
    assert result["best_library_item_id"] == cuatro_k
    assert result["status"] == "preflight_needed"


def test_lo_que_pide_la_peticion_va_antes_que_la_puntuacion(db_conn):
    """La puntuación suma +10 si el año coincide con el de la petición: la copia de 1080p empataba con la 4K y,
    por estar preparada, ganaba en una petición de 2160p."""
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    _insert_library(db_conn, title="Doble", tmdb_id="db2", resolution="1080p", year=2021,
                    nomenclature_status="Correcta", prepared_path="/data/prepared/doble2_1080.mkv")
    cuatro_k = _insert_library(db_conn, title="Doble", tmdb_id="db2", resolution="2160p", year=2020,
                               nomenclature_status="Correcta")
    req_id = _insert_request(db_conn, emu_id="emu-db2", title="Doble", tmdb_id="db2", requested_resolution="2160p")
    db_conn.execute("UPDATE request_items SET created_at = '2021-05-01' WHERE id = ?", (req_id,))
    db_conn.commit()
    assert evaluate_request_readiness(req_id, db_conn)["best_library_item_id"] == cuatro_k


def test_el_id_gana_a_un_titulo_que_esta_listo(db_conn):
    """Ganaba el candidato «listo para subir» aunque solo casara por el título y fuera otra película."""
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    buena = _insert_library(db_conn, title="Titulo Comun", tmdb_id="tc1", local_status="Faltante", file_exists=0)
    _insert_library(db_conn, title="Titulo Comun", nomenclature_status="Correcta",
                    prepared_path="/data/prepared/otra.mkv")
    req_id = _insert_request(db_conn, emu_id="emu-tc", title="Titulo Comun", tmdb_id="tc1")
    assert evaluate_request_readiness(req_id, db_conn)["best_library_item_id"] == buena


# ---------------------------------------------------------------------------
# preflight_needed — nomenclature correct but no prepared_path
# ---------------------------------------------------------------------------

def test_preflight_needed(db_conn):
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    _insert_library(db_conn, title="Preflight Movie", tmdb_id="pf1",
                    local_status="Disponible", file_exists=1,
                    nomenclature_status="Correcta", prepared_path=None)
    req_id = _insert_request(db_conn, emu_id="emu-pf", title="Preflight Movie", tmdb_id="pf1")
    result = evaluate_request_readiness(req_id, db_conn)
    assert result["status"] == "preflight_needed"
    assert result["recommended_action"] == "run_preflight"


# ---------------------------------------------------------------------------
# Scoring determinism
# ---------------------------------------------------------------------------

def test_scoring_is_deterministic(db_conn):
    from emuwarez_uploadrr.services.request_readiness import score_request_candidate
    req = {"tmdb_id": "det1", "imdb_id": None, "title": "Det Movie",
           "category": "Pelicula", "requested_resolution": "1080p", "requested_source": "bluray",
           "emu_status": "open", "compatibility_status": None}
    lib = {"id": 10, "tmdb_id": "det1", "imdb_id": None, "title": "Det Movie",
           "item_type": "movie", "year": 2022, "local_status": "Disponible",
           "file_exists": 1, "nomenclature_status": "Correcta",
           "prepared_path": "/data/prep.mkv",
           "resolution": "1080p", "source": "bluray",
           "arr_queue_status": None, "arr_history_status": None,
           "arr_history_event_type": None, "arr_history_error": None}
    r1 = score_request_candidate(req, lib)
    r2 = score_request_candidate(req, lib)
    assert r1["readiness_status"] == r2["readiness_status"]
    assert r1["compatibility_score"] == r2["compatibility_score"]


# ---------------------------------------------------------------------------
# Blockers correlate with a blocked status
# ---------------------------------------------------------------------------

def test_blockers_force_blocked_bucket(db_conn):
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    _insert_library(db_conn, title="Blocked Movie", tmdb_id="blk1",
                    local_status="Disponible", file_exists=0,
                    nomenclature_status="Correcta")
    req_id = _insert_request(db_conn, emu_id="emu-blk", title="Blocked Movie", tmdb_id="blk1")
    result = evaluate_request_readiness(req_id, db_conn)
    assert result["status"] == "file_missing"
    assert len(result["blockers"]) > 0


# ---------------------------------------------------------------------------
# prioritized ordering
# ---------------------------------------------------------------------------

def test_prioritized_ordering(db_conn):
    from emuwarez_uploadrr.services.request_readiness import (
        evaluate_request_readiness, list_request_readiness,
    )
    # Request 1: ready_to_upload → most actionable
    _insert_library(db_conn, title="Movie High", tmdb_id="h1",
                    local_status="Disponible", file_exists=1,
                    nomenclature_status="Correcta",
                    prepared_path="/data/prep.mkv")
    rq1 = _insert_request(db_conn, emu_id="emu-h1", title="Movie High", tmdb_id="h1")
    # Request 2: no_local_match → least actionable
    rq2 = _insert_request(db_conn, emu_id="emu-l1", title="Unknown Film", tmdb_id="xyz999")
    evaluate_request_readiness(rq1, db_conn)
    evaluate_request_readiness(rq2, db_conn)

    # list_request_readiness() orders by real readiness status (most
    # actionable first) by default — no separate "prioritized" endpoint
    # needed since it always returns this order now.
    items = list_request_readiness(db_conn)
    status_order = {
        "ready_to_upload": 0, "preflight_needed": 1, "needs_nomenclature": 2,
        "downloading": 3, "pending_import": 4, "uploading": 5,
        "no_local_match": 6, "file_missing": 7, "import_error": 8,
        "already_exists": 9, "uploaded": 10,
    }
    ranks = [status_order.get(i["status"], 99) for i in items]
    assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------
# refresh_request_readiness bulk
# ---------------------------------------------------------------------------

def test_refresh_bulk(db_conn):
    from emuwarez_uploadrr.services.request_readiness import refresh_request_readiness
    for i in range(3):
        _insert_request(db_conn, emu_id=f"emu-bulk-{i}", title=f"Bulk {i}")
    result = refresh_request_readiness(db_conn)
    assert result["ok"] is True
    assert result["items_updated"] == 3
    assert result["errors"] == 0


# ---------------------------------------------------------------------------
# get_request_readiness returns stored data
# ---------------------------------------------------------------------------

def test_get_readiness_returns_stored(db_conn):
    from emuwarez_uploadrr.services.request_readiness import (
        evaluate_request_readiness, get_request_readiness,
    )
    req_id = _insert_request(db_conn, emu_id="emu-get", title="Get Test")
    evaluate_request_readiness(req_id, db_conn)
    data = get_request_readiness(req_id, db_conn)
    assert data is not None
    assert data["request_item_id"] == req_id
    assert "status" in data


# ---------------------------------------------------------------------------
# No API keys exposed in output
# ---------------------------------------------------------------------------

def test_no_api_keys_in_readiness(db_conn):
    from emuwarez_uploadrr.services.request_readiness import evaluate_request_readiness
    _insert_library(db_conn, title="Key Test", tmdb_id="kt1",
                    local_status="Disponible", file_exists=1)
    req_id = _insert_request(db_conn, emu_id="emu-kt", title="Key Test", tmdb_id="kt1")
    result = evaluate_request_readiness(req_id, db_conn)
    result_str = str(result)
    for forbidden in ("api_key", "apikey", "token", "password", "secret"):
        assert forbidden.lower() not in result_str.lower()
