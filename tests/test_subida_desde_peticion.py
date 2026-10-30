"""Una subida lanzada desde una petición guarda cuál era (título y enlace).

La fila de Peticiones se borra cuando la petición deja de estar abierta en
eMuwarez, y el historial de Subidas tiene que seguir diciendo qué petición
cubrió cada subida: por eso se copia al encolar, no se lee en vivo.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from emuwarez_uploadrr.database import connect, init_db, set_state
from emuwarez_uploadrr.services import upload_queue as uq

TITULO = "Dune: Parte Dos"
ENLACE = "https://emu-warez.com/requests/77"


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    yield conn
    conn.close()


def _peli(conn, tmp_path) -> int:
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 10)
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status, path, size_bytes, updated_at)
           VALUES ('movie', 'Dune', 'Disponible', 'Sin petición', 'N/A', ?, 10, CURRENT_TIMESTAMP)""",
        (str(f),),
    )
    conn.commit()
    return cur.lastrowid


def _peticion(conn) -> int:
    cur = conn.execute(
        "INSERT INTO request_items (emu_id, title, url) VALUES ('77', ?, ?)", (TITULO, ENLACE))
    conn.commit()
    return cur.lastrowid


def _fila(conn, job_id: int) -> tuple:
    return tuple(conn.execute(
        "SELECT request_item_id, request_title, request_url FROM upload_jobs WHERE id = ?", (job_id,),
    ).fetchone())


# ---------------------------------------------------------------------------
# Al encolar
# ---------------------------------------------------------------------------

def test_al_encolar_desde_una_peticion_se_guardan_su_titulo_y_su_enlace(db_conn, tmp_path):
    item, peticion = _peli(db_conn, tmp_path), _peticion(db_conn)

    job = uq.queue_upload_for_item(item, request_item_id=peticion, conn=db_conn)["job"]
    try:
        assert (job["request_title"], job["request_url"]) == (TITULO, ENLACE)
        assert _fila(db_conn, job["id"]) == (peticion, TITULO, ENLACE)

        # La petición se cierra en eMuwarez y la sincronización borra su fila.
        db_conn.execute("DELETE FROM request_items WHERE id = ?", (peticion,))
        db_conn.commit()
        assert _fila(db_conn, job["id"]) == (peticion, TITULO, ENLACE)
    finally:
        uq.cancel_queued_timer(job["id"])


def test_sin_peticion_las_columnas_quedan_vacias(db_conn, tmp_path):
    job = uq.queue_upload_for_item(_peli(db_conn, tmp_path), conn=db_conn)["job"]
    try:
        assert _fila(db_conn, job["id"]) == (None, None, None)
    finally:
        uq.cancel_queued_timer(job["id"])


def test_una_peticion_que_ya_no_existe_no_impide_encolar(db_conn, tmp_path):
    """Entre abrir el asistente y confirmar pasan minutos, y una sincronización
    puede haber borrado la petición. La subida sale igual, sin foto."""
    resultado = uq.queue_upload_for_item(_peli(db_conn, tmp_path), request_item_id=9999, conn=db_conn)
    try:
        assert resultado["status"] == "queued"
        _, titulo, enlace = _fila(db_conn, resultado["job"]["id"])
        assert (titulo, enlace) == (None, None)
    finally:
        uq.cancel_queued_timer(resultado["job"]["id"])


# ---------------------------------------------------------------------------
# Reintentos
# ---------------------------------------------------------------------------

def test_el_reintento_conserva_la_peticion_aunque_su_fila_ya_no_exista(db_conn, tmp_path):
    item, peticion = _peli(db_conn, tmp_path), _peticion(db_conn)
    primero = uq.queue_upload_for_item(item, request_item_id=peticion, conn=db_conn)["job"]["id"]
    uq.cancel_queued_timer(primero)
    db_conn.execute("UPDATE upload_jobs SET status = 'failed', stage = 'failed' WHERE id = ?", (primero,))
    db_conn.execute("DELETE FROM request_items WHERE id = ?", (peticion,))
    db_conn.commit()

    segundo = uq.queue_retry_for_job(primero, conn=db_conn)["job"]["id"]
    try:
        assert _fila(db_conn, segundo) == (peticion, TITULO, ENLACE)
    finally:
        uq.cancel_queued_timer(segundo)


def test_el_reintento_con_confirmacion_tambien_la_conserva(db_conn):
    from emuwarez_uploadrr.services import upload_execution as ex

    cur = db_conn.execute(
        """INSERT INTO upload_jobs (title, path, status, stage, request_item_id, request_title, request_url,
                                     created_at, updated_at)
           VALUES ('Dune', '/x/movie.mkv', 'failed', 'failed', 5, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (TITULO, ENLACE),
    )
    db_conn.commit()

    with patch.object(ex, "start_upload_job", return_value={"ok": True}):
        resultado = ex.retry_upload_job(
            cur.lastrowid, dry_run=False, start=True, confirmation=ex.CONFIRMATION_TOKEN)

    assert _fila(db_conn, resultado["new_job_id"]) == (5, TITULO, ENLACE)


# ---------------------------------------------------------------------------
# La API
# ---------------------------------------------------------------------------

CAMPOS = ("request_item_id", "request_title", "request_url")


def test_la_api_encola_desde_una_peticion_y_la_devuelve_en_la_lista_y_en_el_detalle(
        client, auth_headers, db_conn, tmp_path):
    item, peticion = _peli(db_conn, tmp_path), _peticion(db_conn)

    resp = client.post(
        f"/api/library/{item}/upload/queue", json={"request_item_id": peticion}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    job = resp.json()["job"]
    try:
        esperado = (peticion, TITULO, ENLACE)
        assert tuple(job[c] for c in CAMPOS) == esperado

        lista = client.get("/api/uploads", headers=auth_headers).json()
        assert tuple(lista[0][c] for c in CAMPOS) == esperado

        detalle = client.get(f"/api/uploads/{job['id']}", headers=auth_headers).json()
        assert tuple(detalle[c] for c in CAMPOS) == esperado
    finally:
        uq.cancel_queued_timer(job["id"])


def test_la_api_sin_peticion_devuelve_los_campos_vacios(client, auth_headers, db_conn, tmp_path):
    item = _peli(db_conn, tmp_path)

    resp = client.post(f"/api/library/{item}/upload/queue", json={}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    job = resp.json()["job"]
    try:
        assert tuple(job[c] for c in CAMPOS) == (None, None, None)
        detalle = client.get(f"/api/uploads/{job['id']}", headers=auth_headers).json()
        assert tuple(detalle[c] for c in CAMPOS) == (None, None, None)
    finally:
        uq.cancel_queued_timer(job["id"])


# ---------------------------------------------------------------------------
# La migración
# ---------------------------------------------------------------------------

def test_una_base_del_esquema_anterior_gana_las_columnas(db_conn):
    """init_db sale sin hacer nada si la versión ya coincide: la migración tiene
    que colgar de SCHEMA_VERSION, o un servidor ya actualizado no la correría."""
    db_conn.execute("ALTER TABLE upload_jobs DROP COLUMN request_title")
    db_conn.execute("ALTER TABLE upload_jobs DROP COLUMN request_url")
    set_state(db_conn, "schema_version", "40")
    db_conn.commit()

    init_db(db_conn)

    columnas = {fila["name"] for fila in db_conn.execute("PRAGMA table_info(upload_jobs)")}
    assert {"request_title", "request_url"} <= columnas
