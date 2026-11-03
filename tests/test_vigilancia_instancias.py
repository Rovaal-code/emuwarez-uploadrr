"""La instancia de Radarr/Sonarr que vuelve a responder tras estar caída se sincroniza sola.

El servidor es el falso de `http_falso` (una instancia caída rechaza la conexión) y el reloj, el de `_ahora`."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import library, scheduler, vigilancia_instancias as vig
from emuwarez_uploadrr.services.settings import set_setting

from tests import arr_falso
from tests.arr_falso import RADARR, _peli
from tests.http_falso import falla_conexion, respuesta

# Las fixtures de arr_falso (la autouse, solo para que actúe) se ven desde este módulo.
arr, conn, _progreso_aparte = arr_falso.arr, arr_falso.conn, arr_falso._progreso_aparte


@pytest.fixture(autouse=True)
def _estado_aparte(monkeypatch):
    """El estado de la vigilancia es del módulo: que un test no deje nada al siguiente."""
    monkeypatch.setattr(vig, "_respondia", {})
    monkeypatch.setattr(vig, "_sincronizada", {})
    monkeypatch.setattr(vig, "_mirada", {})
    monkeypatch.setattr(library.sync, "_LIB_SYNC_PROGRESS", dict(library.sync._LIB_SYNC_PROGRESS))


class Reloj:
    def __init__(self) -> None:
        self.ahora = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def avanza(self, minutos: float) -> None:
        self.ahora += timedelta(minutes=minutos)


@pytest.fixture
def reloj(monkeypatch):
    r = Reloj()
    monkeypatch.setattr(vig, "_ahora", lambda: r.ahora)
    return r


@pytest.fixture
def instancias(http_falso):
    """Qué instancias responden: {"radarr": True, "sonarr": False}. Las caídas rechazan la conexión."""
    vivas = {"radarr": True, "sonarr": True}

    def atiende(request):
        return respuesta(200, json={"version": "5.0"}) if vivas[request.url.host] else falla_conexion()

    http_falso.responde(atiende)
    return vivas


@pytest.fixture
def sincronizaciones(monkeypatch):
    """Las instancias que sincroniza la vigilancia, por nombre, con la sincronización de verdad por debajo."""
    llamadas: list[str] = []
    real = library.sync.sync_instance

    def espia(conn, instance, **kw):
        llamadas.append(instance.name)
        return real(conn, instance, **kw)

    monkeypatch.setattr(library.sync, "sync_instance", espia)
    return llamadas


def test_cae_vuelve_y_se_sincroniza_una_vez(conn, arr, instancias, reloj, sincronizaciones):
    arr["peliculas"] = [_peli(1, "Matrix", 603)]
    assert vig.vigilar_instancias(conn)[0] == "completed"
    assert sincronizaciones == []

    instancias["radarr"] = False
    estado, resumen = vig.vigilar_instancias(conn)
    assert (estado, sincronizaciones) == ("completed", [])
    assert "1 sin responder" in resumen

    instancias["radarr"] = True
    _, resumen = vig.vigilar_instancias(conn)
    assert sincronizaciones == ["Radarr"]
    assert "sincronizada al volver: Radarr" in resumen
    assert conn.execute("SELECT COUNT(*) FROM library_items WHERE instance_id = ?", (RADARR,)).fetchone()[0] == 1

    # Ya responde: las miradas siguientes no vuelven a sincronizar.
    vig.vigilar_instancias(conn)
    vig.vigilar_instancias(conn)
    assert sincronizaciones == ["Radarr"]


def test_caida_que_sigue_caida_no_sincroniza(conn, arr, instancias, reloj, sincronizaciones):
    vig.vigilar_instancias(conn)
    instancias["sonarr"] = False
    for _ in range(3):
        vig.vigilar_instancias(conn)
    assert sincronizaciones == []


def test_la_primera_mirada_no_sincroniza_ni_con_la_instancia_viva_ni_caida(conn, arr, instancias, reloj, sincronizaciones):
    instancias["sonarr"] = False
    vig.vigilar_instancias(conn)
    assert sincronizaciones == []


def test_una_instancia_que_ya_estaba_caida_en_la_primera_mirada_se_sincroniza_al_volver(
        conn, arr, instancias, reloj, sincronizaciones):
    """Es el caso de reiniciar la aplicación con la instancia apagada y encenderla después."""
    instancias["sonarr"] = False
    vig.vigilar_instancias(conn)
    instancias["sonarr"] = True
    vig.vigilar_instancias(conn)
    assert sincronizaciones == ["Sonarr"]


def test_dos_transiciones_seguidas_sincronizan_una_sola_vez(conn, arr, instancias, reloj, sincronizaciones):
    vig.vigilar_instancias(conn)
    for _ in range(2):
        instancias["radarr"] = False
        vig.vigilar_instancias(conn)
        instancias["radarr"] = True
        vig.vigilar_instancias(conn)
        reloj.avanza(5)
    assert sincronizaciones == ["Radarr"]

    # Pasado el enfriamiento, la siguiente vuelta sí sincroniza.
    reloj.avanza(vig.ENFRIAMIENTO.total_seconds() / 60)
    instancias["radarr"] = False
    vig.vigilar_instancias(conn)
    instancias["radarr"] = True
    vig.vigilar_instancias(conn)
    assert sincronizaciones == ["Radarr", "Radarr"]


def test_con_una_sincronizacion_en_marcha_se_salta_y_lo_reintenta_en_la_siguiente(
        conn, arr, instancias, reloj, sincronizaciones):
    vig.vigilar_instancias(conn)
    instancias["radarr"] = False
    vig.vigilar_instancias(conn)
    instancias["radarr"] = True

    with library._lib_sync_guard():
        estado, _ = vig.vigilar_instancias(conn)
    assert sincronizaciones == []
    assert estado == "completed"

    vig.vigilar_instancias(conn)
    assert sincronizaciones == ["Radarr"]


def test_dos_instancias_que_vuelven_a_la_vez_se_sincronizan_una_tras_otra(conn, arr, instancias, reloj, sincronizaciones):
    vig.vigilar_instancias(conn)
    instancias.update(radarr=False, sonarr=False)
    vig.vigilar_instancias(conn)
    instancias.update(radarr=True, sonarr=True)
    vig.vigilar_instancias(conn)
    assert sorted(sincronizaciones) == ["Radarr", "Sonarr"]


def test_una_instancia_caida_no_borra_nada_de_su_biblioteca(conn, arr, instancias, reloj, sincronizaciones):
    arr["peliculas"] = [_peli(1, "Matrix", 603), _peli(2, "Dune", 438631)]
    library.sync_instance(conn, arr_falso.get_instance(conn, RADARR))
    antes = conn.execute("SELECT COUNT(*) FROM library_items WHERE instance_id = ?", (RADARR,)).fetchone()[0]
    assert antes == 2

    # Cae: la vigilancia solo mira, no toca la biblioteca.
    vig.vigilar_instancias(conn)
    instancias["radarr"] = False
    vig.vigilar_instancias(conn)
    assert conn.execute("SELECT COUNT(*) FROM library_items WHERE instance_id = ?", (RADARR,)).fetchone()[0] == antes

    # Vuelve, pero su listado falla (un 5xx al sincronizar): la sincronización falla y tampoco borra.
    instancias["radarr"] = True
    arr["peliculas"] = IntegrationError("HTTP 503")
    estado, resumen = vig.vigilar_instancias(conn)
    assert sincronizaciones == ["Radarr"]
    assert estado == "failed" and "Radarr" in resumen
    assert conn.execute("SELECT COUNT(*) FROM library_items WHERE instance_id = ?", (RADARR,)).fetchone()[0] == antes


def test_apagado_en_configuracion_no_hace_ni_una_llamada(conn, arr, instancias, reloj, sincronizaciones, http_falso):
    set_setting(conn, "biblioteca.sincronizar_al_volver", "false")
    conn.commit()
    assert vig.vigilar_instancias(conn) == ("skipped", "Desactivado en Configuración")
    assert http_falso.peticiones == []


def test_una_instancia_desactivada_y_vuelta_a_activar_empieza_de_cero(conn, arr, instancias, reloj, sincronizaciones):
    vig.vigilar_instancias(conn)
    instancias["radarr"] = False
    vig.vigilar_instancias(conn)
    conn.execute("UPDATE instances SET enabled = 0 WHERE id = ?", (RADARR,))
    conn.commit()
    vig.vigilar_instancias(conn)
    assert RADARR not in vig._respondia

    conn.execute("UPDATE instances SET enabled = 1 WHERE id = ?", (RADARR,))
    conn.commit()
    instancias["radarr"] = True
    vig.vigilar_instancias(conn)  # primera mirada otra vez
    assert sincronizaciones == []


def test_la_comprobacion_es_la_de_la_prueba_de_conexion_con_un_plazo_corto(conn, arr, instancias, reloj, http_falso):
    vig.vigilar_instancias(conn)
    assert sorted(http_falso.urls) == ["http://radarr/api/v3/system/status", "http://sonarr/api/v3/system/status"]
    assert http_falso.ultima.extensions["timeout"]["read"] == vig.PLAZO_COMPROBACION


def test_una_url_mal_formada_es_que_no_responde_y_no_corta_la_vigilancia_de_las_demas(conn, arr, instancias, reloj, monkeypatch):
    original = vig.arr_request

    def rota(metodo, url, *args, **kwargs):
        if "sonarr" in url:
            raise ValueError("URL mal formada")
        return original(metodo, url, *args, **kwargs)

    monkeypatch.setattr(vig, "arr_request", rota)
    vig.vigilar_instancias(conn)
    assert sorted(vig._respondia.values()) == [False, True]


@pytest.mark.parametrize("fallo", [lambda: respuesta(500), lambda: respuesta(401), lambda: falla_conexion()])
def test_un_5xx_una_clave_mala_o_una_conexion_rechazada_es_que_no_responde(conn, arr, http_falso, fallo):
    http_falso.responde(fallo())
    instancia = arr_falso.get_instance(conn, RADARR)
    assert vig._responde(instancia) is False


def test_es_una_tarea_programada_cada_5_minutos_y_no_llena_el_historial(conn, arr, instancias, reloj, sincronizaciones):
    tarea = scheduler.get_scheduled_task(conn, scheduler.TASK_INSTANCE_WATCH)
    assert (tarea["name"], tarea["interval_minutes"], tarea["manual_allowed"]) == ("Vigilar instancias", 5, 1)

    resultado = scheduler.run_scheduled_task(conn, scheduler.TASK_INSTANCE_WATCH)
    assert resultado["status"] == "completed"
    assert conn.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0] == 0


def test_las_instancias_caidas_salen_con_su_ultima_sincronizacion(conn, arr, instancias, reloj, sincronizaciones):
    arr["peliculas"] = [_peli(1, "Matrix", 603)]
    library.sync_instance(conn, arr_falso.get_instance(conn, RADARR))
    vig.vigilar_instancias(conn)
    assert vig.instancias_caidas(conn) == []

    instancias["radarr"] = False
    vig.vigilar_instancias(conn)
    caidas = vig.instancias_caidas(conn)
    assert [(c["id"], c["tipo"]) for c in caidas] == [(RADARR, "radarr")]
    assert caidas[0]["ultima_sincronizacion"] is not None

    instancias["radarr"] = True
    vig.vigilar_instancias(conn)
    assert vig.instancias_caidas(conn) == []


def test_una_caida_con_otra_sincronizacion_en_marcha_no_se_da_por_caida(conn, arr, instancias, reloj, sincronizaciones):
    """La vigilancia aplaza la sincronización de la que vuelve si hay otra en marcha, pero la instancia responde."""
    vig.vigilar_instancias(conn)
    instancias["radarr"] = False
    vig.vigilar_instancias(conn)
    instancias["radarr"] = True
    with library._lib_sync_guard():
        vig.vigilar_instancias(conn)
    assert vig.instancias_caidas(conn) == []


def test_una_mirada_vieja_no_afirma_que_este_caida(conn, arr, instancias, reloj, sincronizaciones):
    instancias["radarr"] = False
    vig.vigilar_instancias(conn)
    assert len(vig.instancias_caidas(conn)) == 1
    reloj.avanza(5 * vig.VIGENCIA_MIRADA_VUELTAS + 1)
    assert vig.instancias_caidas(conn) == []


def test_apagada_la_vigilancia_no_se_dice_nada_de_las_instancias(conn, arr, instancias, reloj, sincronizaciones):
    instancias["radarr"] = False
    vig.vigilar_instancias(conn)
    set_setting(conn, "biblioteca.sincronizar_al_volver", "false")
    conn.commit()
    assert vig.instancias_caidas(conn) == []


def test_una_instancia_desactivada_no_sale_entre_las_caidas(conn, arr, instancias, reloj, sincronizaciones):
    instancias["radarr"] = False
    vig.vigilar_instancias(conn)
    conn.execute("UPDATE instances SET enabled = 0 WHERE id = ?", (RADARR,))
    conn.commit()
    assert vig.instancias_caidas(conn) == []
