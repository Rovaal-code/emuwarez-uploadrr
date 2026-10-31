"""Una sincronización donde ninguna instancia responde no se anota como completada."""
from __future__ import annotations

from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import library

from tests import arr_falso
from tests.arr_falso import RADARR, _con_serie, _externos, _peli

# Las fixtures de arr_falso (la autouse, solo para que actúe) se ven desde este módulo.
arr, conn, _progreso_aparte = arr_falso.arr, arr_falso.conn, arr_falso._progreso_aparte


# --- BIB-8: todas las instancias caídas no es «completada» ---------------------------------------------------

def test_con_todas_las_instancias_caidas_la_sincronizacion_es_fallida(conn, arr):
    arr["peliculas"] = [_peli(1, "Matrix")]
    _con_serie(arr, 20, [1])
    library.sync_all(conn, include_episodes=True)
    visto = library.get_dashboard_summary(conn)["last_sync_at"]
    assert visto

    arr["peliculas"] = arr["series"] = IntegrationError("No se pudo conectar")
    resultado = library.sync_all(conn, include_episodes=True)

    assert resultado["status"] == "failed" and len(resultado["errors"]) == 2
    ultima = conn.execute("SELECT status FROM task_runs WHERE name = 'sync-library' ORDER BY id DESC").fetchone()[0]
    assert ultima == "failed"
    assert library.get_dashboard_summary(conn)["last_sync_at"] == visto  # sigue siendo la última lectura de verdad
    assert _externos(conn, RADARR) == {"1"}


def test_el_planificador_anota_fallida_la_sincronizacion_sin_ninguna_instancia(conn, arr):
    from emuwarez_uploadrr.services.scheduler import TASK_LIBRARY_SYNC, get_scheduled_task, run_scheduled_task
    arr["peliculas"] = arr["series"] = IntegrationError("No se pudo conectar")

    assert run_scheduled_task(conn, TASK_LIBRARY_SYNC, manual=True)["status"] == "failed"
    assert get_scheduled_task(conn, TASK_LIBRARY_SYNC)["last_status"] == "failed"


def test_si_alguna_instancia_responde_la_sincronizacion_es_completada_con_su_aviso(conn, arr):
    arr["peliculas"] = [_peli(1, "Matrix")]
    arr["series"] = IntegrationError("No se pudo conectar")

    resultado = library.sync_all(conn)

    assert resultado["status"] == "completed" and len(resultado["errors"]) == 1
