"""La sincronización borra las peticiones que eMuwarez ya no lista, pero solo tras un recorrido completo.

Nada aquí habla con el tracker: `emu_fetch_all_pages` se sustituye por lo que devolvería."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import requests as reqs
from emuwarez_uploadrr.services.settings import set_setting


def _fila(id_, nombre=None, tmdb=0):
    return {"id": id_, "name": nombre or f"Petición {id_}", "category_id": 1, "tmdb": tmdb,
            "status": "unfilled", "bounty": "10.00", "created": "2025-01-01T00:00:00+00:00"}


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    set_setting(conn, "emu.api_key", "clave")
    return conn


@pytest.fixture
def sincroniza(db_conn, monkeypatch):
    """sincroniza(filas, total) hace una sincronización que recorrió `filas` y dice haber visto `total`."""
    def hacer(filas, total):
        monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", lambda *a, **kw: (filas, total))
        return reqs.sync_emu_requests(db_conn, force=True)
    return hacer


def _emu_ids(conn):
    return sorted(r[0] for r in conn.execute("SELECT emu_id FROM request_items"))


def test_la_sincronizacion_deja_calculada_la_preparacion_de_cada_peticion(db_conn, sincroniza):
    """Nada la calculaba: abrir una petición real pedía /readiness y daba 404."""
    from emuwarez_uploadrr.services.request_readiness import get_request_readiness
    sincroniza([_fila(1), _fila(2)], 2)
    ids = [r[0] for r in db_conn.execute("SELECT id FROM request_items")]
    assert len(ids) == 2 and all(get_request_readiness(i, db_conn) for i in ids)


def test_un_recorrido_completo_borra_lo_que_ya_no_esta_con_lo_que_colgaba(db_conn, sincroniza):
    peli = db_conn.execute(
        "INSERT INTO library_items (item_type, title, year, tmdb_id, local_status)"
        " VALUES ('movie', 'Matrix', 1999, '603', 'Disponible')").lastrowid
    db_conn.execute(
        "INSERT INTO library_items (item_type, title, year, tmdb_id, local_status)"
        " VALUES ('movie', 'Dune', 2021, '438631', 'Disponible')")
    db_conn.commit()
    sincroniza([_fila(1, "Matrix", tmdb=603), _fila(2, "Dune", tmdb=438631), _fila(3, "Otra")], 3)
    ids = {r["emu_id"]: r["id"] for r in db_conn.execute("SELECT id, emu_id FROM request_items")}
    cuelgan = ids["1"]
    # La preparación la deja calculada la propia sincronización.
    assert db_conn.execute("SELECT COUNT(*) FROM request_readiness WHERE request_item_id = ?",
                           (cuelgan,)).fetchone()[0] == 1
    db_conn.execute("INSERT INTO request_candidates (request_item_id, library_item_id, candidate_rank, match_status)"
                    " VALUES (?, ?, 1, 'Compatible')", (cuelgan, peli))
    db_conn.execute("INSERT INTO operational_queue_items (queue_key, item_type, entity_type, request_item_id)"
                    " VALUES ('request:1:readiness', 'request_readiness', 'request', ?)", (cuelgan,))
    db_conn.commit()
    assert db_conn.execute("SELECT request_status FROM library_items WHERE id = ?", (peli,)).fetchone()[0] == "Compatible"

    # Matrix ya no está abierta (alguien la llenó); Dune y Otra siguen.
    resultado = sincroniza([_fila(2, "Dune", tmdb=438631), _fila(3, "Otra")], 2)

    assert resultado["removed"] == 1
    assert _emu_ids(db_conn) == ["2", "3"]
    for tabla in ("request_matches", "request_readiness", "request_candidates", "operational_queue_items"):
        assert db_conn.execute(f"SELECT COUNT(*) FROM {tabla} WHERE request_item_id = ?", (cuelgan,)).fetchone()[0] == 0, tabla
    # La biblioteca recalcula: Matrix deja de llevar una petición que ya no existe, Dune sigue cruzada.
    estados = {r["title"]: (r["request_status"], r["request_id"]) for r in db_conn.execute(
        "SELECT title, request_status, request_id FROM library_items")}
    assert estados["Matrix"] == ("Sin petición", None)
    assert estados["Dune"] == ("Compatible", ids["2"])


def test_la_sincronizacion_anota_cuando_vio_cada_peticion(db_conn, sincroniza):
    sincroniza([_fila(1)], 1)
    vista = db_conn.execute("SELECT last_seen_at FROM request_items").fetchone()[0]
    assert vista
    sincroniza([_fila(1)], 1)
    assert db_conn.execute("SELECT last_seen_at FROM request_items").fetchone()[0] > vista


@pytest.mark.parametrize("filas, total, motivo", [
    ([_fila(1)], 3, "faltan filas respecto al total"),
    ([_fila(1), _fila(1), _fila(2)], 3, "una fila repetida no cuenta dos veces"),
    ([_fila(1), _fila(1), _fila(2), _fila(3)], 3, "una fila repetida: las páginas se movieron aunque los ids cuadren"),
    ([_fila(1), {"name": "sin id"}, _fila(2)], 3, "una fila sin id no cuenta"),
    ([_fila(1), _fila(2), _fila(3)], None, "eMuwarez no dio el total o cambió a mitad"),
    ([_fila(1), _fila(2), _fila(3)], 2, "sobran filas respecto al total"),
])
def test_un_recorrido_que_no_cuadra_con_el_total_no_borra_nada(db_conn, sincroniza, filas, total, motivo):
    sincroniza([_fila(1), _fila(2), _fila(3), _fila(4)], 4)

    resultado = sincroniza(filas, total)

    assert resultado["status"] == "ok" and resultado["removed"] == 0, motivo
    assert _emu_ids(db_conn) == ["1", "2", "3", "4"], motivo


def test_un_recorrido_que_falla_no_borra_nada(db_conn, sincroniza, monkeypatch):
    sincroniza([_fila(1), _fila(2)], 2)

    def roto(*a, **kw):
        raise IntegrationError("eMuwarez ha limitado las peticiones; prueba en unos minutos", status=429)
    monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", roto)
    with pytest.raises(IntegrationError):
        reqs.sync_emu_requests(db_conn, force=True)

    assert _emu_ids(db_conn) == ["1", "2"]


def test_sin_peticiones_abiertas_un_recorrido_que_cuadra_con_cero_las_retira_todas(db_conn, sincroniza):
    sincroniza([_fila(1), _fila(2)], 2)
    assert sincroniza([], 0)["removed"] == 2
    assert _emu_ids(db_conn) == []


def test_lo_que_no_vino_de_la_sincronizacion_tambien_se_borra(db_conn, sincroniza):
    """Una fila sin last_seen_at (insertada a mano, o de antes de existir la columna) no se vio en este recorrido."""
    db_conn.execute("INSERT INTO request_items (emu_id, title) VALUES ('vieja', 'Vieja')")
    db_conn.commit()
    sincroniza([_fila(1)], 1)
    assert _emu_ids(db_conn) == ["1"]
