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


# ---------------------------------------------------------------------------
# PR 2: resumen, cancelar pendientes y reintentar fallidas
# ---------------------------------------------------------------------------

def _estado(conn, job_id: int) -> str:
    return conn.execute("SELECT status FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()[0]


def _poner(conn, job_id: int, estado: str) -> None:
    conn.execute("UPDATE upload_jobs SET status = ?, stage = ? WHERE id = ?", (estado, estado, job_id))
    conn.commit()


def test_resumen_de_lote_cuenta_cada_estado_sobre_las_puntas(db_conn, tmp_path):
    ids = [_encolar(db_conn, _peli(db_conn, tmp_path, t)) for t in "ABCDE"]
    _poner(db_conn, ids[1], "preparing")
    _poner(db_conn, ids[2], "completed")
    _poner(db_conn, ids[3], "cancelled")
    _fallar(db_conn, ids[4])
    uq.queue_retry_for_job(ids[4], conn=db_conn)  # vuelve a la cola: el fallido deja de ser punta

    resumen = lotes.resumen_de_lote(db_conn, LOTE)

    assert {k: resumen[k] for k in ("total", "en_cola", "en_marcha", "completadas", "fallidas", "canceladas")} == {
        "total": 5, "en_cola": 2, "en_marcha": 1, "completadas": 1, "fallidas": 0, "canceladas": 1}
    assert (resumen["terminado"], resumen["puede_cancelar"], resumen["puede_reintentar"]) == (False, True, True)
    assert lotes.resumen_de_lote(db_conn, OTRO) is None


def test_cancelar_pendientes_deja_en_paz_lo_que_ya_esta_en_marcha(db_conn, tmp_path, monkeypatch):
    from emuwarez_uploadrr.services import upload_queue
    en_marcha = _encolar(db_conn, _peli(db_conn, tmp_path, "A"))
    pendientes = [_encolar(db_conn, _peli(db_conn, tmp_path, t)) for t in "BC"]
    _poner(db_conn, en_marcha, "running")
    retiradas = []

    def retirar(job_id):
        # Al sacar la primera de la puerta, todas las pendientes ya están canceladas en la base.
        retiradas.append((job_id, [_estado(db_conn, j) for j in pendientes]))
    monkeypatch.setattr(upload_queue, "retirar_de_la_cola", retirar)

    hecho = lotes.cancelar_lote(db_conn, LOTE)

    assert hecho == {"canceladas": 2, "intactas": 0}
    assert [_estado(db_conn, j) for j in pendientes] == ["cancelled", "cancelled"]
    assert _estado(db_conn, en_marcha) == "running"
    assert retiradas == [(j, ["cancelled", "cancelled"]) for j in pendientes]


def test_cancelar_pendientes_no_toca_una_que_arranco_entre_medias(db_conn, tmp_path, monkeypatch):
    """La lista se leyó con la subida en cola, pero cuando se escribe ya se está preparando: no es pendiente."""
    job = _encolar(db_conn, _peli(db_conn, tmp_path))
    foto = lotes._puntas(db_conn, LOTE)
    _poner(db_conn, job, "preparing")
    monkeypatch.setattr(lotes, "_puntas", lambda conn, lote_id: foto)

    assert lotes.cancelar_lote(db_conn, LOTE) == {"canceladas": 0, "intactas": 1}
    assert _estado(db_conn, job) == "preparing"


def test_cancelar_todo_para_tambien_lo_que_se_prepara(db_conn, tmp_path):
    preparando = _encolar(db_conn, _peli(db_conn, tmp_path, "A"))
    pendiente = _encolar(db_conn, _peli(db_conn, tmp_path, "B"))
    hecha = _encolar(db_conn, _peli(db_conn, tmp_path, "C"))
    _poner(db_conn, preparando, "preparing")
    _poner(db_conn, hecha, "completed")

    hecho = lotes.cancelar_lote(db_conn, LOTE, solo_pendientes=False)

    assert hecho == {"canceladas": 2, "intactas": 0}
    assert (_estado(db_conn, preparando), _estado(db_conn, pendiente), _estado(db_conn, hecha)) == (
        "cancelled", "cancelled", "completed")


def test_reintentar_fallidas_reencola_en_orden_y_sigue_en_el_lote(db_conn, tmp_path):
    fallida = _encolar(db_conn, _peli(db_conn, tmp_path, "A"))
    hecha = _encolar(db_conn, _peli(db_conn, tmp_path, "B"))
    cancelada = _encolar(db_conn, _peli(db_conn, tmp_path, "C"))
    _fallar(db_conn, fallida)
    _poner(db_conn, hecha, "completed")
    _poner(db_conn, cancelada, "cancelled")

    hecho = lotes.reintentar_fallidas(db_conn, LOTE)

    assert (hecho["reintentadas"], hecho["saltadas"]) == (2, [])
    nuevas = db_conn.execute(
        "SELECT retry_of_job_id, lote_id FROM upload_jobs WHERE retry_of_job_id IS NOT NULL ORDER BY id").fetchall()
    assert [tuple(f) for f in nuevas] == [(fallida, LOTE), (cancelada, LOTE)]
    assert lotes.resumen_de_lote(db_conn, LOTE)["en_cola"] == 2


def test_reintentar_fallidas_salta_la_que_ya_no_se_puede_reintentar(db_conn, tmp_path):
    job = _encolar(db_conn, _peli(db_conn, tmp_path))
    _fallar(db_conn, job)
    db_conn.execute("DELETE FROM library_items")
    db_conn.commit()

    hecho = lotes.reintentar_fallidas(db_conn, LOTE)

    assert hecho["reintentadas"] == 0
    assert [s["job_id"] for s in hecho["saltadas"]] == [job]
    assert hecho["saltadas"][0]["errors"]


def test_solo_se_reintenta_la_punta_de_la_cadena(db_conn, tmp_path):
    """Reintentar un intento anterior abría otra punta para el mismo elemento (y el lote contaba uno de más)."""
    job = _encolar(db_conn, _peli(db_conn, tmp_path))
    _fallar(db_conn, job)
    reintento = uq.queue_retry_for_job(job, conn=db_conn)["job"]["id"]
    _fallar(db_conn, reintento)

    otra_vez = uq.queue_retry_for_job(job, conn=db_conn)

    assert otra_vez["status"] == "blocked"
    assert f"#{reintento}" in otra_vez["errors"][0]
    assert uq.queue_retry_for_job(reintento, conn=db_conn)["status"] == "queued"
    assert lotes.contar_por_lote(db_conn, [LOTE]) == {LOTE: 1}


def test_la_puerta_lee_el_limite_una_vez_por_segundo_y_lo_olvida_al_vaciarse(monkeypatch):
    from emuwarez_uploadrr.services.upload_execution import concurrencia
    lecturas = []
    monkeypatch.setattr(concurrencia, "get_upload_max_concurrent", lambda conn=None: lecturas.append(1) or 1)
    puerta = concurrencia._UploadConcurrencyGate()

    assert [puerta._limite() for _ in range(5)] == [1] * 5
    assert len(lecturas) == 1

    puerta.acquire(1)  # entra y la cola queda vacía: se olvida lo leído
    puerta.release()
    assert puerta._limite_leido is None
    puerta._limite()
    assert len(lecturas) == 2


def test_la_api_del_lote(client, auth_headers, db_conn, tmp_path):
    a = _encolar(db_conn, _peli(db_conn, tmp_path, "A"))
    b = _encolar(db_conn, _peli(db_conn, tmp_path, "B"))
    _fallar(db_conn, a)

    resumen = client.get(f"/api/uploads/lotes/{LOTE}", headers=auth_headers)
    assert resumen.status_code == 200, resumen.text
    assert (resumen.json()["total"], resumen.json()["fallidas"], resumen.json()["en_cola"]) == (2, 1, 1)

    cancelar = client.post(f"/api/uploads/lotes/{LOTE}/cancelar", json={}, headers=auth_headers).json()
    assert (cancelar["canceladas"], cancelar["resumen"]["canceladas"]) == (1, 1)
    assert _estado(db_conn, b) == "cancelled"

    reintentar = client.post(f"/api/uploads/lotes/{LOTE}/reintentar", json={}, headers=auth_headers).json()
    assert (reintentar["reintentadas"], reintentar["resumen"]["en_cola"]) == (2, 2)

    assert client.get(f"/api/uploads/lotes/{OTRO}", headers=auth_headers).status_code == 404
    assert client.post(f"/api/uploads/lotes/{OTRO}/cancelar", json={}, headers=auth_headers).status_code == 404
    assert client.get("/api/uploads/lotes/NOVALE", headers=auth_headers).status_code == 422
    assert client.get(f"/api/uploads/lotes/{LOTE}").status_code == 401
