"""El freno del lote (pregunta 4 de docs/PLAN_SUBIDA_POR_LOTES.md): tras FALLOS_SEGUIDOS_PARA_PARAR fallos seguidos
con el mismo motivo, las puntas del lote que esperan en la cola no se lanzan.

Los fallos se provocan por el camino real: upload_queue._fail (la preparación) o _finalize_job_status +
_notify_upload_failed (lo que hace la ejecución de Uploadrr-EMU), que es quien llama al freno.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from emuwarez_uploadrr.services import lotes
from emuwarez_uploadrr.services import upload_queue as uq
from emuwarez_uploadrr.services.upload_execution import _finalize_job_status, _notify_upload_failed

LOTE = "0123456789ab"
SISTEMICO = "Forbidden (403): la cuenta no tiene permiso de subida\nExit code: 1"
MOTIVO = "Forbidden (403): la cuenta no tiene permiso de subida"
PARADO = f"Lote parado: 5 fallos seguidos por «{MOTIVO}»"


@pytest.fixture
def db_conn(isolated_db):
    """La misma base que abren los servicios (connect() sin ruta)."""
    from emuwarez_uploadrr.database import connect, db_path, init_db
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def retiradas(monkeypatch):
    """Lo que se saca de la puerta de «Subidas en paralelo», con el estado de cada una en ese momento."""
    from emuwarez_uploadrr.database import connect
    hechas: list[tuple[int, str]] = []

    def retirar(job_id: int) -> None:
        conn = connect()
        try:
            hechas.append((job_id, conn.execute("SELECT status FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()[0]))
        finally:
            conn.close()
    monkeypatch.setattr(uq, "retirar_de_la_cola", retirar)
    return hechas


def _trabajo(conn, *, status: str = "running", lote_id: str | None = LOTE, titulo: str = "Peli") -> int:
    cur = conn.execute(
        """INSERT INTO upload_jobs (title, path, status, stage, lote_id, created_at, updated_at)
           VALUES (?, '/x', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (titulo, status, status, lote_id),
    )
    conn.commit()
    return cur.lastrowid


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _completar(conn, job_id: int) -> None:
    conn.execute("UPDATE upload_jobs SET status = 'completed', stage = 'finished', finished_at = ? WHERE id = ?",
                 (_ahora(), job_id))
    conn.commit()


def _fila(conn, job_id: int) -> dict:
    return dict(conn.execute("SELECT * FROM upload_jobs WHERE id = ?", (job_id,)).fetchone())


def _estados(conn, ids) -> list[str]:
    return [_fila(conn, j)["status"] for j in ids]


def _avisos(conn, titulo: str | None = None) -> list[dict]:
    filas = [dict(f) for f in conn.execute("SELECT * FROM notifications ORDER BY id").fetchall()]
    return [f for f in filas if titulo is None or f["title"] == titulo]


def _modo(conn, modo: str) -> None:
    from emuwarez_uploadrr.services.settings import escribir_ajuste
    escribir_ajuste(conn, "notify_lote_modo", modo)
    conn.commit()


def _lote(conn, *, en_marcha: int, en_cola: int, lote_id: str = LOTE) -> tuple[list[int], list[int]]:
    marcha = [_trabajo(conn, titulo=f"M{i}", lote_id=lote_id) for i in range(en_marcha)]
    cola = [_trabajo(conn, status="queued", titulo=f"C{i}", lote_id=lote_id) for i in range(en_cola)]
    return marcha, cola


# ---------------------------------------------------------------------------
# Qué es un fallo «por elemento»
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mensaje", [
    "Potential duplicate on EMU\nExit code: 1",
    "Exact size match. Aborting..",
    "Banned group on EMU\nExit code: 1",
    "TMDb ID not found\nExit code: 1",
    "Upload failed: The name has already been taken.\nError details: {...}\nEMU Rejected Upload",
    "El archivo no es accesible: /data/peli.mkv",
    "El archivo del capítulo 3 no es accesible: /data/s01e03.mkv",
    "MediaInfo no pudo leer el fichero (posible corrupción).",
    "mkvtoolnix no pudo leer el archivo del capítulo 2: roto",
    "Hay errores en la propuesta de nomenclatura que bloquean la subida.",
    "No se pudo aplicar la nomenclatura: el nombre es demasiado largo",
    "Error aplicando la nomenclatura del pack de temporada: boom",
    "«Peli.2020.1080p.mkv» es de la subida #12, que lo siembra o lo tiene en qBittorrent: no se rehace.",
    "El elemento ya no existe en la biblioteca.",
    "Interrumpido al pararse la aplicación. Puedes reintentar la subida.",
    "",
    None,
])
def test_los_fallos_por_elemento_no_tienen_motivo_de_lote(mensaje):
    assert lotes.motivo_de_fallo(mensaje) is None


@pytest.mark.parametrize("mensaje, motivo", [
    (SISTEMICO, MOTIVO),
    ("  Upload failed: EMU no ha respondido tras 3 intentos  \nExit code: 1",
     "Upload failed: EMU no ha respondido tras 3 intentos"),
    ("Proceso cancelado por timeout (3600s).", "Proceso cancelado por timeout (3600s)."),
    ("Dupe search failed on EMU\nExit code: 1", "Dupe search failed on EMU"),
    # Una clave que falta junto con la nomenclatura bloqueada sí habla del resto.
    ("API key de TMDb no configurada.; Hay errores en la propuesta de nomenclatura que bloquean la subida.",
     "API key de TMDb no configurada.; Hay errores en la propuesta de nomenclatura que bloquean la subida."),
])
def test_los_fallos_sistemicos_se_comparan_por_su_primera_linea(mensaje, motivo):
    assert lotes.motivo_de_fallo(mensaje) == motivo


def test_las_marcas_de_la_app_siguen_en_los_mensajes_que_escribe():
    """Si un mensaje de la preparación cambia y su marca no, ese fallo pasaría a contar para el freno."""
    servicios = Path(lotes.__file__).parent
    codigo = "\n".join(p.read_text(encoding="utf-8") for p in servicios.rglob("*.py") if p.name != "lotes.py")
    for marca in lotes._MARCAS_DE_LA_APP:
        assert marca in codigo, f"«{marca}» ya no aparece en ningún mensaje de services/"


# ---------------------------------------------------------------------------
# La racha
# ---------------------------------------------------------------------------

def test_cinco_fallos_seguidos_paran_lo_que_espera_en_la_cola(db_conn, retiradas):
    marcha, cola = _lote(db_conn, en_marcha=5, en_cola=3)
    preparando = _trabajo(db_conn, status="preparing", titulo="P")

    for job in marcha[:4]:
        uq._fail(job, SISTEMICO)
    assert _estados(db_conn, cola) == ["queued"] * 3, "cuatro fallos no paran el lote"
    assert retiradas == []

    uq._fail(marcha[4], SISTEMICO)

    for job in cola:
        fila = _fila(db_conn, job)
        assert (fila["status"], fila["stage"], fila["error_message"]) == ("cancelled", lotes.ETAPA_LOTE_PARADO, PARADO)
        assert fila["finished_at"]
    assert _fila(db_conn, preparando)["status"] == "preparing", "lo que ya se prepara sigue"
    # Fuera de la puerta, y cada una ya cancelada en la base al sacarla.
    assert retiradas == [(j, "cancelled") for j in cola]

    # «Una por subida»: cada fallo avisa como siempre y el lote, una vez; las paradas no avisan una a una.
    avisos = _avisos(db_conn)
    assert [a["title"] for a in avisos] == ["Subida fallida"] * 5 + ["Lote parado"]
    parada = avisos[-1]
    assert (parada["event_type"], parada["level"]) == ("upload_failed", "error")
    assert (parada["entity_type"], parada["entity_id"]) == ("upload_lote", int(LOTE, 16))
    assert parada["body"] == (f"{PARADO}. 3 subidas no llegaron a empezar; «Reintentar fallidas» las relanza.\n"
                              f"Lote {LOTE}.")
    assert not any(a["entity_type"] == "upload_job" and a["entity_id"] in cola for a in avisos)

    resumen = lotes.resumen_de_lote(db_conn, LOTE)
    assert (resumen["parado"], resumen["paradas"], resumen["canceladas"], resumen["en_cola"]) == (PARADO, 3, 3, 0)
    assert resumen["puede_reintentar"]

    # Un fallo más (el que se preparaba) ya no tiene nada que parar ni avisa otra vez del lote.
    uq._fail(preparando, SISTEMICO)
    assert len(_avisos(db_conn, "Lote parado")) == 1


def test_el_fallo_de_uploadrr_tambien_cuenta(db_conn, retiradas):
    """Lo que hace la ejecución al fallar Uploadrr-EMU: escribir el estado y después avisar."""
    marcha, cola = _lote(db_conn, en_marcha=5, en_cola=1)
    for job in marcha:
        _finalize_job_status(job, "failed", stage="failed", finished_at=_ahora(), error_message=SISTEMICO)
        _notify_upload_failed(job, SISTEMICO)
    assert _estados(db_conn, cola) == ["cancelled"]
    assert len(_avisos(db_conn, "Lote parado")) == 1


def test_los_fallos_por_elemento_ni_cuentan_ni_cortan_la_racha(db_conn, retiradas):
    marcha, cola = _lote(db_conn, en_marcha=8, en_cola=2)
    cancelada = _trabajo(db_conn, status="cancelled", titulo="X")
    db_conn.execute("UPDATE upload_jobs SET finished_at = ? WHERE id = ?", (_ahora(), cancelada))
    db_conn.commit()

    for job in marcha[:3]:
        uq._fail(job, SISTEMICO)
    uq._fail(marcha[3], "Potential duplicate on EMU\nExit code: 1")
    uq._fail(marcha[4], "El archivo no es accesible: /data/peli.mkv")
    uq._fail(marcha[5], SISTEMICO)
    assert _estados(db_conn, cola) == ["queued"] * 2, "cuatro sistémicos (con dos por elemento entre medias)"
    # Un fallo por elemento no dispara nada aunque la racha ya estuviera completa antes.
    uq._fail(marcha[6], "TMDb ID not found\nExit code: 1")
    assert _estados(db_conn, cola) == ["queued"] * 2

    uq._fail(marcha[7], SISTEMICO)
    assert _estados(db_conn, cola) == ["cancelled"] * 2
    assert _fila(db_conn, cancelada)["stage"] == "cancelled", "una cancelada a mano no se toca"


def test_una_completada_corta_la_racha(db_conn, retiradas):
    marcha, cola = _lote(db_conn, en_marcha=9, en_cola=1)
    for job in marcha[:3]:
        uq._fail(job, SISTEMICO)
    _completar(db_conn, marcha[3])
    for job in marcha[4:8]:
        uq._fail(job, SISTEMICO)
    assert _estados(db_conn, cola) == ["queued"], "solo cuatro desde la completada"

    uq._fail(marcha[8], SISTEMICO)
    assert _estados(db_conn, cola) == ["cancelled"]


def test_motivos_distintos_no_paran(db_conn, retiradas):
    marcha, cola = _lote(db_conn, en_marcha=5, en_cola=1)
    for job in marcha[:4]:
        uq._fail(job, SISTEMICO)
    uq._fail(marcha[4], "Dupe search failed on EMU\nExit code: 1")
    assert _estados(db_conn, cola) == ["queued"]
    assert _avisos(db_conn, "Lote parado") == []


def test_sin_nada_en_cola_no_hay_nada_que_parar(db_conn, retiradas):
    marcha, _cola = _lote(db_conn, en_marcha=6, en_cola=0)
    for job in marcha[:5]:
        uq._fail(job, SISTEMICO)
    assert _fila(db_conn, marcha[5])["status"] == "running"
    assert _avisos(db_conn, "Lote parado") == []


def test_una_suelta_o_de_otro_lote_no_cuenta(db_conn, retiradas):
    _marcha, cola = _lote(db_conn, en_marcha=0, en_cola=2)
    otro = [_trabajo(db_conn, lote_id="ba9876543210") for _ in range(5)]
    sueltas = [_trabajo(db_conn, lote_id=None) for _ in range(5)]
    for job in otro + sueltas:
        uq._fail(job, SISTEMICO)
    assert _estados(db_conn, cola) == ["queued"] * 2


def test_una_que_arranco_entre_la_decision_y_la_escritura_sigue(db_conn, retiradas, monkeypatch):
    marcha, cola = _lote(db_conn, en_marcha=5, en_cola=3)
    decidir = lotes._decidir_parada

    def y_arranca_una(conn, lote_id, job_id):
        decision = decidir(conn, lote_id, job_id)
        if decision:
            db_conn.execute("UPDATE upload_jobs SET status = 'preparing', stage = 'nomenclature' WHERE id = ?",
                            (cola[0],))
            db_conn.commit()
        return decision
    monkeypatch.setattr(lotes, "_decidir_parada", y_arranca_una)

    for job in marcha:
        uq._fail(job, SISTEMICO)

    assert _estados(db_conn, cola) == ["preparing", "cancelled", "cancelled"]
    assert [j for j, _ in retiradas] == cola[1:]
    assert "2 subidas no llegaron a empezar" in _avisos(db_conn, "Lote parado")[0]["body"]


# ---------------------------------------------------------------------------
# Concurrencia: una sola decisión y un solo aviso
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ronda", range(4))
def test_fallos_a_la_vez_paran_una_sola_vez(db_conn, retiradas, ronda):
    marcha, cola = _lote(db_conn, en_marcha=7, en_cola=3)
    for job in marcha[:3]:
        uq._fail(job, SISTEMICO)
    a_la_vez = marcha[3:]
    salida = threading.Barrier(len(a_la_vez))
    errores: list[BaseException] = []

    def fallar(job_id: int) -> None:
        try:
            salida.wait(timeout=5)
            uq._fail(job_id, SISTEMICO)
        except BaseException as exc:  # noqa: BLE001 - se comprueba abajo
            errores.append(exc)

    hilos = [threading.Thread(target=fallar, args=(j,)) for j in a_la_vez]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    assert not errores, errores

    assert _estados(db_conn, cola) == ["cancelled"] * 3
    assert sorted(j for j, _ in retiradas) == cola, "cada parada se saca de la puerta una sola vez"
    assert len(_avisos(db_conn, "Lote parado")) == 1


def test_la_decision_se_apunta_y_no_se_repite(db_conn):
    marcha, cola = _lote(db_conn, en_marcha=5, en_cola=2)
    for job in marcha:
        db_conn.execute("UPDATE upload_jobs SET status = 'failed', error_message = ?, finished_at = ? WHERE id = ?",
                        (SISTEMICO, _ahora(), job))
    db_conn.commit()

    assert lotes._decidir_parada(db_conn, LOTE, marcha[-1]) == (MOTIVO, cola)
    # Las mismas puntas siguen en cola (la primera aún no ha escrito): la segunda no decide nada.
    assert lotes._decidir_parada(db_conn, LOTE, marcha[-2]) is None


# ---------------------------------------------------------------------------
# «Una por lote»: el resumen lo cuenta y no hay otro aviso
# ---------------------------------------------------------------------------

def test_por_lote_el_resumen_dice_que_se_paro(db_conn, retiradas):
    _modo(db_conn, "por_lote")
    marcha, cola = _lote(db_conn, en_marcha=5, en_cola=2)
    for job in marcha:
        uq._fail(job, SISTEMICO)

    assert _estados(db_conn, cola) == ["cancelled"] * 2
    avisos = _avisos(db_conn)
    assert [a["event_type"] for a in avisos] == ["upload_batch_done"]
    cuerpo = avisos[0]["body"].split("\n")
    assert cuerpo[0] == "7 subidas, 0 completadas, 5 fallidas, 2 canceladas."
    assert cuerpo[1] == f"{PARADO}. 2 subidas no llegaron a empezar; «Reintentar fallidas» las relanza."
    assert avisos[0]["level"] == "error"


def test_por_lote_con_una_aun_subiendo_el_resumen_espera_y_lo_cuenta(db_conn, retiradas):
    _modo(db_conn, "por_lote")
    marcha, cola = _lote(db_conn, en_marcha=6, en_cola=1)
    for job in marcha[:5]:
        uq._fail(job, SISTEMICO)
    assert _estados(db_conn, cola) == ["cancelled"]
    assert _avisos(db_conn) == [], "con una subiendo, el lote aún no ha terminado"

    _completar(db_conn, marcha[5])
    from emuwarez_uploadrr.services.upload_execution import _notify_upload_completed
    _notify_upload_completed(marcha[5], None)

    avisos = _avisos(db_conn)
    assert [a["event_type"] for a in avisos] == ["upload_batch_done"]
    assert f"{PARADO}. 1 subida no llegó a empezar; «Reintentar fallidas» la relanza." in avisos[0]["body"]


# ---------------------------------------------------------------------------
# «Reintentar fallidas» relanza las paradas; reiniciar no frena
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _biblioteca_en_tmp(tmp_path, monkeypatch):
    from emuwarez_uploadrr.services import uploadrr_contract
    monkeypatch.setattr(uploadrr_contract, "DEFAULT_ALLOWED_ROOTS", [str(tmp_path)])


def _peli(conn, tmp_path, titulo: str) -> int:
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


def test_reintentar_fallidas_relanza_las_paradas_y_el_freno_vuelve_a_valer(db_conn, tmp_path, retiradas):
    ids = []
    for t in "ABCDEFG":
        r = uq.queue_upload_for_item(_peli(db_conn, tmp_path, t), lote_id=LOTE, conn=db_conn)
        assert r["status"] == "queued", r
        ids.append(r["job"]["id"])
    for job in ids[:5]:
        uq._fail(job, SISTEMICO)
    assert _estados(db_conn, ids[5:]) == ["cancelled"] * 2

    hecho = lotes.reintentar_fallidas(db_conn, LOTE)

    assert (hecho["reintentadas"], hecho["saltadas"]) == (7, [])
    nuevas = [dict(f) for f in db_conn.execute(
        "SELECT id, retry_of_job_id, lote_id, status FROM upload_jobs WHERE retry_of_job_id IS NOT NULL ORDER BY id")]
    assert [(n["retry_of_job_id"], n["lote_id"], n["status"]) for n in nuevas] == [(j, LOTE, "queued") for j in ids]
    resumen = lotes.resumen_de_lote(db_conn, LOTE)
    assert (resumen["en_cola"], resumen["parado"], resumen["paradas"]) == (7, None, 0)

    # Los reintentos son puntas nuevas: si la racha vuelve, el lote se para otra vez.
    for n in nuevas[:5]:
        uq._fail(n["id"], SISTEMICO)
    assert _estados(db_conn, [n["id"] for n in nuevas[5:]]) == ["cancelled"] * 2
    assert len(_avisos(db_conn, "Lote parado")) == 2


def test_reiniciar_la_aplicacion_no_frena(db_conn, retiradas):
    marcha, cola = _lote(db_conn, en_marcha=5, en_cola=2)
    for job in marcha[:4]:
        uq._fail(job, SISTEMICO)
    corriendo = _trabajo(db_conn, titulo="R")

    assert uq.reconcile_interrupted_jobs(db_conn) == 4  # marcha[4], corriendo y las dos de la cola

    filas = [_fila(db_conn, j) for j in cola]
    assert [(f["status"], f["stage"]) for f in filas] == [("failed", "failed")] * 2
    assert all(re.match("Interrumpido", f["error_message"]) for f in filas)
    assert _avisos(db_conn, "Lote parado") == []
    assert retiradas == []
    assert lotes.resumen_de_lote(db_conn, LOTE)["parado"] is None
    assert _fila(db_conn, corriendo)["status"] == "failed"


def test_la_api_del_lote_dice_si_se_paro(client, auth_headers, db_conn, retiradas):
    marcha, _cola = _lote(db_conn, en_marcha=5, en_cola=2)
    for job in marcha:
        uq._fail(job, SISTEMICO)
    datos = client.get(f"/api/uploads/lotes/{LOTE}", headers=auth_headers).json()
    assert (datos["parado"], datos["paradas"], datos["canceladas"]) == (PARADO, 2, 2)


def test_el_freno_nunca_lanza(db_conn, monkeypatch):
    def roto(*a, **kw):
        raise RuntimeError("base rota")
    monkeypatch.setattr(lotes, "_decidir_parada", roto)
    _trabajo(db_conn, status="failed")
    assert lotes.frenar_si_fallo_sistemico(1) == 0
    assert lotes.frenar_si_fallo_sistemico(999) == 0
