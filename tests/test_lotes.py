"""Lotes de subidas (PR 1 del plan de la subida por lotes): la etiqueta `upload_jobs.lote_id`.

Un lote no es una tabla: es la etiqueta que llevan las subidas lanzadas de una vez (hoy, una tanda del asistente). Lo que
se sabe de él se deduce de sus filas, y un elemento del lote es la punta de su cadena de reintentos.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import lotes
from emuwarez_uploadrr.services import upload_queue as uq
from emuwarez_uploadrr.services.upload_execution import count_upload_jobs, list_upload_jobs

LOTE = "0123456789ab"
OTRO = "ba9876543210"


@pytest.fixture(autouse=True)
def _biblioteca_en_tmp(tmp_path, monkeypatch):
    from emuwarez_uploadrr.services import uploadrr_contract
    monkeypatch.setattr(uploadrr_contract, "DEFAULT_ALLOWED_ROOTS", [str(tmp_path)])


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    yield conn
    conn.close()


def _peli(conn, tmp_path, titulo: str = "Peli") -> int:
    f = tmp_path / f"{titulo}.mkv"
    f.write_bytes(b"x" * 10)
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status, path,
                                      size_bytes, updated_at)
           VALUES ('movie', ?, 'Disponible', 'Sin petición', 'N/A', ?, 10, CURRENT_TIMESTAMP)""",
        (titulo, str(f)),
    )
    conn.commit()
    return cur.lastrowid


def _fallar(conn, job_id: int) -> None:
    conn.execute("UPDATE upload_jobs SET status = 'failed', stage = 'failed' WHERE id = ?", (job_id,))
    conn.commit()


def _encolar(conn, item: int, lote_id: str | None = LOTE) -> int:
    resultado = uq.queue_upload_for_item(item, lote_id=lote_id, conn=conn)
    assert resultado["status"] == "queued", resultado
    return resultado["job"]["id"]


# ---------------------------------------------------------------------------
# La migración (esquema 52)
# ---------------------------------------------------------------------------

def test_la_migracion_añade_la_columna_y_el_indice_y_se_puede_repetir(db_conn):
    from emuwarez_uploadrr.database import _migrate_upload_jobs_lote
    columnas = lambda: {f[1] for f in db_conn.execute("PRAGMA table_info(upload_jobs)")}  # noqa: E731
    indices = lambda: {f[1] for f in db_conn.execute("PRAGMA index_list(upload_jobs)")}  # noqa: E731
    assert "lote_id" in columnas() and "idx_upload_jobs_lote" in indices()

    # SQLite no deja quitar una columna indexada: primero el índice.
    db_conn.execute("DROP INDEX idx_upload_jobs_lote")
    db_conn.execute("ALTER TABLE upload_jobs DROP COLUMN lote_id")
    assert "lote_id" not in columnas()

    _migrate_upload_jobs_lote(db_conn)
    _migrate_upload_jobs_lote(db_conn)

    assert "lote_id" in columnas() and "idx_upload_jobs_lote" in indices()
    db_conn.execute("INSERT INTO upload_jobs (title, path, status, created_at, updated_at) "
                    "VALUES ('x', '/x', 'failed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
    assert db_conn.execute("SELECT lote_id FROM upload_jobs").fetchone()[0] is None


def test_la_columna_sobrevive_al_atajo_de_la_version_de_esquema(db_conn):
    """init_db se salta la cascada si la versión guardada ya es la actual: la columna tiene que llegar igual a una
    base que la perdió (mismo patrón que la de season_overrides)."""
    from emuwarez_uploadrr.database import SCHEMA_VERSION, init_db

    assert SCHEMA_VERSION >= 52
    db_conn.execute("DROP INDEX idx_upload_jobs_lote")
    db_conn.execute("ALTER TABLE upload_jobs DROP COLUMN lote_id")
    db_conn.execute("DELETE FROM app_state WHERE key = 'schema_version'")
    db_conn.commit()

    init_db(db_conn)

    assert "lote_id" in {f[1] for f in db_conn.execute("PRAGMA table_info(upload_jobs)")}


# ---------------------------------------------------------------------------
# Encolar y reintentar
# ---------------------------------------------------------------------------

def test_encolar_con_lote_lo_guarda_y_sin_lote_queda_vacio(db_conn, tmp_path):
    con = _encolar(db_conn, _peli(db_conn, tmp_path, "A"))
    sin = _encolar(db_conn, _peli(db_conn, tmp_path, "B"), lote_id=None)

    fila = lambda job: db_conn.execute("SELECT lote_id FROM upload_jobs WHERE id = ?", (job,)).fetchone()[0]  # noqa: E731
    assert fila(con) == LOTE
    assert fila(sin) is None


def test_un_reintento_sigue_en_el_mismo_lote(db_conn, tmp_path):
    job = _encolar(db_conn, _peli(db_conn, tmp_path))
    _fallar(db_conn, job)

    reintento = uq.queue_retry_for_job(job, conn=db_conn)

    assert reintento["status"] == "queued"
    assert reintento["job"]["lote_id"] == LOTE
    assert reintento["job"]["retry_of_job_id"] == job


def test_subir_otra_vez_el_elemento_no_hereda_el_lote(db_conn, tmp_path):
    """Un «Subir» nuevo del mismo elemento encadena sobre su último trabajo pero no entra en su lote."""
    item = _peli(db_conn, tmp_path)
    job = _encolar(db_conn, item)
    _fallar(db_conn, job)

    nuevo = uq.queue_upload_for_item(item, conn=db_conn)["job"]

    assert nuevo["retry_of_job_id"] == job
    assert nuevo["lote_id"] is None


# ---------------------------------------------------------------------------
# Contar y filtrar: solo las puntas de cadena
# ---------------------------------------------------------------------------

def test_contar_por_lote_cuenta_elementos_no_intentos(db_conn, tmp_path):
    a = _encolar(db_conn, _peli(db_conn, tmp_path, "A"))
    _encolar(db_conn, _peli(db_conn, tmp_path, "B"))
    _encolar(db_conn, _peli(db_conn, tmp_path, "C"), lote_id=OTRO)
    _fallar(db_conn, a)
    uq.queue_retry_for_job(a, conn=db_conn)

    assert lotes.contar_por_lote(db_conn, [LOTE, OTRO, None]) == {LOTE: 2, OTRO: 1}
    assert lotes.contar_por_lote(db_conn, []) == {}


def test_un_elemento_subido_despues_fuera_del_lote_sale_de_el(db_conn, tmp_path):
    item = _peli(db_conn, tmp_path, "A")
    job = _encolar(db_conn, item)
    _encolar(db_conn, _peli(db_conn, tmp_path, "B"))
    _fallar(db_conn, job)
    uq.queue_upload_for_item(item, conn=db_conn)

    assert lotes.contar_por_lote(db_conn, [LOTE]) == {LOTE: 1}


def test_el_filtro_por_lote_devuelve_y_cuenta_solo_las_puntas(db_conn, tmp_path):
    a = _encolar(db_conn, _peli(db_conn, tmp_path, "A"))
    b = _encolar(db_conn, _peli(db_conn, tmp_path, "B"))
    _encolar(db_conn, _peli(db_conn, tmp_path, "C"), lote_id=None)
    _fallar(db_conn, a)
    reintento = uq.queue_retry_for_job(a, conn=db_conn)["job"]["id"]

    ids = {j["id"] for j in list_upload_jobs({"lote_id": LOTE}, conn=db_conn)}

    assert ids == {b, reintento}
    assert count_upload_jobs({"lote_id": LOTE}, conn=db_conn) == 2
    # Sin filtro siguen saliendo todos los intentos.
    assert count_upload_jobs({}, conn=db_conn) == 4


def test_nuevo_lote_id_tiene_el_formato_del_patron():
    valor = lotes.nuevo_lote_id()
    assert lotes.lote_id_valido(valor)
    assert valor != lotes.nuevo_lote_id()
    assert not lotes.lote_id_valido("0123456789AB")
    assert not lotes.lote_id_valido("123")
    assert not lotes.lote_id_valido(None)


# ---------------------------------------------------------------------------
# La API
# ---------------------------------------------------------------------------

def test_la_api_encola_con_lote_y_lo_devuelve_con_su_total(client, auth_headers, db_conn, tmp_path):
    a, b = _peli(db_conn, tmp_path, "A"), _peli(db_conn, tmp_path, "B")
    for item in (a, b):
        resp = client.post(f"/api/library/{item}/upload/queue", json={"lote_id": LOTE}, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["job"]["lote_id"] == LOTE
    suelta = client.post(f"/api/library/{_peli(db_conn, tmp_path, 'C')}/upload/queue", json={},
                         headers=auth_headers).json()["job"]

    lista = client.get("/api/uploads", headers=auth_headers).json()
    por_id = {j["id"]: j for j in lista}
    assert {(j["lote_id"], j["lote_total"]) for j in lista if j["id"] != suelta["id"]} == {(LOTE, 2)}
    assert (por_id[suelta["id"]]["lote_id"], por_id[suelta["id"]]["lote_total"]) == (None, None)

    filtrada = client.get(f"/api/uploads?lote_id={LOTE}", headers=auth_headers).json()
    assert len(filtrada) == 2
    assert client.get(f"/api/uploads/count?lote_id={LOTE}", headers=auth_headers).json() == {"total": 2}

    detalle = client.get(f"/api/uploads/{filtrada[0]['id']}", headers=auth_headers).json()
    assert (detalle["lote_id"], detalle["lote_total"]) == (LOTE, 2)


@pytest.mark.parametrize("malo", ["0123456789AB", "123", "0123456789abc", "zzzzzzzzzzzz"])
def test_la_api_rechaza_un_lote_mal_formado(client, auth_headers, db_conn, tmp_path, malo):
    item = _peli(db_conn, tmp_path)

    assert client.post(f"/api/library/{item}/upload/queue", json={"lote_id": malo},
                       headers=auth_headers).status_code == 422
    assert client.get(f"/api/uploads?lote_id={malo}", headers=auth_headers).status_code == 422
    assert client.get(f"/api/uploads/count?lote_id={malo}", headers=auth_headers).status_code == 422
    assert db_conn.execute("SELECT COUNT(*) FROM upload_jobs").fetchone()[0] == 0
