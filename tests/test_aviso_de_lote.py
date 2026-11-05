"""El aviso de un lote (Ajustes → Notificaciones → «Notificaciones de un lote», pregunta 5 de
docs/PLAN_SUBIDA_POR_LOTES.md).

Con «Una por subida» (por defecto) todo avisa como siempre. Con «Una por lote», las subidas de un lote no avisan una a
una y, cuando la última punta del lote llega a un estado final, sale UNA notificación `upload_batch_done` con el
resumen. Las sueltas avisan siempre.
"""
from __future__ import annotations

import threading

import pytest

from emuwarez_uploadrr.services import lotes
from emuwarez_uploadrr.services import notification_center
from emuwarez_uploadrr.services.upload_execution import (
    _notify_upload_completed,
    _notify_upload_failed,
    cancel_upload_job,
)

LOTE = "0123456789ab"


@pytest.fixture
def db_conn(isolated_db):
    """La misma base que abren los servicios (connect() sin ruta)."""
    from emuwarez_uploadrr.database import connect, db_path, init_db
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _trabajo(conn, *, status: str = "running", lote_id: str | None = LOTE, titulo: str = "Peli",
             reintenta: int | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO upload_jobs (title, path, status, stage, lote_id, retry_of_job_id, created_at, updated_at)
           VALUES (?, '/x', ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (titulo, status, status, lote_id, reintenta),
    )
    conn.commit()
    return cur.lastrowid


def _poner(conn, job_id: int, estado: str) -> None:
    conn.execute("UPDATE upload_jobs SET status = ?, stage = ? WHERE id = ?", (estado, estado, job_id))
    conn.commit()


def _modo(conn, modo: str) -> None:
    from emuwarez_uploadrr.services.settings import escribir_ajuste
    escribir_ajuste(conn, "notify_lote_modo", modo)
    conn.commit()


def _avisos(conn, tipo: str | None = None) -> list[dict]:
    filas = conn.execute("SELECT * FROM notifications ORDER BY id").fetchall()
    return [dict(f) for f in filas if tipo is None or f["event_type"] == tipo]


def _terminar(conn, job_id: int, estado: str) -> None:
    """Lo que hace la ejecución: escribir el estado final y después avisar."""
    _poner(conn, job_id, estado)
    if estado == "completed":
        _notify_upload_completed(job_id, "https://emu-warez.com/torrents/1")
    else:
        _notify_upload_failed(job_id, "falló")


# ---------------------------------------------------------------------------
# El ajuste
# ---------------------------------------------------------------------------

def test_el_ajuste_va_por_subida_de_fabrica_y_se_guarda(client, auth_headers):
    assert client.get("/api/settings", headers=auth_headers).json()["notify_lote_modo"] == "por_subida"

    resp = client.put("/api/settings", json={"notify_lote_modo": "por_lote"}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["notify_lote_modo"] == "por_lote"
    assert client.get("/api/settings", headers=auth_headers).json()["notify_lote_modo"] == "por_lote"

    malo = client.put("/api/settings", json={"notify_lote_modo": "a_veces"}, headers=auth_headers)
    assert malo.status_code == 422
    assert client.get("/api/settings", headers=auth_headers).json()["notify_lote_modo"] == "por_lote"


def test_el_tipo_nuevo_sale_en_la_matriz_de_cada_canal(client, auth_headers):
    datos = client.get("/api/settings", headers=auth_headers).json()
    assert {"code": "upload_batch_done", "label": "Lote de subidas terminado"} in datos["notify_event_types"]
    # Sin configurar, todos los canales lo reciben, como el resto.
    for canal in ("ui", "discord", "telegram"):
        assert "upload_batch_done" in datos[f"notify_{canal}_events"]
    # Y se puede desmarcar como cualquier otro.
    client.put("/api/settings", json={"notify_discord_events": ["upload_completed"]}, headers=auth_headers)
    assert client.get("/api/settings", headers=auth_headers).json()["notify_discord_events"] == ["upload_completed"]


# ---------------------------------------------------------------------------
# «Una por subida»: como siempre
# ---------------------------------------------------------------------------

def test_por_subida_cada_trabajo_del_lote_avisa_y_el_lote_no(db_conn):
    a, b = _trabajo(db_conn, titulo="A"), _trabajo(db_conn, titulo="B")
    _terminar(db_conn, a, "completed")
    _terminar(db_conn, b, "failed")

    assert [n["event_type"] for n in _avisos(db_conn)] == ["upload_completed", "upload_failed"]
    assert not lotes.avisar_si_lote_terminado(LOTE)
    assert not _avisos(db_conn, "upload_batch_done")


def test_por_subida_cancelar_el_lote_no_avisa(db_conn, monkeypatch):
    from emuwarez_uploadrr.services import upload_queue
    monkeypatch.setattr(upload_queue, "retirar_de_la_cola", lambda job_id: None)
    _trabajo(db_conn, status="completed")
    _trabajo(db_conn, status="queued")
    lotes.cancelar_lote(db_conn, LOTE)
    assert _avisos(db_conn) == []


# ---------------------------------------------------------------------------
# «Una por lote»
# ---------------------------------------------------------------------------

def test_por_lote_calla_las_del_lote_y_avisa_una_vez_al_terminar_la_ultima(db_conn):
    _modo(db_conn, "por_lote")
    a, b, c = (_trabajo(db_conn, titulo=t) for t in ("A", "B", "C"))

    _terminar(db_conn, a, "completed")
    _terminar(db_conn, b, "failed")
    assert _avisos(db_conn) == [], "una subida del lote ha avisado sola, o el lote ha avisado antes de terminar"

    _terminar(db_conn, c, "completed")
    avisos = _avisos(db_conn)
    assert len(avisos) == 1
    aviso = avisos[0]
    assert aviso["event_type"] == "upload_batch_done"
    assert aviso["title"] == "Lote terminado"
    assert aviso["body"].startswith("3 subidas, 2 completadas, 1 fallida, 0 canceladas.")
    assert "Fallidas: «B»." in aviso["body"]
    assert f"Lote {LOTE}." in aviso["body"]
    assert aviso["level"] == "warning"
    # La campana abre Subidas filtrada por el lote: el lote_id va en entity_id.
    assert (aviso["entity_type"], aviso["entity_id"]) == ("upload_lote", int(LOTE, 16))
    assert format(aviso["entity_id"], "012x") == LOTE

    # Llamarlo otra vez (otra notificación tardía del mismo lote) no repite.
    assert not lotes.avisar_si_lote_terminado(LOTE)
    _notify_upload_failed(b, "otra vez")
    assert len(_avisos(db_conn)) == 1


def test_por_lote_las_sueltas_avisan_como_siempre(db_conn):
    _modo(db_conn, "por_lote")
    suelta = _trabajo(db_conn, lote_id=None, titulo="Suelta")
    otra = _trabajo(db_conn, lote_id=None, titulo="Otra")
    _terminar(db_conn, suelta, "completed")
    _terminar(db_conn, otra, "failed")
    assert [(n["event_type"], n["entity_id"]) for n in _avisos(db_conn)] == [
        ("upload_completed", suelta), ("upload_failed", otra)]


def test_por_lote_un_lote_que_se_quedo_en_uno_avisa_como_una_suelta(db_conn):
    """Subidas solo agrupa un lote de más de un elemento; uno solo avisa como una suelta, con su póster y su enlace."""
    _modo(db_conn, "por_lote")
    solo = _trabajo(db_conn)
    _terminar(db_conn, solo, "completed")
    assert [n["event_type"] for n in _avisos(db_conn)] == ["upload_completed"]


def test_el_nivel_del_aviso_sigue_al_resultado(db_conn):
    _modo(db_conn, "por_lote")
    casos = [
        (("completed", "completed"), "success", "2 subidas, 2 completadas, 0 fallidas, 0 canceladas."),
        (("failed", "failed"), "error", "2 subidas, 0 completadas, 2 fallidas, 0 canceladas."),
        (("completed", "cancelled"), "warning", "2 subidas, 1 completada, 0 fallidas, 1 cancelada."),
        (("cancelled", "cancelled"), "info", "2 subidas, 0 completadas, 0 fallidas, 2 canceladas."),
    ]
    for i, (estados, nivel, cuerpo) in enumerate(casos):
        lote = f"{i:012x}"
        for e in estados:
            _trabajo(db_conn, status=e, lote_id=lote)
        assert lotes.avisar_si_lote_terminado(lote)
        aviso = _avisos(db_conn, "upload_batch_done")[-1]
        assert (aviso["level"], aviso["body"].split("\n")[0]) == (nivel, cuerpo)


def test_los_titulos_de_las_fallidas_se_cortan(db_conn):
    _modo(db_conn, "por_lote")
    for i in range(7):
        _trabajo(db_conn, status="failed", titulo=f"T{i}")
    assert lotes.avisar_si_lote_terminado(LOTE)
    cuerpo = _avisos(db_conn)[0]["body"]
    assert "Fallidas: «T0», «T1», «T2», «T3», «T4» y 2 más." in cuerpo


def test_reintentar_las_fallidas_vuelve_a_avisar_y_cuenta_cada_elemento_una_vez(db_conn):
    _modo(db_conn, "por_lote")
    a, b, c = (_trabajo(db_conn, titulo=t) for t in ("A", "B", "C"))
    _terminar(db_conn, a, "completed")
    _terminar(db_conn, b, "failed")
    _terminar(db_conn, c, "failed")
    assert len(_avisos(db_conn, "upload_batch_done")) == 1

    # «Reintentar fallidas»: los reintentos son filas nuevas del mismo lote, que pasan a ser las puntas.
    rb = _trabajo(db_conn, status="queued", titulo="B", reintenta=b)
    rc = _trabajo(db_conn, status="queued", titulo="C", reintenta=c)
    _terminar(db_conn, rb, "completed")
    assert len(_avisos(db_conn, "upload_batch_done")) == 1, "ha avisado con un reintento aún en marcha"
    _terminar(db_conn, rc, "failed")

    avisos = _avisos(db_conn, "upload_batch_done")
    assert len(avisos) == 2
    assert avisos[1]["body"].startswith("3 subidas, 2 completadas, 1 fallida, 0 canceladas.")
    assert "Fallidas: «C»." in avisos[1]["body"]
    assert not _avisos(db_conn, "upload_completed") and not _avisos(db_conn, "upload_failed")


def test_cancelar_pendientes_cuando_ya_no_queda_nada_mas_avisa(db_conn, monkeypatch):
    from emuwarez_uploadrr.services import upload_queue
    monkeypatch.setattr(upload_queue, "retirar_de_la_cola", lambda job_id: None)
    _modo(db_conn, "por_lote")
    _trabajo(db_conn, status="completed")
    _trabajo(db_conn, status="queued")
    _trabajo(db_conn, status="queued")

    assert lotes.cancelar_lote(db_conn, LOTE)["canceladas"] == 2
    avisos = _avisos(db_conn)
    assert [n["event_type"] for n in avisos] == ["upload_batch_done"]
    assert avisos[0]["body"].startswith("3 subidas, 1 completada, 0 fallidas, 2 canceladas.")


def test_cancelar_pendientes_con_una_subiendo_espera_a_que_termine(db_conn, monkeypatch):
    from emuwarez_uploadrr.services import upload_queue
    monkeypatch.setattr(upload_queue, "retirar_de_la_cola", lambda job_id: None)
    _modo(db_conn, "por_lote")
    subiendo = _trabajo(db_conn, status="running")
    _trabajo(db_conn, status="queued")

    lotes.cancelar_lote(db_conn, LOTE)
    assert _avisos(db_conn) == []
    _terminar(db_conn, subiendo, "completed")
    avisos = _avisos(db_conn)
    assert [n["event_type"] for n in avisos] == ["upload_batch_done"]
    assert avisos[0]["body"].startswith("2 subidas, 1 completada, 0 fallidas, 1 cancelada.")


def test_cancelar_la_ultima_del_lote_desde_su_fila_avisa_del_lote(db_conn, monkeypatch):
    from emuwarez_uploadrr.services import upload_queue
    monkeypatch.setattr(upload_queue, "retirar_de_la_cola", lambda job_id: None)
    _modo(db_conn, "por_lote")
    _trabajo(db_conn, status="failed")
    en_cola = _trabajo(db_conn, status="queued")

    assert cancel_upload_job(en_cola)["ok"]
    assert [n["event_type"] for n in _avisos(db_conn)] == ["upload_batch_done"]


def test_reiniciar_no_avisa(db_conn):
    from emuwarez_uploadrr.services.upload_queue import reconcile_interrupted_jobs
    _modo(db_conn, "por_lote")
    _trabajo(db_conn, status="completed")
    _trabajo(db_conn, status="running")
    _trabajo(db_conn, status="queued")
    assert reconcile_interrupted_jobs(db_conn) == 2
    assert _avisos(db_conn) == []


def test_un_fallo_al_avisar_no_lanza(db_conn, monkeypatch):
    _modo(db_conn, "por_lote")
    _trabajo(db_conn, status="completed")
    _trabajo(db_conn, status="completed")

    def roto(*a, **kw):
        raise RuntimeError("campana rota")
    monkeypatch.setattr(notification_center, "emit", roto)
    assert lotes.avisar_si_lote_terminado(LOTE) is False
    assert lotes.avisar_si_lote_terminado("no es un lote") is False
    assert lotes.avisar_si_lote_terminado(None) is False


# ---------------------------------------------------------------------------
# Carreras: dos del mismo lote terminando a la vez dan un solo aviso
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ronda", range(5))
def test_dos_que_terminan_a_la_vez_dan_un_solo_aviso(db_conn, ronda):
    _modo(db_conn, "por_lote")
    lote = f"{ronda + 1:012x}"
    trabajos = [_trabajo(db_conn, lote_id=lote, titulo=f"T{i}") for i in range(4)]
    salida = threading.Barrier(len(trabajos))
    errores: list[BaseException] = []

    def terminar(job_id: int, estado: str) -> None:
        from emuwarez_uploadrr.database import connect
        try:
            conn = connect()
            try:
                salida.wait(timeout=5)
                _terminar(conn, job_id, estado)
            finally:
                conn.close()
        except BaseException as exc:  # noqa: BLE001 - se comprueba abajo
            errores.append(exc)

    hilos = [threading.Thread(target=terminar, args=(j, "completed" if i % 2 else "failed"))
             for i, j in enumerate(trabajos)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    assert not errores, errores

    avisos = _avisos(db_conn)
    assert [n["event_type"] for n in avisos] == ["upload_batch_done"]
    assert avisos[0]["body"].startswith("4 subidas, 2 completadas, 2 fallidas, 0 canceladas.")


def test_muchas_llamadas_a_la_vez_sobre_un_lote_terminado_avisan_una_vez(db_conn):
    _modo(db_conn, "por_lote")
    for _ in range(3):
        _trabajo(db_conn, status="completed")
    salida = threading.Barrier(8)
    resultados: list[bool] = []

    def avisar() -> None:
        salida.wait(timeout=5)
        resultados.append(lotes.avisar_si_lote_terminado(LOTE))

    hilos = [threading.Thread(target=avisar) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    assert sorted(resultados) == [False] * 7 + [True]
    assert len(_avisos(db_conn, "upload_batch_done")) == 1


# ---------------------------------------------------------------------------
# Canales: el tipo nuevo se envía o no como los demás
# ---------------------------------------------------------------------------

def _discord(conn, eventos: str | None) -> None:
    from emuwarez_uploadrr.services.settings import set_setting
    set_setting(conn, "notify.discord.enabled", "true")
    set_setting(conn, "notify.discord.webhook_url", "https://discord.com/api/webhooks/1/x")
    if eventos is not None:
        set_setting(conn, "notify.discord.events", eventos)
    conn.commit()


@pytest.mark.parametrize("eventos, enviado", [
    (None, True),                                   # sin configurar: todos
    ("upload_completed,upload_batch_done", True),
    ("upload_completed,upload_failed", False),       # desmarcado
])
def test_el_aviso_del_lote_respeta_los_eventos_de_cada_canal(db_conn, monkeypatch, eventos, enviado):
    enviados: list[str] = []
    monkeypatch.setattr(notification_center, "send_discord",
                        lambda url, mensaje, poster_url=None: enviados.append(mensaje) or {"ok": True})
    _modo(db_conn, "por_lote")
    _discord(db_conn, eventos)
    a, b = _trabajo(db_conn, titulo="A"), _trabajo(db_conn, titulo="B")
    _terminar(db_conn, a, "completed")
    _terminar(db_conn, b, "completed")

    if enviado:
        assert len(enviados) == 1
        assert enviados[0].startswith("📢 Lote terminado\n2 subidas, 2 completadas, 0 fallidas, 0 canceladas.")
    else:
        assert enviados == []
    # La campana, sin configurar, lo guarda siempre; y ninguna subida del lote ha avisado sola por ningún canal.
    assert [n["event_type"] for n in _avisos(db_conn)] == ["upload_batch_done"]
