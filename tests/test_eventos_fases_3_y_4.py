"""Los avisos del asistente y del resto de pantallas (fases 3 y 4).

Otra vez lo que importa es DESDE DÓNDE sale cada uno. Todos van sobre el único
escritor de su dato: si el aviso se pone en uno de los sitios que llaman a ese
escritor en vez de en él, hay caminos que no avisan y la pantalla se queda
parada sin que nadie sepa por qué.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import eventos


@pytest.fixture(autouse=True)
def _limpio():
    eventos.olvidar_todos()
    yield
    eventos.olvidar_todos()


def _espiar(monkeypatch, modulo) -> list:
    avisos: list = []
    monkeypatch.setattr(modulo, "publicar",
                        lambda tipo, datos=None: avisos.append((tipo, datos)) or 0)
    return avisos


# ───────────────── Fase 3: el asistente ─────────────────

def test_avanzar_las_comprobaciones_avisa(monkeypatch):
    """Era el sondeo de 0,5 s, y encima disparaba justo mientras el servidor
    estaba ocupado verificando."""
    from emuwarez_uploadrr.services import upload_checks

    avisos = _espiar(monkeypatch, upload_checks)
    upload_checks._set_checks_progress(42, checks=[{"key": "a"}], done=False)
    upload_checks._set_checks_progress(42, checks=[{"key": "a"}, {"key": "b"}], done=True)

    assert avisos == [
        ("comprobaciones-progreso", {"item_id": 42, "done": False}),
        ("comprobaciones-progreso", {"item_id": 42, "done": True}),
    ]


def test_el_plan_de_temporada_avisa_por_capitulo(monkeypatch):
    """No se agrupa a propósito: el asistente enseña el título del capítulo que
    va, y agrupar se saltaría nombres. Cada capítulo cuesta lo suyo, así que la
    frecuencia la marca el trabajo real y no un bucle."""
    from emuwarez_uploadrr.services import season_pack

    avisos = _espiar(monkeypatch, season_pack)
    for i in (1, 2, 3):
        season_pack._set_season_plan_progress(7, done=i, total=3, current_title=f"Cap {i}")

    assert [a[1]["done"] for a in avisos] == [1, 2, 3]
    assert all(a[0] == "plan-temporada-progreso" and a[1]["season_id"] == 7 for a in avisos)


def test_el_progreso_del_plan_se_lee_igual_que_antes(monkeypatch):
    """Avisar no puede haber cambiado lo que devuelve el sondeo, porque sigue
    siendo lo que se pide al recibir el aviso."""
    from emuwarez_uploadrr.services import season_pack

    _espiar(monkeypatch, season_pack)
    season_pack._set_season_plan_progress(7, done=2, total=5, current_title="Cap 2")
    assert season_pack.get_season_plan_progress(7) == {
        "done": 2, "total": 5, "current_title": "Cap 2"}


# ───────────────── Fase 4: campana, tareas, sync ─────────────────

def test_una_notificacion_avisa(monkeypatch, client):
    """La campana sondeaba cada 30 s: una notificación podía tardar medio
    minuto en salir."""
    from emuwarez_uploadrr.database import connect, db_path, init_db
    from emuwarez_uploadrr.services import notification_center

    avisos = _espiar(monkeypatch, notification_center)
    conn = connect(db_path()); init_db(conn)
    try:
        notification_center.emit(conn, "upload_completed", "Subida lista", dispatch=False)
    finally:
        conn.close()

    assert avisos and avisos[0][0] == "notificacion"
    assert avisos[0][1]["event_type"] == "upload_completed"


def test_si_la_campana_esta_apagada_no_se_avisa(monkeypatch, client):
    """No se avisa de lo que no se ha guardado: si el canal UI está apagado no
    hay nada nuevo que enseñar."""
    from emuwarez_uploadrr.database import connect, db_path, init_db
    from emuwarez_uploadrr.services import notification_center

    avisos = _espiar(monkeypatch, notification_center)
    monkeypatch.setattr(notification_center, "_ui_stores", lambda conn, evento: False)
    conn = connect(db_path()); init_db(conn)
    try:
        notification_center.emit(conn, "upload_completed", "Subida lista", dispatch=False)
    finally:
        conn.close()

    assert avisos == []


def test_una_tarea_que_termina_avisa(monkeypatch, client):
    """Aquí termina TODA tarea, la lance el reloj o el botón de Ejecutar
    ahora."""
    from emuwarez_uploadrr.database import connect, db_path, init_db
    from emuwarez_uploadrr.services import scheduler

    avisos = _espiar(monkeypatch, scheduler)
    monkeypatch.setitem(scheduler._EXECUTORS, "sync-library",
                        lambda conn: ("completed", "hecho"))
    conn = connect(db_path()); init_db(conn)
    try:
        scheduler.ensure_default_tasks(conn)
        scheduler.run_scheduled_task(conn, "sync-library", manual=True)
    finally:
        conn.close()

    assert ("tarea-terminada", {"task_key": "sync-library", "status": "completed"}) in avisos


def test_una_tarea_que_falla_tambien_avisa(monkeypatch, client):
    """La tabla tiene que enseñar el fallo, no quedarse con lo de antes."""
    from emuwarez_uploadrr.database import connect, db_path, init_db
    from emuwarez_uploadrr.services import scheduler

    avisos = _espiar(monkeypatch, scheduler)

    def _revienta(conn):
        raise RuntimeError("se cayó Sonarr")

    monkeypatch.setitem(scheduler._EXECUTORS, "sync-library", _revienta)
    conn = connect(db_path()); init_db(conn)
    try:
        scheduler.ensure_default_tasks(conn)
        scheduler.run_scheduled_task(conn, "sync-library", manual=True)
    finally:
        conn.close()

    assert [a for a in avisos if a[1]["status"] == "failed"]


def test_empezar_una_sync_avisa(monkeypatch):
    """La barra de arriba tiene que APARECER al empezar. Eso se descubría con
    un sondeo cada 8 s por si la había lanzado otra pestaña o una tarea."""
    from emuwarez_uploadrr.services import library

    avisos = _espiar(monkeypatch, library)
    with library._lib_sync_guard():
        pass

    assert [a[0] for a in avisos] == ["sync-empezada", "sync-terminada"]


def test_si_ya_hay_una_corriendo_no_se_avisa_de_otra(monkeypatch):
    """Dos avisos de arranque harían aparecer la barra dos veces para una sola
    sincronización."""
    from emuwarez_uploadrr.services import library

    with library._lib_sync_guard():
        avisos = _espiar(monkeypatch, library)
        with pytest.raises(library.SyncAlreadyRunning):
            with library._lib_sync_guard():
                pass
        assert avisos == []


# ─────────────────────────────────────────────────────────────────────────────
# El inventario de sondeos, para que no vuelva a crecer sin querer
# ─────────────────────────────────────────────────────────────────────────────

import pathlib
import re

FRONT = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"

# Los que quedan preguntando al servidor por su cuenta, y por qué. Todos son
# ahora redes de seguridad para cuando el canal de avisos está caído, salvo el
# del estado del sistema, que no puede ser otra cosa.
SONDEOS_ESPERADOS = {
    "components/SystemStatusPanel.tsx": (
        "CPU/RAM/disco no cambian en ningún instante concreto: se miden cuando "
        "alguien mira. No hay nada que el servidor pueda anunciar."
    ),
    "context/SyncContext.tsx": "red de seguridad del aviso sync-empezada",
    "hooks/useRefrescoPorAvisos.ts": "la red de seguridad de las pantallas",
    "api/eventos.ts": "la red de seguridad del asistente (seguirProgreso)",
    "components/UploadJobDetailPage.tsx": "recarga del registro tras una acción",
    "pages/LogsPage.tsx": (
        "lo enciende el usuario con el interruptor de auto-refresco, y solo "
        "corre mientras está mirando esa pantalla. Pedirlo es la intención."
    ),
    "pages/DashboardPage.tsx": (
        "red de seguridad general del Panel a 15 s. Lo que de verdad se mueve "
        "(subidas, sincronizaciones) ya llega por aviso."
    ),
}

# Temporizadores que NO preguntan nada al servidor: relojes de pantalla, cuentas
# atrás. No tienen nada que ver con esto.
RELOJES = {
    "pages/TasksPage.tsx", "utils/uploadStatus.ts", "hooks/useCooldown.ts",
}


def test_no_han_aparecido_sondeos_nuevos():
    """Que un sondeo vuelva a entrar sin querer es fácil y no da la cara: la
    pantalla funciona igual, solo que preguntando cada dos segundos para nada.
    Este test obliga a decidirlo a propósito."""
    con_temporizador = set()
    for f in FRONT.rglob("*.ts*"):
        if "__tests__" in f.parts:
            continue
        if re.search(r"\bsetInterval\s*\(", f.read_text()):
            con_temporizador.add(str(f.relative_to(FRONT)))

    inesperados = con_temporizador - set(SONDEOS_ESPERADOS) - RELOJES
    assert not inesperados, (
        f"Sondeos nuevos sin declarar: {sorted(inesperados)}.\n"
        "Si de verdad hace falta preguntar cada pocos segundos, añádelo a "
        "SONDEOS_ESPERADOS con el motivo. Si no, mira services/eventos.py: "
        "seguramente el servidor pueda avisar."
    )
