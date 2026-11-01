"""La tarea nocturna «Mantenimiento»: poda lo antiguo y no toca nada que una subida enlace.

F7 de la revisión de 2026-10-31.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services import maintenance_service as mant
from emuwarez_uploadrr.services.scheduler import (
    DEFAULT_TASKS,
    TASK_MAINTENANCE,
    get_scheduled_task,
    run_scheduled_task,
)

AHORA = datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc)


def _hace(dias: int, formato: str = "%Y-%m-%d %H:%M:%S") -> str:
    return (AHORA - timedelta(days=dias)).strftime(formato)


@pytest.fixture
def conn(isolated_db):
    c = connect(db_path())
    init_db(c)
    yield c
    c.close()


def _tarea(conn, nombre, estado, dias):
    conn.execute(
        "INSERT INTO task_runs(name, status, started_at, summary) VALUES (?, ?, ?, 'x')",
        (nombre, estado, _hace(dias)),
    )


def _subida(conn, estado, dias, lineas):
    """Una subida con `lineas` líneas de registro; devuelve su id."""
    job_id = conn.execute(
        "INSERT INTO upload_jobs(title, path, status, updated_at) VALUES ('t', '/p', ?, ?)",
        (estado, _hace(dias, "%Y-%m-%dT%H:%M:%S+00:00")),
    ).lastrowid
    conn.executemany(
        "INSERT INTO upload_job_logs(upload_job_id, level, message, stream, created_at, sequence) "
        "VALUES (?, 'info', ?, 'system', 'x', ?)",
        [(job_id, f"línea {n}", n) for n in range(1, lineas + 1)],
    )
    return job_id


def _lineas(conn, job_id):
    return [r[0] for r in conn.execute(
        "SELECT sequence FROM upload_job_logs WHERE upload_job_id = ? ORDER BY sequence", (job_id,))]


def _aviso(conn, dias, leido):
    conn.execute(
        "INSERT INTO notifications(event_type, title, created_at, read_at) VALUES ('x', 't', ?, ?)",
        (_hace(dias, "%Y-%m-%dT%H:%M:%SZ"), "2026-01-01T00:00:00Z" if leido else None),
    )


# ---------------------------------------------------------------------------
# Historial de tareas
# ---------------------------------------------------------------------------

def test_se_borran_las_ejecuciones_viejas_y_no_las_recientes(conn):
    _tarea(conn, "sync-library", "completed", 200)
    _tarea(conn, "sync-library", "failed", 100)
    _tarea(conn, "sync-library", "completed", 10)
    _tarea(conn, "sync-library", "completed", 1)

    assert mant.podar_tareas(conn, 90, AHORA) == 2

    assert [r[0] for r in conn.execute("SELECT status FROM task_runs ORDER BY id")] == ["completed", "completed"]


def test_de_cada_tarea_queda_siempre_la_ultima_y_la_ultima_completada(conn):
    """De ahí salen «última sincronización» y el diagnóstico: una tarea parada meses no se queda sin ellas."""
    _tarea(conn, "sync-library", "completed", 400)
    _tarea(conn, "sync-library", "completed", 300)  # la última completada
    _tarea(conn, "sync-library", "failed", 200)
    _tarea(conn, "sync-library", "failed", 150)     # la última
    _tarea(conn, "check-version", "completed", 500)  # única de su tarea: es la última

    assert mant.podar_tareas(conn, 90, AHORA) == 2

    assert sorted((r[0], r[1]) for r in conn.execute("SELECT name, status FROM task_runs")) == [
        ("check-version", "completed"), ("sync-library", "completed"), ("sync-library", "failed")]


def test_el_corte_cuenta_dias_y_vale_con_las_dos_formas_de_fecha(conn):
    for dias, formato in ((95, "%Y-%m-%d %H:%M:%S"), (91, "%Y-%m-%dT%H:%M:%S+00:00"),
                          (89, "%Y-%m-%dT%H:%M:%S+00:00"), (1, "%Y-%m-%d %H:%M:%S")):
        conn.execute("INSERT INTO task_runs(name, status, started_at) VALUES ('a', 'failed', ?)", (_hace(dias, formato),))

    assert mant.podar_tareas(conn, 90, AHORA) == 2  # las de 95 y 91 días; la de 89 y la última se quedan


# ---------------------------------------------------------------------------
# Registro de subidas
# ---------------------------------------------------------------------------

def test_una_subida_completada_vieja_queda_en_sus_ultimas_lineas(conn):
    job = _subida(conn, "completed", 60, 500)

    assert mant.recortar_registros_de_subidas(conn, 30, 200, AHORA) == 300

    assert _lineas(conn, job) == list(range(301, 501))


def test_las_canceladas_tambien_se_recortan(conn):
    job = _subida(conn, "cancelled", 60, 50)
    mant.recortar_registros_de_subidas(conn, 30, 20, AHORA)
    assert _lineas(conn, job) == list(range(31, 51))


def test_el_registro_de_una_fallida_se_conserva_entero(conn):
    job = _subida(conn, "failed", 400, 500)
    assert mant.recortar_registros_de_subidas(conn, 30, 200, AHORA) == 0
    assert len(_lineas(conn, job)) == 500


@pytest.mark.parametrize("estado", ["queued", "staging", "preparing", "running"])
def test_el_registro_de_una_subida_viva_no_se_toca_por_vieja_que_sea(conn, estado):
    job = _subida(conn, estado, 400, 500)
    assert mant.recortar_registros_de_subidas(conn, 30, 200, AHORA) == 0
    assert len(_lineas(conn, job)) == 500


def test_una_subida_reciente_conserva_todo_su_registro(conn):
    job = _subida(conn, "completed", 5, 500)
    assert mant.recortar_registros_de_subidas(conn, 30, 200, AHORA) == 0
    assert len(_lineas(conn, job)) == 500


def test_recortar_no_mezcla_el_registro_de_unas_subidas_con_el_de_otras(conn):
    vieja = _subida(conn, "completed", 60, 300)
    otra = _subida(conn, "completed", 60, 100)  # ya cabe: no se toca
    mant.recortar_registros_de_subidas(conn, 30, 200, AHORA)
    assert len(_lineas(conn, vieja)) == 200
    assert len(_lineas(conn, otra)) == 100


# ---------------------------------------------------------------------------
# Avisos
# ---------------------------------------------------------------------------

def test_solo_se_borran_los_avisos_leidos_y_viejos(conn):
    _aviso(conn, 60, leido=True)    # se va
    _aviso(conn, 60, leido=False)   # sin leer: se queda por viejo que sea
    _aviso(conn, 5, leido=True)     # leído, pero reciente

    assert mant.podar_avisos_leidos(conn, 30, AHORA) == 1

    assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM notifications WHERE read_at IS NULL").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# La tarea entera: nada de lo que enlaza una subida
# ---------------------------------------------------------------------------

def _huella(conn) -> dict:
    return {
        t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY id")]
        for t in ("upload_jobs", "upload_artifacts", "library_items", "request_items", "operational_queue_items", "instances")
    }


def test_el_mantenimiento_no_toca_las_subidas_ni_lo_que_enlazan(conn):
    biblioteca = conn.execute(
        "INSERT INTO library_items(item_type, title, local_status, instance_type, instance_name, external_id) "
        "VALUES ('movie', 'Peli', 'Disponible', 'radarr', 'R', '1')").lastrowid
    job = _subida(conn, "completed", 400, 600)
    conn.execute("UPDATE upload_jobs SET library_item_id = ?, torrent_subido = 1 WHERE id = ?", (biblioteca, job))
    conn.execute(
        "INSERT INTO upload_artifacts(upload_job_id, artifact_type, name, created_at) VALUES (?, 'torrent', 'a', 'x')", (job,))
    fallida = _subida(conn, "failed", 400, 600)
    _tarea(conn, "sync-library", "completed", 500)
    _tarea(conn, "sync-library", "completed", 400)
    _aviso(conn, 90, leido=True)
    conn.commit()
    antes = _huella(conn)

    estado, resumen = mant.ejecutar_mantenimiento(conn, AHORA)

    assert estado == "completed"
    assert _huella(conn) == antes
    assert len(_lineas(conn, job)) == 200 and len(_lineas(conn, fallida)) == 600
    assert conn.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0] == 1
    assert "1 ejecuciones de tareas" in resumen and "400 líneas de registro de subidas" in resumen and "1 avisos leídos" in resumen


def test_un_paso_que_falla_no_impide_los_demas(conn):
    _aviso(conn, 90, leido=True)
    _tarea(conn, "a", "completed", 400)
    _tarea(conn, "a", "completed", 300)
    conn.commit()
    with patch.object(mant, "podar_tareas", side_effect=sqlite3.OperationalError("database is locked")):
        estado, resumen = mant.ejecutar_mantenimiento(conn, AHORA)

    assert estado == "failed"
    assert "database is locked" in resumen and "1 avisos leídos" in resumen
    assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0


def test_si_optimizar_falla_el_resumen_lo_dice(conn):
    with patch.object(mant, "optimizar_base", side_effect=sqlite3.OperationalError("disk I/O error")):
        estado, resumen = mant.ejecutar_mantenimiento(conn, AHORA)
    assert estado == "failed" and "optimizar: disk I/O error" in resumen


def test_sin_nada_que_borrar_termina_completada(conn):
    estado, resumen = mant.ejecutar_mantenimiento(conn, AHORA)
    assert estado == "completed"
    assert "0 ejecuciones de tareas" in resumen


def test_si_una_lectura_impide_vaciar_el_wal_optimizar_dice_que_no(conn):
    conn.execute("PRAGMA busy_timeout = 0")
    lector = connect(db_path())
    lector.execute("BEGIN")
    lector.execute("SELECT COUNT(*) FROM task_runs").fetchone()
    try:
        conn.execute("INSERT INTO task_runs(name, status) VALUES ('z', 'completed')")
        conn.commit()
        assert mant.optimizar_base(conn) is False
    finally:
        lector.close()


def test_optimizar_vacia_el_wal_si_nadie_lo_impide(conn):
    conn.execute("INSERT INTO task_runs(name, status) VALUES ('z', 'completed')")
    conn.commit()
    assert mant.optimizar_base(conn) is True
    wal = db_path().with_name(db_path().name + "-wal")
    assert not wal.exists() or wal.stat().st_size == 0


# ---------------------------------------------------------------------------
# Opciones
# ---------------------------------------------------------------------------

def test_las_opciones_tienen_sus_valores_por_defecto(conn):
    assert [mant.valor_opcion(conn, c) for c in (
        "mantenimiento.dias_tareas", "mantenimiento.dias_registros",
        "mantenimiento.lineas_registro", "mantenimiento.dias_avisos", "copias.conservar")] == [90, 30, 200, 30, 7]


def test_una_opcion_guardada_manda_y_una_corrupta_vuelve_al_defecto(conn):
    mant.guardar_opciones(conn, {"mantenimiento.dias_tareas": 120})
    assert mant.valor_opcion(conn, "mantenimiento.dias_tareas") == 120
    conn.execute("UPDATE settings SET value = 'mucho' WHERE key = 'mantenimiento.dias_tareas'")
    assert mant.valor_opcion(conn, "mantenimiento.dias_tareas") == 90
    conn.execute("UPDATE settings SET value = '1' WHERE key = 'mantenimiento.dias_tareas'")
    assert mant.valor_opcion(conn, "mantenimiento.dias_tareas") == 7  # el mínimo: nunca se poda el día de ayer


@pytest.mark.parametrize("valores", [
    {"copias.conservar": 0},
    {"copias.conservar": 366},
    {"copias.conservar": True},
    {"mantenimiento.dias_tareas": 3},
    {"no.existe": 5},
])
def test_una_opcion_fuera_de_rango_se_rechaza_y_no_guarda_ninguna(conn, valores):
    with pytest.raises(ValueError):
        mant.guardar_opciones(conn, {"mantenimiento.dias_avisos": 45, **valores})
    assert mant.valor_opcion(conn, "mantenimiento.dias_avisos") == 30


# ---------------------------------------------------------------------------
# Como tarea programada
# ---------------------------------------------------------------------------

def test_mantenimiento_es_una_tarea_diaria_a_las_cuatro(conn):
    fila = next(t for t in DEFAULT_TASKS if t[0] == TASK_MAINTENANCE)
    assert (fila[1], fila[6]) == ("Mantenimiento", "04:00")
    assert get_scheduled_task(conn, TASK_MAINTENANCE)["run_at"] == "04:00"


def test_ejecutar_la_tarea_deja_su_registro_y_su_resumen(conn):
    _aviso(conn, 90, leido=True)
    conn.commit()
    run = run_scheduled_task(conn, TASK_MAINTENANCE, manual=True)

    assert run["status"] == "completed"
    assert "1 avisos leídos" in run["summary"]
    fila = conn.execute("SELECT status, summary FROM task_runs WHERE name = ?", (TASK_MAINTENANCE,)).fetchone()
    assert (fila["status"], fila["summary"]) == ("completed", run["summary"])
    assert get_scheduled_task(conn, TASK_MAINTENANCE)["last_status"] == "completed"


def test_si_el_mantenimiento_revienta_queda_failed_en_su_registro(conn):
    with patch.object(mant, "ejecutar_mantenimiento", side_effect=RuntimeError("disco lleno")):
        run = run_scheduled_task(conn, TASK_MAINTENANCE, manual=True)
    assert run["status"] == "failed" and "disco lleno" in run["summary"]
    assert conn.execute("SELECT status FROM task_runs WHERE name = ?", (TASK_MAINTENANCE,)).fetchone()[0] == "failed"
