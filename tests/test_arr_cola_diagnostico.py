"""La cola de diagnóstico se limpia con lo que Radarr/Sonarr dicen ahora, y una instancia caída no cuenta como vacía."""
from __future__ import annotations

from emuwarez_uploadrr.integrations.arr_base import ArrConnectionError

from tests import arr_falso
from tests.arr_falso import RADARR

# Las fixtures de arr_falso (la autouse, solo para que actúe) se ven desde este módulo.
conn, _progreso_aparte = arr_falso.conn, arr_falso._progreso_aparte


# --- BIB-11: la cola y el historial de diagnóstico ------------------------------------------------------------

def _pelicula_en_cola(conn):
    conn.execute("INSERT INTO library_items (item_type, title, instance_id, external_id, local_status, instance_type,"
                 " arr_queue_status, arr_queue_title) VALUES ('movie', 'M', ?, '42', 'Faltante', 'radarr',"
                 " 'downloading', 'M.1080p')", (RADARR,))
    conn.commit()


def test_lo_que_sale_de_la_cola_deja_de_figurar_en_ella(conn, monkeypatch):
    from emuwarez_uploadrr.services import arr_health
    _pelicula_en_cola(conn)
    monkeypatch.setattr(arr_health, "radarr_get_queue", lambda _i: [])

    resultado = arr_health.refresh_arr_queue_diagnostics(conn, instance_id=RADARR)

    assert resultado["ok"] is True
    assert tuple(conn.execute("SELECT arr_queue_status, arr_queue_title FROM library_items").fetchone()) == (None, None)


def test_una_instancia_que_no_responde_no_es_una_cola_vacia(conn, monkeypatch):
    from emuwarez_uploadrr.services import arr_health
    _pelicula_en_cola(conn)

    def apagada(_i):
        raise ArrConnectionError("No se pudo conectar")

    monkeypatch.setattr(arr_health, "radarr_get_queue", apagada)
    monkeypatch.setattr(arr_health, "radarr_get_history", apagada)

    cola = arr_health.refresh_arr_queue_diagnostics(conn, instance_id=RADARR)
    historial = arr_health.refresh_arr_history_diagnostics(conn, instance_id=RADARR)

    assert cola["ok"] is False and cola["errors"][0]["instance"] == "Radarr"
    assert historial["ok"] is False
    assert conn.execute("SELECT arr_queue_status FROM library_items").fetchone()[0] == "downloading"
