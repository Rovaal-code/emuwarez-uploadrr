"""La cola de diagnóstico se limpia con lo que Radarr/Sonarr dicen ahora, y una instancia caída no cuenta como vacía."""
from __future__ import annotations

from emuwarez_uploadrr.integrations.arr_base import ArrConnectionError

from tests import arr_falso
from tests.arr_falso import RADARR, SONARR

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


# El registro de Radarr/Sonarr trae el enlace del indexador con su clave (Prowlarr: ...?apikey=...).
_ENLACE = "http://prowlarr:9696/1/download?apikey=clavedeprowlarr123&link=abc"


def test_la_cola_y_el_historial_no_guardan_la_clave_del_indexador(conn, monkeypatch):
    from emuwarez_uploadrr.services import arr_health
    conn.execute("INSERT INTO library_items (item_type, title, instance_id, external_id, local_status, instance_type)"
                 " VALUES ('movie', 'M', ?, '42', 'Faltante', 'radarr'), ('series', 'S', ?, '7', 'Faltante', 'sonarr')",
                 (RADARR, SONARR))
    conn.commit()
    datos = {"downloadUrl": _ENLACE, "message": "Import failed"}
    monkeypatch.setattr(arr_health, "radarr_get_queue", lambda _i: [{"movieId": 42, "status": "downloading",
                                                                    "title": "M", "downloadUrl": _ENLACE}])
    monkeypatch.setattr(arr_health, "sonarr_get_queue", lambda _i: [{"seriesId": 7, "status": "downloading",
                                                                    "title": "S", "downloadUrl": _ENLACE}])
    monkeypatch.setattr(arr_health, "radarr_get_history", lambda _i, **_: [{"movieId": 42, "eventType": "downloadFailed",
                                                                          "sourceTitle": "M", "data": datos}])
    monkeypatch.setattr(arr_health, "sonarr_get_history", lambda _i, **_: [{"seriesId": 7, "eventType": "downloadFailed",
                                                                          "sourceTitle": "S", "data": datos}])

    assert arr_health.refresh_arr_queue_diagnostics(conn)["library_items_updated"] == 2
    assert arr_health.refresh_arr_history_diagnostics(conn)["library_items_updated"] == 2

    filas = conn.execute("SELECT * FROM library_items").fetchall()
    assert [f["arr_history_error"] for f in filas] == ["Import failed", "Import failed"]
    assert not any("clavedeprowlarr123" in str(v) for f in filas for v in tuple(f))


def test_al_migrar_se_borra_el_registro_que_ya_se_guardo(conn):
    from emuwarez_uploadrr.database import SCHEMA_VERSION, init_db, set_state
    conn.execute("INSERT INTO library_items (item_type, title, instance_id, external_id, local_status, instance_type,"
                 " arr_queue_raw_json, arr_history_raw_json) VALUES ('movie', 'M', ?, '42', 'Faltante', 'radarr', ?, ?)",
                 (RADARR, f'{{"downloadUrl": "{_ENLACE}"}}', f'{{"data": {{"downloadUrl": "{_ENLACE}"}}}}'))
    set_state(conn, "schema_version", str(SCHEMA_VERSION - 1))
    conn.commit()

    init_db(conn)

    assert tuple(conn.execute("SELECT arr_queue_raw_json, arr_history_raw_json FROM library_items").fetchone()) == (None, None)
