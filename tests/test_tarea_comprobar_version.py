"""La comprobación de versión, como tarea programada.

Corre cada hora, aparece en "Últimas tareas ejecutadas" del Panel y avisa por
la campana cuando hay una imagen más nueva. Lo que más importa probar es que
NO avisa cada hora: mientras no actualices, la tarea sigue corriendo y
diciéndolo en su resumen, pero la notificación se manda una sola vez por
versión.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services import scheduler
from emuwarez_uploadrr.services.notification_center import (
    EVENT_TYPES, SOLO_UI_POR_DEFECTO, channel_events, list_notifications,
)


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(db_path()); init_db(conn)
    scheduler.ensure_default_tasks(conn); conn.commit()
    yield conn
    conn.close()


def _version(monkeypatch, estado, commit="nuevo111", notas="algo nuevo"):
    monkeypatch.setattr(
        "emuwarez_uploadrr.services.version_info.estado_de_version",
        lambda **kw: {
            "version": "0.2.0", "commit": "viejo000", "commit_corto": "viejo00",
            "construida": "2026-08-01", "digest": None, "estado": estado, "motivo":
            "sin manifiesto" if estado == "desconocido" else None,
            "ultima": {"commit": commit, "commit_corto": commit[:7], "digest": "sha256:x",
                       "publicada": "2026-08-02", "notas": notas, "version": "0.3.0"},
        })


def test_la_tarea_existe_y_corre_cada_hora(db_conn):
    tarea = scheduler.get_scheduled_task(db_conn, scheduler.TASK_CHECK_VERSION)
    assert tarea is not None
    assert tarea["interval_minutes"] == 60
    assert tarea["manual_allowed"] == 1


def test_aparece_en_ultimas_tareas_ejecutadas(db_conn, monkeypatch):
    from emuwarez_uploadrr.services.tasks import list_tasks

    _version(monkeypatch, "al_dia")
    scheduler.run_scheduled_task(db_conn, scheduler.TASK_CHECK_VERSION, manual=True)

    ejecuciones = [t for t in list_tasks(db_conn, limit=10)
                   if t["name"] == scheduler.TASK_CHECK_VERSION]
    assert ejecuciones, "la tarea no ha dejado constancia en task_runs"
    assert ejecuciones[0]["status"] == "completed"
    assert "Al día" in (ejecuciones[0]["summary"] or "")


def test_avisa_una_sola_vez_por_version(db_conn, monkeypatch):
    """El caso que importa: la tarea corre cada hora y el aviso no se repite."""
    _version(monkeypatch, "hay_novedad", commit="nuevo111")

    r1 = scheduler.run_scheduled_task(db_conn, scheduler.TASK_CHECK_VERSION, manual=True)
    assert "avisado" in r1["summary"]
    aviso = [n for n in list_notifications(db_conn) if n["event_type"] == "version_available"][0]
    # Una sola línea, con el número de versión y sin instrucciones.
    assert aviso["title"] == "Hay una versión más nueva: v0.3.0"
    assert not aviso["body"]
    assert len([n for n in list_notifications(db_conn) if n["event_type"] == "version_available"]) == 1

    # Segunda hora, misma versión: sigue diciendo que hay novedad, sin avisar.
    r2 = scheduler.run_scheduled_task(db_conn, scheduler.TASK_CHECK_VERSION, manual=True)
    assert "ya avisado" in r2["summary"]
    assert len([n for n in list_notifications(db_conn) if n["event_type"] == "version_available"]) == 1

    # Se publica OTRA versión: vuelve a avisar.
    _version(monkeypatch, "hay_novedad", commit="masnuevo222")
    scheduler.run_scheduled_task(db_conn, scheduler.TASK_CHECK_VERSION, manual=True)
    assert len([n for n in list_notifications(db_conn) if n["event_type"] == "version_available"]) == 2


def test_sin_manifiesto_no_es_un_fallo(db_conn, monkeypatch):
    """No poder comparar no es que la tarea falle: es que no hay con qué."""
    _version(monkeypatch, "desconocido")
    r = scheduler.run_scheduled_task(db_conn, scheduler.TASK_CHECK_VERSION, manual=True)
    assert r["status"] == "skipped"
    assert not [n for n in list_notifications(db_conn) if n["event_type"] == "version_available"]


def test_por_defecto_va_a_la_campana_pero_no_a_los_bots(db_conn):
    assert "version_available" in EVENT_TYPES
    assert "version_available" in SOLO_UI_POR_DEFECTO
    # Sin configurar ningún canal, que es una instalación nueva:
    assert "version_available" in channel_events(db_conn, "ui")
    assert "version_available" not in channel_events(db_conn, "discord")
    assert "version_available" not in channel_events(db_conn, "telegram")


def test_quien_ya_tenia_notificaciones_configuradas_lo_recibe_en_la_campana(db_conn):
    """La migración del esquema 38: una lista guardada es cerrada, y el evento
    nuevo se habría quedado fuera."""
    from emuwarez_uploadrr.database import _migrate_ui_recibe_aviso_de_version

    db_conn.execute("INSERT OR REPLACE INTO settings(key,value) "
                    "VALUES ('notify.ui.events','upload_completed,upload_failed')")
    db_conn.execute("INSERT OR REPLACE INTO settings(key,value) "
                    "VALUES ('notify.discord.events','upload_completed')")
    db_conn.commit()

    _migrate_ui_recibe_aviso_de_version(db_conn); db_conn.commit()

    assert "version_available" in channel_events(db_conn, "ui")
    assert "version_available" not in channel_events(db_conn, "discord")
