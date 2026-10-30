"""Unit tests for emuwarez_uploadrr/services/scheduler.py (Phase 11D).

All actual sync work (library/eMuwarez/network) is mocked — these tests
only exercise the scheduler's own bookkeeping (interval enforcement,
claim/due logic, status recording), never real Radarr/Sonarr/eMuwarez
traffic.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services.scheduler import (
    TASK_EMU_SYNC,
    TASK_LIBRARY_SYNC,
    claim_due_tasks,
    get_scheduled_task,
    list_scheduled_tasks,
    run_scheduled_task,
    set_task_interval,
    tick_due_tasks,
)


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def test_default_tasks_seeded_with_correct_intervals(db_conn):
    tasks = {t["task_key"]: t for t in list_scheduled_tasks(db_conn)}
    assert tasks[TASK_LIBRARY_SYNC]["interval_minutes"] == 30
    assert tasks[TASK_LIBRARY_SYNC]["min_interval_minutes"] == 15
    assert tasks[TASK_LIBRARY_SYNC]["manual_allowed"] == 1


def test_emu_request_sync_is_daily_with_an_hourly_floor(db_conn):
    """Cada 24 h, que son ≤ 9 llamadas a la API por sincronización; el botón sigue valiendo."""
    tarea = {t["task_key"]: t for t in list_scheduled_tasks(db_conn)}[TASK_EMU_SYNC]
    assert (tarea["interval_minutes"], tarea["min_interval_minutes"], tarea["manual_allowed"]) == (1440, 60, 1)
    assert tarea["name"] == "Sincronizar peticiones eMuwarez"
    with pytest.raises(ValueError, match="mínimo"):
        set_task_interval(db_conn, TASK_EMU_SYNC, 30)


def test_list_scheduled_tasks_idempotent(db_conn):
    from emuwarez_uploadrr.services.scheduler import DEFAULT_TASKS

    first = list_scheduled_tasks(db_conn)
    second = list_scheduled_tasks(db_conn)
    assert len(first) == len(second) == len(DEFAULT_TASKS)


# ---------------------------------------------------------------------------
# set_task_interval — minimum enforcement
# ---------------------------------------------------------------------------

def test_set_interval_below_minimum_rejected(db_conn):
    with pytest.raises(ValueError, match="mínimo"):
        set_task_interval(db_conn, TASK_LIBRARY_SYNC, 5)


def test_set_interval_at_minimum_allowed(db_conn):
    task = set_task_interval(db_conn, TASK_LIBRARY_SYNC, 15)
    assert task["interval_minutes"] == 15


def test_set_interval_above_minimum_allowed(db_conn):
    task = set_task_interval(db_conn, TASK_LIBRARY_SYNC, 120)
    assert task["interval_minutes"] == 120


def test_set_interval_unknown_task_raises(db_conn):
    with pytest.raises(ValueError, match="desconocida"):
        set_task_interval(db_conn, "not-a-real-task", 30)


# ---------------------------------------------------------------------------
# run_scheduled_task
# ---------------------------------------------------------------------------

def test_run_library_sync_updates_bookkeeping(db_conn):
    with patch("emuwarez_uploadrr.services.library.sync_all") as mock_sync:
        mock_sync.return_value = {"imported": 5, "missing": 1, "instances": 1, "errors": []}
        result = run_scheduled_task(db_conn, TASK_LIBRARY_SYNC, manual=True)

    assert result["status"] == "completed"
    assert "5" in result["summary"]
    task = get_scheduled_task(db_conn, TASK_LIBRARY_SYNC)
    assert task["last_status"] == "completed"
    assert task["last_run_at"] is not None
    assert task["next_run_at"] is not None


def test_run_library_sync_failure_recorded_not_raised(db_conn):
    with patch("emuwarez_uploadrr.services.library.sync_all", side_effect=RuntimeError("boom")):
        result = run_scheduled_task(db_conn, TASK_LIBRARY_SYNC, manual=True)

    assert result["status"] == "failed"
    assert "boom" in result["summary"]
    task = get_scheduled_task(db_conn, TASK_LIBRARY_SYNC)
    assert task["last_status"] == "failed"


def test_run_unknown_task_raises(db_conn):
    with pytest.raises(ValueError, match="desconocida"):
        run_scheduled_task(db_conn, "not-a-real-task", manual=False)


# ---------------------------------------------------------------------------
# claim_due_tasks
# ---------------------------------------------------------------------------

def test_claim_due_tasks_all_due_initially(db_conn):
    from emuwarez_uploadrr.services.scheduler import DEFAULT_TASKS

    claimed = claim_due_tasks(db_conn)
    assert set(claimed) == {t[0] for t in DEFAULT_TASKS}


def test_claim_due_tasks_does_not_reclaim_immediately(db_conn):
    from emuwarez_uploadrr.services.scheduler import DEFAULT_TASKS

    first = claim_due_tasks(db_conn)
    assert len(first) == len(DEFAULT_TASKS)
    second = claim_due_tasks(db_conn)
    assert second == []  # grace window pushed next_run_at forward


def test_claim_due_tasks_respects_disabled_flag(db_conn):
    list_scheduled_tasks(db_conn)  # seeds the default rows first
    db_conn.execute("UPDATE scheduled_tasks SET enabled = 0 WHERE task_key = ?", (TASK_LIBRARY_SYNC,))
    db_conn.commit()
    claimed = claim_due_tasks(db_conn)
    assert TASK_LIBRARY_SYNC not in claimed


# ---------------------------------------------------------------------------
# tick_due_tasks — full loop, still all mocked
# ---------------------------------------------------------------------------

def test_tick_due_tasks_runs_all_on_first_tick(isolated_db):
    from emuwarez_uploadrr.services.scheduler import DEFAULT_TASKS

    with patch("emuwarez_uploadrr.services.library.sync_all") as mock_lib, \
         patch("emuwarez_uploadrr.services.requests.sync_emu_requests") as mock_emu, \
         patch("emuwarez_uploadrr.services.version_info.estado_de_version") as mock_ver:
        mock_lib.return_value = {"imported": 0, "missing": 0, "instances": 0, "errors": []}
        mock_emu.return_value = {"status": "ok", "imported": 0, "matched": 0}
        # Sin manifiesto publicado: la comprobación de versión no puede
        # comparar y se salta, que es un resultado válido de la tarea.
        mock_ver.return_value = {"estado": "desconocido", "motivo": "sin manifiesto",
                                 "version": "0.2.0", "commit_corto": None, "ultima": {}}
        results = tick_due_tasks()

    task_keys = {r["task_key"] for r in results}
    assert task_keys == {t[0] for t in DEFAULT_TASKS}
    assert all(r["status"] in ("completed", "skipped") for r in results)


def test_tick_due_tasks_second_tick_runs_nothing(isolated_db):
    with patch("emuwarez_uploadrr.services.library.sync_all") as mock_lib:
        mock_lib.return_value = {"imported": 0, "missing": 0, "instances": 0, "errors": []}
        tick_due_tasks()
        second_results = tick_due_tasks()

    assert second_results == []


# ---------------------------------------------------------------------------
# Sincronización de peticiones de eMuwarez
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("resultado, estado, texto", [
    ({"status": "ok", "imported": 12, "matched": 3}, "completed", "12 peticiones importadas, 3 cruces"),
    ({"status": "throttled", "wait_seconds": 90}, "skipped", "Esperando 90s"),
    ({"status": "busy", "message": "Hay una subida en marcha; vuelve a probar cuando termine."},
     "skipped", "Hay una subida en marcha"),
])
def test_emu_request_sync_records_what_happened(db_conn, resultado, estado, texto):
    with patch("emuwarez_uploadrr.services.requests.sync_emu_requests", return_value=resultado) as mock_emu:
        run = run_scheduled_task(db_conn, TASK_EMU_SYNC)

    mock_emu.assert_called_once_with(db_conn, force=False)
    assert run["status"] == estado
    assert texto in run["summary"]
    assert get_scheduled_task(db_conn, TASK_EMU_SYNC)["last_status"] == estado


def test_emu_request_sync_failure_is_recorded_with_its_message(db_conn):
    from emuwarez_uploadrr.integrations.base import IntegrationError

    error = IntegrationError("eMuwarez ha rechazado la API key (¿ratio por debajo de 1?)", status=401)
    with patch("emuwarez_uploadrr.services.requests.sync_emu_requests", side_effect=error):
        run = run_scheduled_task(db_conn, TASK_EMU_SYNC)

    assert run["status"] == "failed"
    assert run["summary"] == "eMuwarez ha rechazado la API key (¿ratio por debajo de 1?)"
