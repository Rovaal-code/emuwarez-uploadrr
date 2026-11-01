"""Tareas a una hora fija (04:00) además de «cada N minutos», con la zona horaria de TZ.

N17 de la revisión de 2026-10-31.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from emuwarez_uploadrr.database import SCHEMA_VERSION, connect, db_path, init_db, olvidar_esquema, preparar_base
from emuwarez_uploadrr.services import scheduler
from emuwarez_uploadrr.services.scheduler import (
    TASK_EMU_SYNC,
    TASK_LIBRARY_SYNC,
    TASK_MAINTENANCE,
    claim_due_tasks,
    get_scheduled_task,
    nombre_zona_horaria,
    run_scheduled_task,
    set_task_interval,
    set_task_schedule,
    siguiente_a_hora_fija,
    zona_horaria,
)

MADRID = ZoneInfo("Europe/Madrid")


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture
def conn(isolated_db):
    c = connect(db_path())
    init_db(c)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# La cuenta de la próxima hora
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("desde, esperada", [
    (utc(2026, 7, 15, 1, 0), utc(2026, 7, 15, 2, 0)),    # verano (UTC+2): 04:00 de hoy = 02:00 UTC
    (utc(2026, 7, 15, 2, 0), utc(2026, 7, 16, 2, 0)),    # justo a la hora: la siguiente es la de mañana
    (utc(2026, 7, 15, 2, 0, 1), utc(2026, 7, 16, 2, 0)),
    (utc(2026, 7, 15, 23, 59), utc(2026, 7, 16, 2, 0)),
    (utc(2026, 1, 15, 1, 0), utc(2026, 1, 15, 3, 0)),    # invierno (UTC+1): 04:00 = 03:00 UTC
    (utc(2026, 1, 15, 3, 0), utc(2026, 1, 16, 3, 0)),
])
def test_siguiente_a_las_cuatro_en_madrid(desde, esperada):
    assert siguiente_a_hora_fija("04:00", desde, MADRID) == esperada


def test_el_cambio_de_hora_de_primavera_mueve_la_hora_en_utc():
    """El 29/03/2026 Madrid pasa a UTC+2: las 04:00 del día 28 son las 03:00 UTC y las del 29, las 02:00 UTC."""
    assert siguiente_a_hora_fija("04:00", utc(2026, 3, 28, 3, 0, 1), MADRID) == utc(2026, 3, 29, 2, 0)


def test_el_cambio_de_hora_de_otono_mueve_la_hora_en_utc():
    """El 25/10/2026 Madrid vuelve a UTC+1: las 04:00 del día 24 son las 02:00 UTC y las del 25, las 03:00 UTC."""
    assert siguiente_a_hora_fija("04:00", utc(2026, 10, 24, 2, 0, 1), MADRID) == utc(2026, 10, 25, 3, 0)


def test_una_hora_que_no_existe_ese_dia_se_resuelve_sin_romperse():
    """02:30 el 29/03/2026 no existe en Madrid (de 02:00 salta a 03:00): sale un instante posterior a «desde»."""
    r = siguiente_a_hora_fija("02:30", utc(2026, 3, 28, 12, 0), MADRID)
    assert r > utc(2026, 3, 28, 12, 0) and r - utc(2026, 3, 28, 12, 0) < timedelta(days=1)


def test_la_hora_se_cuenta_en_la_zona_pedida_no_en_utc():
    ny = ZoneInfo("America/New_York")
    assert siguiente_a_hora_fija("04:00", utc(2026, 7, 15, 0, 0), ny) == utc(2026, 7, 15, 8, 0)  # UTC-4


def test_acepta_un_desde_en_otra_zona():
    desde = datetime(2026, 7, 15, 3, 30, tzinfo=MADRID)  # = 01:30 UTC
    assert siguiente_a_hora_fija("04:00", desde, MADRID) == utc(2026, 7, 15, 2, 0)


# ---------------------------------------------------------------------------
# Zona horaria
# ---------------------------------------------------------------------------

def test_la_zona_es_la_de_tz(monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    assert zona_horaria() == ZoneInfo("America/New_York")
    assert nombre_zona_horaria() == "America/New_York"


def test_sin_tz_es_europe_madrid(monkeypatch):
    monkeypatch.delenv("TZ", raising=False)
    assert nombre_zona_horaria() == "Europe/Madrid"


@pytest.mark.parametrize("tz", ["", "No/Existe", "CET-1", "/etc/localtime", "../../x"])
def test_una_tz_que_no_vale_cae_a_europe_madrid(monkeypatch, tz):
    monkeypatch.setenv("TZ", tz)
    assert nombre_zona_horaria() == "Europe/Madrid"


def test_si_el_sistema_no_tiene_zonas_cae_a_la_hora_del_sistema(monkeypatch):
    from zoneinfo import ZoneInfoNotFoundError
    monkeypatch.setattr(scheduler, "ZoneInfo", lambda nombre: (_ for _ in ()).throw(ZoneInfoNotFoundError(nombre)))
    assert zona_horaria() is not None
    assert siguiente_a_hora_fija("04:00", utc(2026, 7, 15, 0, 0)) > utc(2026, 7, 15, 0, 0)


# ---------------------------------------------------------------------------
# Guardar el horario
# ---------------------------------------------------------------------------

def test_poner_una_hora_fija_calcula_la_proxima_y_deja_el_intervalo(conn):
    antes = get_scheduled_task(conn, TASK_EMU_SYNC)
    tarea = set_task_schedule(conn, TASK_EMU_SYNC, run_at="04:00")

    assert tarea["run_at"] == "04:00"
    assert tarea["interval_minutes"] == antes["interval_minutes"]
    proxima = datetime.fromisoformat(tarea["next_run_at"])
    assert proxima > datetime.now(timezone.utc) and proxima - datetime.now(timezone.utc) <= timedelta(days=1, hours=1)
    assert proxima.astimezone(zona_horaria()).strftime("%H:%M") == "04:00"


@pytest.mark.parametrize("hora", ["24:00", "4:00", "04:60", "04:0", "ab:cd", "04:00:00", " 04:00", "0400", "-1:00"])
def test_una_hora_mal_escrita_se_rechaza(conn, hora):
    with pytest.raises(ValueError, match="HH:MM"):
        set_task_schedule(conn, TASK_EMU_SYNC, run_at=hora)
    assert get_scheduled_task(conn, TASK_EMU_SYNC)["run_at"] is None


def test_sin_hora_ni_intervalo_se_rechaza(conn):
    with pytest.raises(ValueError, match="intervalo o una hora"):
        set_task_schedule(conn, TASK_EMU_SYNC)


def test_una_tarea_desconocida_se_rechaza(conn):
    with pytest.raises(ValueError, match="desconocida"):
        set_task_schedule(conn, "no-existe", run_at="04:00")


def test_volver_al_intervalo_borra_la_hora_y_cuenta_desde_la_ultima_ejecucion(conn):
    set_task_schedule(conn, TASK_LIBRARY_SYNC, run_at="04:00")
    ultima = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    conn.execute("UPDATE scheduled_tasks SET last_run_at = ? WHERE task_key = ?", (ultima, TASK_LIBRARY_SYNC))

    tarea = set_task_schedule(conn, TASK_LIBRARY_SYNC, interval_minutes=45)

    assert tarea["run_at"] is None and tarea["interval_minutes"] == 45
    assert datetime.fromisoformat(tarea["next_run_at"]) == datetime.fromisoformat(ultima) + timedelta(minutes=45)


def test_volver_al_intervalo_sin_haber_corrido_nunca_cuenta_desde_ahora(conn):
    set_task_schedule(conn, TASK_LIBRARY_SYNC, run_at="04:00")
    tarea = set_task_schedule(conn, TASK_LIBRARY_SYNC, interval_minutes=30)
    resto = datetime.fromisoformat(tarea["next_run_at"]) - datetime.now(timezone.utc)
    assert timedelta(minutes=29) < resto <= timedelta(minutes=30)


def test_cambiar_solo_el_intervalo_no_mueve_la_proxima_ejecucion(conn):
    """Como hasta ahora: el nuevo intervalo vale desde la siguiente vuelta."""
    get_scheduled_task(conn, TASK_LIBRARY_SYNC)  # siembra las filas
    conn.execute("UPDATE scheduled_tasks SET next_run_at = '2030-01-01T00:00:00+00:00' WHERE task_key = ?", (TASK_LIBRARY_SYNC,))
    tarea = set_task_interval(conn, TASK_LIBRARY_SYNC, 45)
    assert tarea["next_run_at"] == "2030-01-01T00:00:00+00:00" and tarea["interval_minutes"] == 45


def test_el_minimo_del_intervalo_sigue_valiendo(conn):
    with pytest.raises(ValueError, match="mínimo"):
        set_task_schedule(conn, TASK_LIBRARY_SYNC, interval_minutes=5)
    assert get_scheduled_task(conn, TASK_LIBRARY_SYNC)["interval_minutes"] == 30


def test_con_hora_fija_el_minimo_del_intervalo_no_cuenta(conn):
    """A las 04:00 de cada día no hay intervalo: no se le exige el mínimo (la de peticiones tiene 60 min)."""
    assert set_task_schedule(conn, TASK_EMU_SYNC, interval_minutes=5, run_at="04:00")["run_at"] == "04:00"


# ---------------------------------------------------------------------------
# Ejecutar y reprogramar
# ---------------------------------------------------------------------------

def _ahora_falso(monkeypatch, instante: datetime):
    monkeypatch.setattr(scheduler, "_now", lambda: instante)


def test_tras_correr_una_tarea_con_hora_fija_la_proxima_es_la_de_manana(conn, monkeypatch):
    set_task_schedule(conn, TASK_MAINTENANCE, run_at="04:00")
    _ahora_falso(monkeypatch, utc(2026, 7, 15, 2, 0, 30))  # las 04:00:30 en Madrid

    run = run_scheduled_task(conn, TASK_MAINTENANCE)

    assert run["next_run_at"] == utc(2026, 7, 16, 2, 0).isoformat()
    assert get_scheduled_task(conn, TASK_MAINTENANCE)["next_run_at"] == run["next_run_at"]


def test_ejecutar_a_mano_antes_de_la_hora_no_quita_la_de_hoy(conn, monkeypatch):
    set_task_schedule(conn, TASK_MAINTENANCE, run_at="04:00")
    _ahora_falso(monkeypatch, utc(2026, 7, 15, 0, 0))  # las 02:00 en Madrid

    run = run_scheduled_task(conn, TASK_MAINTENANCE, manual=True)

    assert run["next_run_at"] == utc(2026, 7, 15, 2, 0).isoformat()


def test_un_horario_cambiado_mientras_corre_la_tarea_no_se_pisa(conn, monkeypatch):
    """La próxima ejecución se calcula con el horario de ahora, no con el que tenía al empezar."""
    set_task_schedule(conn, TASK_MAINTENANCE, run_at="04:00")
    _ahora_falso(monkeypatch, utc(2026, 7, 15, 2, 0, 30))

    def cambia_el_horario(c):
        set_task_schedule(c, TASK_MAINTENANCE, interval_minutes=120)
        return "completed", "ok"

    with patch.dict(scheduler._EXECUTORS, {TASK_MAINTENANCE: cambia_el_horario}):
        run = run_scheduled_task(conn, TASK_MAINTENANCE)

    assert run["next_run_at"] == utc(2026, 7, 15, 4, 0, 30).isoformat()
    tarea = get_scheduled_task(conn, TASK_MAINTENANCE)
    assert tarea["run_at"] is None and tarea["next_run_at"] == run["next_run_at"]


def test_una_tarea_por_intervalo_sigue_contando_desde_que_termina(conn, monkeypatch):
    _ahora_falso(monkeypatch, utc(2026, 7, 15, 9, 0))
    with patch("emuwarez_uploadrr.services.library.sync_all", return_value={"imported": 0, "missing": 0, "errors": []}):
        run = run_scheduled_task(conn, TASK_LIBRARY_SYNC)
    assert run["next_run_at"] == utc(2026, 7, 15, 9, 30).isoformat()


def test_una_tarea_con_hora_fija_no_se_reclama_antes_de_su_hora(conn):
    set_task_schedule(conn, TASK_MAINTENANCE, run_at="04:00")
    assert TASK_MAINTENANCE not in claim_due_tasks(conn)


def test_una_tarea_con_hora_fija_se_reclama_cuando_llega_su_hora(conn):
    set_task_schedule(conn, TASK_MAINTENANCE, run_at="04:00")
    conn.execute("UPDATE scheduled_tasks SET next_run_at = ? WHERE task_key = ?",
                 ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), TASK_MAINTENANCE))
    assert TASK_MAINTENANCE in claim_due_tasks(conn)


# ---------------------------------------------------------------------------
# Migración 45
# ---------------------------------------------------------------------------

def test_una_base_del_esquema_44_gana_la_columna_y_conserva_sus_tareas(isolated_db):
    olvidar_esquema()
    c = connect(db_path())
    init_db(c)
    scheduler.list_scheduled_tasks(c)  # siembra las filas
    c.execute("ALTER TABLE scheduled_tasks DROP COLUMN run_at")
    c.execute("DELETE FROM scheduled_tasks WHERE task_key IN ('backup-config', 'mantenimiento')")
    c.execute("UPDATE scheduled_tasks SET interval_minutes = 99 WHERE task_key = ?", (TASK_LIBRARY_SYNC,))
    c.execute("UPDATE app_state SET value = '44' WHERE key = 'schema_version'")
    c.commit()
    c.close()
    olvidar_esquema()

    preparar_base()

    c = connect(db_path())
    try:
        assert "run_at" in {f[1] for f in c.execute("PRAGMA table_info(scheduled_tasks)")}
        tareas = {t["task_key"]: t for t in scheduler.list_scheduled_tasks(c)}
        assert tareas[TASK_LIBRARY_SYNC]["interval_minutes"] == 99 and tareas[TASK_LIBRARY_SYNC]["run_at"] is None
        assert tareas["backup-config"]["run_at"] == "03:30" and tareas[TASK_MAINTENANCE]["run_at"] == "04:00"
        assert c.execute("SELECT value FROM app_state WHERE key = 'schema_version'").fetchone()[0] == str(SCHEMA_VERSION)
    finally:
        c.close()
    assert list((db_path().parent / "backups").glob("pre-migracion-*-v44.db"))


def test_la_migracion_no_traga_un_fallo_que_no_es_columna_repetida():
    """Antes un `except OperationalError: pass` dejaba pasar cualquier error y se marcaba el esquema 45 sin la columna."""
    from emuwarez_uploadrr.database import _migrate_scheduled_tasks_run_at
    sin_tabla = sqlite3.connect(":memory:")
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        _migrate_scheduled_tasks_run_at(sin_tabla)


def test_la_migracion_es_idempotente(conn):
    from emuwarez_uploadrr.database import _migrate_scheduled_tasks_run_at
    _migrate_scheduled_tasks_run_at(conn)
    _migrate_scheduled_tasks_run_at(conn)
    assert conn.execute("SELECT COUNT(*) FROM pragma_table_info('scheduled_tasks') WHERE name = 'run_at'").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_la_lista_trae_la_hora_la_zona_y_las_opciones(client, auth_headers, monkeypatch):
    monkeypatch.delenv("TZ", raising=False)
    tareas = {t["task_key"]: t for t in client.get("/api/tasks/scheduled", headers=auth_headers).json()}

    assert tareas[TASK_MAINTENANCE]["run_at"] == "04:00" and tareas["backup-config"]["run_at"] == "03:30"
    assert tareas[TASK_LIBRARY_SYNC]["run_at"] is None
    assert {t["timezone"] for t in tareas.values()} == {"Europe/Madrid"}
    assert [o["clave"] for o in tareas[TASK_MAINTENANCE]["opciones"]] == [
        "mantenimiento.dias_tareas", "mantenimiento.dias_registros", "mantenimiento.lineas_registro", "mantenimiento.dias_avisos"]
    assert tareas[TASK_MAINTENANCE]["opciones"][0] == {
        "clave": "mantenimiento.dias_tareas", "etiqueta": "Historial de tareas: conservar (días)",
        "valor": 90, "minimo": 7, "maximo": 3650, "nota": ""}
    assert [(o["clave"], o["valor"]) for o in tareas["backup-config"]["opciones"]] == [
        ("copias.conservar", 7), ("copias.incluir_claves", 0)]
    claves = tareas["backup-config"]["opciones"][1]
    assert (claves["minimo"], claves["maximo"]) == (0, 1) and "legible" in claves["nota"]
    assert tareas[TASK_LIBRARY_SYNC]["opciones"] == []


def test_la_zona_de_la_respuesta_es_la_de_tz(client, auth_headers, monkeypatch):
    monkeypatch.setenv("TZ", "Atlantic/Canary")
    t = client.get("/api/tasks/scheduled", headers=auth_headers).json()[0]
    assert t["timezone"] == "Atlantic/Canary"


def test_put_con_hora_fija(client, auth_headers):
    r = client.put(f"/api/tasks/scheduled/{TASK_EMU_SYNC}", json={"run_at": "04:00"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["run_at"] == "04:00" and r.json()["interval_minutes"] == 1440
    assert datetime.fromisoformat(r.json()["next_run_at"]).astimezone(MADRID).strftime("%H:%M") == "04:00"


def test_put_con_intervalo_sigue_funcionando_y_quita_la_hora(client, auth_headers):
    client.put(f"/api/tasks/scheduled/{TASK_EMU_SYNC}", json={"run_at": "04:00"}, headers=auth_headers)
    r = client.put(f"/api/tasks/scheduled/{TASK_EMU_SYNC}", json={"interval_minutes": 120}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["run_at"] is None and r.json()["interval_minutes"] == 120


def test_put_sin_nada_o_con_hora_mala_da_422(client, auth_headers):
    assert client.put(f"/api/tasks/scheduled/{TASK_EMU_SYNC}", json={}, headers=auth_headers).status_code == 422
    r = client.put(f"/api/tasks/scheduled/{TASK_EMU_SYNC}", json={"run_at": "25:00"}, headers=auth_headers)
    assert r.status_code == 422 and "HH:MM" in r.json()["detail"]


def test_put_de_hora_a_una_tarea_desconocida_da_404(client, auth_headers):
    assert client.put("/api/tasks/scheduled/no-existe", json={"run_at": "04:00"}, headers=auth_headers).status_code == 404


def test_opciones_se_guardan_y_vuelven_en_la_respuesta(client, auth_headers):
    r = client.put(f"/api/tasks/scheduled/{TASK_MAINTENANCE}/opciones",
                   json={"valores": {"mantenimiento.dias_tareas": 120, "mantenimiento.lineas_registro": 500}},
                   headers=auth_headers)
    assert r.status_code == 200
    valores = {o["clave"]: o["valor"] for o in r.json()["opciones"]}
    assert valores["mantenimiento.dias_tareas"] == 120 and valores["mantenimiento.lineas_registro"] == 500
    assert valores["mantenimiento.dias_avisos"] == 30
    tareas = {t["task_key"]: t for t in client.get("/api/tasks/scheduled", headers=auth_headers).json()}
    assert {o["clave"]: o["valor"] for o in tareas[TASK_MAINTENANCE]["opciones"]} == valores


@pytest.mark.parametrize("tarea, valores, codigo", [
    (TASK_MAINTENANCE, {"mantenimiento.dias_tareas": 2}, 422),
    (TASK_MAINTENANCE, {"copias.conservar": 5}, 422),          # de otra tarea
    (TASK_MAINTENANCE, {"no.existe": 5}, 422),
    (TASK_LIBRARY_SYNC, {"mantenimiento.dias_tareas": 100}, 422),
    ("no-existe", {"copias.conservar": 5}, 404),
])
def test_opciones_invalidas_se_rechazan(client, auth_headers, tarea, valores, codigo):
    r = client.put(f"/api/tasks/scheduled/{tarea}/opciones", json={"valores": valores}, headers=auth_headers)
    assert r.status_code == codigo


def test_opciones_piden_sesion(client):
    assert client.put(f"/api/tasks/scheduled/{TASK_MAINTENANCE}/opciones", json={"valores": {}}).status_code == 401


def test_ejecutar_a_mano_el_mantenimiento_por_la_api(client, auth_headers):
    r = client.post(f"/api/tasks/scheduled/{TASK_MAINTENANCE}/run", headers=auth_headers)
    assert r.status_code == 200 and r.json()["status"] == "completed"
    logs = client.get(f"/api/tasks/scheduled/{TASK_MAINTENANCE}/logs", headers=auth_headers).json()["logs"]
    assert [l["status"] for l in logs] == ["completed"]
