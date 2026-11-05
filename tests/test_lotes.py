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


def _existe(conn, job_id: int) -> bool:
    return conn.execute("SELECT 1 FROM upload_jobs WHERE id = ?", (job_id,)).fetchone() is not None


def test_borrar_lote_borra_las_terminadas_con_su_cadena_y_deja_las_en_curso(db_conn, tmp_path):
    """Como «Borrar» en cada fila: la cadena entera del elemento, también su intento suelto anterior (D5)."""
    item = _peli(db_conn, tmp_path, "A")
    suelta = _encolar(db_conn, item, lote_id=None)
    _fallar(db_conn, suelta)
    completada = uq.queue_upload_for_item(item, lote_id=LOTE, conn=db_conn)["job"]["id"]  # encadena sobre la suelta
    _poner(db_conn, completada, "completed")
    fallida = _encolar(db_conn, _peli(db_conn, tmp_path, "B"))
    _fallar(db_conn, fallida)
    reintento = uq.queue_retry_for_job(fallida, conn=db_conn)["job"]["id"]
    _fallar(db_conn, reintento)
    cancelada = _encolar(db_conn, _peli(db_conn, tmp_path, "C"))
    _poner(db_conn, cancelada, "cancelled")
    en_cola = _encolar(db_conn, _peli(db_conn, tmp_path, "D"))
    subiendo = _encolar(db_conn, _peli(db_conn, tmp_path, "E"))
    _poner(db_conn, subiendo, "running")
    de_otro_lote = _encolar(db_conn, _peli(db_conn, tmp_path, "F"), lote_id=OTRO)
    _poner(db_conn, de_otro_lote, "completed")
    db_conn.execute("INSERT INTO upload_job_logs (upload_job_id, level, message, created_at) "
                    "VALUES (?, 'info', 'x', CURRENT_TIMESTAMP)", (fallida,))
    db_conn.commit()

    hecho = lotes.borrar_lote(db_conn, LOTE)

    assert hecho == {"borradas": 3, "intentos": 5, "en_curso": 2}
    for job in (suelta, completada, fallida, reintento, cancelada):
        assert not _existe(db_conn, job)
    assert (_estado(db_conn, en_cola), _estado(db_conn, subiendo), _estado(db_conn, de_otro_lote)) == (
        "queued", "running", "completed")
    assert db_conn.execute("SELECT COUNT(*) FROM upload_job_logs WHERE upload_job_id = ?", (fallida,)).fetchone()[0] == 0
    resumen = lotes.resumen_de_lote(db_conn, LOTE)
    assert (resumen["total"], resumen["en_cola"], resumen["en_marcha"]) == (2, 1, 1)


def test_borrar_lote_usa_el_mismo_borrado_que_una_fila_suelta(db_conn, tmp_path, monkeypatch):
    """Ni SQL propio ni otra regla: cada elemento pasa por delete_upload_job con el token de siempre."""
    from emuwarez_uploadrr.services import upload_execution
    llamadas = []
    original = upload_execution.delete_upload_job

    def espia(job_id, confirmation=None, conn=None):
        llamadas.append((job_id, confirmation))
        return original(job_id, confirmation=confirmation, conn=conn)
    monkeypatch.setattr(upload_execution, "delete_upload_job", espia)
    a = _encolar(db_conn, _peli(db_conn, tmp_path, "A"))
    b = _encolar(db_conn, _peli(db_conn, tmp_path, "B"))
    _poner(db_conn, a, "completed")
    _fallar(db_conn, b)

    assert lotes.borrar_lote(db_conn, LOTE) == {"borradas": 2, "intentos": 2, "en_curso": 0}
    assert llamadas == [(a, upload_execution.DELETE_CONFIRMATION_TOKEN), (b, upload_execution.DELETE_CONFIRMATION_TOKEN)]
    assert lotes.resumen_de_lote(db_conn, LOTE) is None


def test_borrar_lote_no_toca_una_que_volvio_a_la_cola_entre_medias(db_conn, tmp_path, monkeypatch):
    """Se leyó fallida, pero antes de borrarla alguien la reintentó: su cadena tiene un intento vivo y se queda."""
    job = _encolar(db_conn, _peli(db_conn, tmp_path))
    _fallar(db_conn, job)
    foto = lotes._puntas(db_conn, LOTE)
    reintento = uq.queue_retry_for_job(job, conn=db_conn)["job"]["id"]
    monkeypatch.setattr(lotes, "_puntas", lambda conn, lote_id: foto)

    assert lotes.borrar_lote(db_conn, LOTE) == {"borradas": 0, "intentos": 0, "en_curso": 1}
    assert _existe(db_conn, job) and _estado(db_conn, reintento) == "queued"


def test_la_api_borra_el_lote(client, auth_headers, db_conn, tmp_path):
    hecha = _encolar(db_conn, _peli(db_conn, tmp_path, "A"))
    en_cola = _encolar(db_conn, _peli(db_conn, tmp_path, "B"))
    _poner(db_conn, hecha, "completed")
    ruta = f"/api/uploads/lotes/{LOTE}/borrar"
    token = {"confirmation": "BORRAR_SUBIDA"}

    sin_token = client.post(ruta, json={}, headers=auth_headers)
    assert sin_token.status_code == 400 and _existe(db_conn, hecha)

    resp = client.post(ruta, json=token, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert (cuerpo["borradas"], cuerpo["intentos"], cuerpo["en_curso"]) == (1, 1, 1)
    assert (cuerpo["resumen"]["total"], cuerpo["resumen"]["en_cola"]) == (1, 1)
    assert not _existe(db_conn, hecha) and _estado(db_conn, en_cola) == "queued"

    # Con todo terminado, no queda lote.
    _poner(db_conn, en_cola, "cancelled")
    cuerpo = client.post(ruta, json=token, headers=auth_headers).json()
    assert (cuerpo["borradas"], cuerpo["resumen"]) == (1, None)
    assert client.post(ruta, json=token, headers=auth_headers).status_code == 404
    assert client.post("/api/uploads/lotes/NOVALE/borrar", json=token, headers=auth_headers).status_code == 422
    assert client.post(ruta, json=token).status_code == 401


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


def test_cancelar_todo_para_tambien_la_que_arranco_entre_medias(db_conn, tmp_path, monkeypatch):
    """Con «parar también las que están en marcha», una que estaba en cola al leer y ya se prepara al escribir
    también se para (por cancel_upload_job), no se queda contada como intacta."""
    job = _encolar(db_conn, _peli(db_conn, tmp_path))
    foto = lotes._puntas(db_conn, LOTE)
    _poner(db_conn, job, "preparing")
    monkeypatch.setattr(lotes, "_puntas", lambda conn, lote_id: foto)

    assert lotes.cancelar_lote(db_conn, LOTE, solo_pendientes=False) == {"canceladas": 1, "intactas": 0}
    assert _estado(db_conn, job) == "cancelled"


def test_dos_reintentos_a_la_vez_no_dejan_dos_puntas(db_conn, tmp_path):
    """La guardia de queue_retry_for_job va fuera de la transacción: la de dentro cierra la carrera."""
    item = _peli(db_conn, tmp_path)
    job = _encolar(db_conn, item)
    _fallar(db_conn, job)
    primero = uq.queue_retry_for_job(job, conn=db_conn)["job"]["id"]
    _fallar(db_conn, primero)
    fila = dict(db_conn.execute("SELECT * FROM library_items WHERE id = ?", (item,)).fetchone())

    # Lo que haría el segundo reintento si hubiera pasado la guardia de fuera antes de que existiera el primero.
    segundo = uq._insert_and_start_queued_job(db_conn, fila, retry_of_job_id=job, lote_id=LOTE)

    assert segundo["status"] == "blocked"
    assert f"#{primero}" in segundo["errors"][0]
    assert lotes.contar_por_lote(db_conn, [LOTE]) == {LOTE: 1}

# ---------------------------------------------------------------------------
# PR 3: POST /uploads/lote (encolar_lote)
# ---------------------------------------------------------------------------

LISTO = {"checks": [{"id": "accesible", "label": "El archivo es accesible", "status": "ok", "message": ""}],
         "ready": True}


@pytest.fixture
def sin_comprobaciones(monkeypatch):
    """Claves configuradas y contenido apto: cada test decide qué falla."""
    from emuwarez_uploadrr.services import upload_checks, upload_queue
    monkeypatch.setattr(upload_queue, "_season_upload_preconditions", lambda conn: [])
    contenido = {}
    monkeypatch.setattr(upload_checks, "run_upload_checks",
                        lambda conn, item_id, scope="all", **kw: contenido.get(item_id, LISTO))
    return contenido


def _item(conn, tipo: str, titulo: str, parent_id: int | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, parent_id, local_status, request_status, nomenclature_status,
                                      updated_at)
           VALUES (?, ?, ?, 'Disponible', 'Sin petición', 'N/A', CURRENT_TIMESTAMP)""",
        (tipo, titulo, parent_id),
    )
    conn.commit()
    return cur.lastrowid


def _el(item_id: int, **extra) -> dict:
    return {"item_id": item_id, "checks": LISTO, **extra}


def test_encolar_lote_en_el_orden_dado_con_una_sola_etiqueta(db_conn, tmp_path, sin_comprobaciones):
    a, b, c = (_peli(db_conn, tmp_path, t) for t in "ABC")

    r = lotes.encolar_lote(db_conn, [_el(c), _el(a), _el(b)])

    assert (r["encolados"], r["saltados"]) == (3, 0)
    assert lotes.lote_id_valido(r["lote_id"])
    filas = db_conn.execute("SELECT library_item_id, lote_id FROM upload_jobs ORDER BY id").fetchall()
    assert [tuple(f) for f in filas] == [(c, r["lote_id"]), (a, r["lote_id"]), (b, r["lote_id"])]
    assert [x["job_id"] for x in r["resultados"]] == [f[0] for f in db_conn.execute(
        "SELECT id FROM upload_jobs ORDER BY id")]


def test_encolar_lote_salta_cada_elemento_que_no_vale_sin_tumbar_el_resto(db_conn, tmp_path, sin_comprobaciones,
                                                                          monkeypatch):
    bueno = _peli(db_conn, tmp_path, "Buena")
    serie = _item(db_conn, "series", "Serie")
    temporada = _item(db_conn, "season", "T1", parent_id=serie)
    capitulo = _item(db_conn, "episode", "E1", parent_id=temporada)
    sin_castellano = _peli(db_conn, tmp_path, "Sin castellano")
    sin_comprobar = _peli(db_conn, tmp_path, "Sin comprobar")
    activo = _peli(db_conn, tmp_path, "Activa")
    _encolar(db_conn, activo, lote_id=None)
    revienta = _peli(db_conn, tmp_path, "Revienta")
    sin_comprobaciones[sin_castellano] = {
        "checks": [{"id": "spanish", "label": "No tiene castellano", "status": "fail", "message": "Sin pista"}],
        "ready": False}
    from emuwarez_uploadrr.services import upload_queue
    original = upload_queue.queue_upload_for_item

    def queue(item_id, **kw):
        if item_id == revienta:
            raise RuntimeError("boom")
        return original(item_id, **kw)
    monkeypatch.setattr(upload_queue, "queue_upload_for_item", queue)

    r = lotes.encolar_lote(db_conn, [
        _el(bueno), _el(bueno), _el(999999), _el(serie), _el(temporada), _el(capitulo), _el(sin_castellano),
        {"item_id": sin_comprobar, "checks": {"checks": [], "ready": False}}, _el(activo), _el(revienta),
    ])

    estados = [(x["item_id"], x["status"], (x["errors"] or [""])[0]) for x in r["resultados"]]
    assert estados == [
        (bueno, "queued", ""),
        (bueno, "blocked", "Repetido en el lote."),
        (999999, "blocked", "El elemento ya no está en la biblioteca."),
        (serie, "blocked", "Elige sus temporadas."),
        (temporada, "queued", ""),
        (capitulo, "blocked", "Su temporada ya va en el lote."),
        (sin_castellano, "blocked", "No tiene castellano: Sin pista"),
        (sin_comprobar, "blocked", "No pasó las comprobaciones previas."),
        (activo, "blocked", "Ya hay una subida en curso para este contenido."),
        (revienta, "blocked", "Error inesperado al encolarlo; mira el registro."),
    ]
    assert (r["encolados"], r["saltados"]) == (2, 8)


def test_ninguno_encolado_no_deja_lote(db_conn, tmp_path, sin_comprobaciones):
    serie = _item(db_conn, "series", "Serie")
    r = lotes.encolar_lote(db_conn, [_el(serie)])
    assert (r["lote_id"], r["encolados"]) == (None, 0)


def test_doble_clic_salta_todos_la_segunda_vez(db_conn, tmp_path, sin_comprobaciones):
    elementos = [_el(_peli(db_conn, tmp_path, t)) for t in "AB"]
    assert lotes.encolar_lote(db_conn, elementos)["encolados"] == 2
    segundo = lotes.encolar_lote(db_conn, elementos)
    assert (segundo["lote_id"], segundo["encolados"]) == (None, 0)


def test_falta_una_clave_rechaza_el_lote_entero(db_conn, tmp_path, monkeypatch):
    from emuwarez_uploadrr.services import upload_queue
    monkeypatch.setattr(upload_queue, "_season_upload_preconditions",
                        lambda conn: ["API key de TMDb no configurada."])
    with pytest.raises(lotes.LoteRechazado) as e:
        lotes.encolar_lote(db_conn, [_el(_peli(db_conn, tmp_path))])
    assert e.value.motivos == ["API key de TMDb no configurada."]
    assert db_conn.execute("SELECT COUNT(*) FROM upload_jobs").fetchone()[0] == 0


def test_el_tope_del_lote(db_conn):
    with pytest.raises(ValueError):
        lotes.encolar_lote(db_conn, [])
    with pytest.raises(ValueError):
        lotes.encolar_lote(db_conn, [_el(1)] * (lotes.MAX_ELEMENTOS_LOTE + 1))


def test_cada_elemento_lleva_su_peticion_sus_comprobaciones_y_el_proveedor_solo_en_packs(
        db_conn, tmp_path, sin_comprobaciones, monkeypatch):
    from emuwarez_uploadrr.services import upload_queue
    llamadas = []
    monkeypatch.setattr(upload_queue, "queue_upload_for_item",
                        lambda item_id, **kw: llamadas.append((item_id, kw)) or {"status": "queued", "job": {"id": 1}})
    peli = _peli(db_conn, tmp_path)
    temporada = _item(db_conn, "season", "T1", parent_id=_item(db_conn, "series", "S"))

    lotes.encolar_lote(db_conn, [_el(peli, request_item_id=7, provider="AMZN"), _el(temporada, provider="")])

    (p, kw_p), (t, kw_t) = llamadas
    assert (p, kw_p["request_item_id"], kw_p["checks"], kw_p["provider_override"]) == (peli, 7, LISTO, None)
    assert (t, kw_t["provider_override"]) == (temporada, "")
    assert kw_p["lote_id"] == kw_t["lote_id"]


def _peticion_compatible(conn, emu_id: str, cruce: int) -> int:
    from emuwarez_uploadrr.models import RequestItem
    from emuwarez_uploadrr.services.requests import upsert_request
    rid = upsert_request(conn, RequestItem(id=None, emu_id=emu_id, title=f"Petición {emu_id}", emu_status="Sin llenar",
                                           url=f"https://emu-warez.com/requests/{emu_id}"))
    conn.execute("INSERT INTO request_matches (library_item_id, request_item_id, status, confidence) "
                 "VALUES (?, ?, 'Compatible', 0.9)", (cruce, rid))
    conn.commit()
    return rid


def _peticion_del_trabajo(conn, job_id: int) -> tuple:
    return tuple(conn.execute("SELECT request_item_id, request_title FROM upload_jobs WHERE id = ?",
                              (job_id,)).fetchone())


def test_desde_biblioteca_enlaza_la_peticion_abierta_de_cada_elemento(db_conn, tmp_path, sin_comprobaciones):
    """Sin petición elegida, la abierta del elemento si hay una sola; con dos posibles (ambiguo), ninguna."""
    con_peticion = _peli(db_conn, tmp_path, "A")
    rid = _peticion_compatible(db_conn, "1", con_peticion)
    sin_peticion = _peli(db_conn, tmp_path, "B")
    ambigua = _peli(db_conn, tmp_path, "C")
    _peticion_compatible(db_conn, "2", ambigua)
    _peticion_compatible(db_conn, "3", ambigua)

    r = lotes.encolar_lote(db_conn, [_el(con_peticion), _el(sin_peticion), _el(ambigua)])

    a, b, c = (x["job_id"] for x in r["resultados"])
    assert _peticion_del_trabajo(db_conn, a) == (rid, "Petición 1")
    assert _peticion_del_trabajo(db_conn, b) == (None, None)
    assert _peticion_del_trabajo(db_conn, c) == (None, None)


def test_la_peticion_elegida_en_el_panel_gana(db_conn, tmp_path, sin_comprobaciones):
    peli = _peli(db_conn, tmp_path)
    _peticion_compatible(db_conn, "1", peli)
    elegida = _peticion_compatible(db_conn, "2", _peli(db_conn, tmp_path, "Otra"))

    job = lotes.encolar_lote(db_conn, [_el(peli, request_item_id=elegida)])["resultados"][0]["job_id"]

    assert _peticion_del_trabajo(db_conn, job) == (elegida, "Petición 2")


def test_si_falla_buscar_la_peticion_se_sube_igual_sin_ella(db_conn, tmp_path, sin_comprobaciones, monkeypatch):
    from emuwarez_uploadrr.services import requests as reqs

    def rota(conn, item_id):
        raise RuntimeError("boom")
    monkeypatch.setattr(reqs, "peticion_que_enlazar", rota)
    peli = _peli(db_conn, tmp_path)

    r = lotes.encolar_lote(db_conn, [_el(peli)])

    assert r["encolados"] == 1
    assert _peticion_del_trabajo(db_conn, r["resultados"][0]["job_id"]) == (None, None)


def test_campos_se_guardan_como_save_fields_y_no_si_el_elemento_se_salta(db_conn, tmp_path, sin_comprobaciones,
                                                                         monkeypatch):
    from emuwarez_uploadrr.services import nomenclature, source_assistant
    guardados = []
    monkeypatch.setattr(source_assistant, "update_nomenclature_fields_preview",
                        lambda item_id, campos, conn=None: {"torrent_name": "X"})
    monkeypatch.setattr(nomenclature, "save_manual_nomenclature_fields",
                        lambda item_id, campos, preview, conn: guardados.append((item_id, campos, preview)))
    campos = {"title": "Peli", "provider": "AMZN"}
    peli = _peli(db_conn, tmp_path, "A")
    activa = _peli(db_conn, tmp_path, "B")
    _encolar(db_conn, activa, lote_id=None)

    lotes.encolar_lote(db_conn, [_el(peli, campos=campos), _el(activa, campos=campos)])

    assert guardados == [(peli, campos, {"torrent_name": "X"})]


def test_la_api_encola_un_lote(client, auth_headers, db_conn, tmp_path, sin_comprobaciones):
    a, b = _peli(db_conn, tmp_path, "A"), _peli(db_conn, tmp_path, "B")

    resp = client.post("/api/uploads/lote", json={"elementos": [_el(a), _el(b)]}, headers=auth_headers)

    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert (cuerpo["encolados"], [x["status"] for x in cuerpo["resultados"]]) == (2, ["queued", "queued"])
    assert client.get(f"/api/uploads/lotes/{cuerpo['lote_id']}", headers=auth_headers).json()["total"] == 2


def test_la_api_valida_el_lote(client, auth_headers, db_conn, tmp_path, monkeypatch):
    assert client.post("/api/uploads/lote", json={"elementos": []}, headers=auth_headers).status_code == 422
    demasiados = [_el(1)] * (lotes.MAX_ELEMENTOS_LOTE + 1)
    assert client.post("/api/uploads/lote", json={"elementos": demasiados}, headers=auth_headers).status_code == 422
    assert client.post("/api/uploads/lote", json={"elementos": [{"item_id": 1}]},
                       headers=auth_headers).status_code == 422  # sin comprobaciones
    assert client.post("/api/uploads/lote", json={"elementos": [_el(1)]}).status_code == 401

    from emuwarez_uploadrr.services import upload_queue
    monkeypatch.setattr(upload_queue, "_season_upload_preconditions", lambda conn: ["Ruta de Uploadrr no existe: /x"])
    resp = client.post("/api/uploads/lote", json={"elementos": [_el(_peli(db_conn, tmp_path))]}, headers=auth_headers)
    assert (resp.status_code, resp.json()["detail"]) == (409, ["Ruta de Uploadrr no existe: /x"])
