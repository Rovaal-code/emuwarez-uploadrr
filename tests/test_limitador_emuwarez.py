"""El limitador compartido de las peticiones a eMuwarez (integrations/emu_limitador.py).

Casi todo con un reloj falso (dormir adelanta el reloj); una prueba usa hilos de verdad con una ventana mínima."""
from __future__ import annotations

import logging
import threading
import time

import pytest

from emuwarez_uploadrr.integrations import emu, emu_limitador
from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.integrations.emu_limitador import Limitador

CLAVE = "CLAVESECRETA123"


class Reloj:
    def __init__(self):
        self.ahora = 1000.0
        self.dormidas: list[float] = []
        self._cerrojo = threading.Lock()

    def __call__(self):
        with self._cerrojo:
            return self.ahora

    def dormir(self, s):
        with self._cerrojo:
            self.dormidas.append(s)
            self.ahora += s


class Espia(Limitador):
    """Apunta el instante de cada hueco concedido; `_espera` corre con el cerrojo cogido, así que el orden es exacto."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.concedidas: list[float] = []

    def _espera(self, estado, ahora, interactiva):
        espera = super()._espera(estado, ahora, interactiva)
        if espera <= 0:
            self.concedidas.append(ahora)
        return espera


def _limitador(cls=Limitador, **kw):
    reloj = Reloj()
    return cls(reloj=reloj, dormir=reloj.dormir, **kw), reloj


def _nunca_mas_de(concedidas, limite, ventana):
    marcas = sorted(concedidas)
    return all(marcas[i + limite] - marcas[i] >= ventana for i in range(len(marcas) - limite))


# --- La ventana -------------------------------------------------------------

def test_la_llamada_31_dentro_del_minuto_espera_a_que_salga_la_primera():
    lim, reloj = _limitador(capacidad=30, reserva_interactiva=0)
    for _ in range(30):
        assert lim.esperar_turno(CLAVE) == 0
        reloj.ahora += 1  # 30 peticiones en 30 s
    assert reloj.dormidas == []
    assert lim.esperar_turno(CLAVE) == pytest.approx(30.0)  # la primera fue hace 30 s: faltan otros 30
    assert sum(reloj.dormidas) == pytest.approx(30.0)


def test_por_defecto_se_planifica_con_margen_bajo_las_30_de_emuwarez():
    assert emu_limitador.EMU_LIMITE_POR_MINUTO < 30
    lim, reloj = _limitador()
    for _ in range(lim.capacidad - lim.reserva_interactiva):
        lim.esperar_turno(CLAVE)
    assert reloj.dormidas == []
    assert lim.esperar_turno(CLAVE) == pytest.approx(60.0)  # todas en el mismo instante: un minuto entero


def test_se_duerme_a_tramos_cortos_y_se_vuelve_a_mirar():
    lim, reloj = _limitador(capacidad=2, reserva_interactiva=0, tramo=1.0)
    lim.esperar_turno(CLAVE)
    lim.esperar_turno(CLAVE)
    lim.esperar_turno(CLAVE)
    assert max(reloj.dormidas) <= 1.0 and len(reloj.dormidas) == 60


def test_cada_clave_tiene_su_ventana():
    """El límite es por API key: probar una clave escrita a mano no gasta la de la aplicación."""
    lim, reloj = _limitador(capacidad=3, reserva_interactiva=0)
    for _ in range(3):
        lim.esperar_turno(CLAVE)
    assert lim.esperar_turno("OTRA") == 0
    assert reloj.dormidas == []


def test_las_claves_sin_nada_pendiente_se_olvidan_y_no_se_guarda_la_clave():
    lim, reloj = _limitador()
    lim.esperar_turno("PROBADA")
    assert CLAVE not in "".join(lim._claves) and "PROBADA" not in "".join(lim._claves)
    reloj.ahora += 61
    lim.esperar_turno(CLAVE)
    assert len(lim._claves) == 1


# --- Hilos ------------------------------------------------------------------

def test_con_hilos_y_reloj_falso_nunca_hay_mas_de_las_permitidas_en_60_s():
    lim, _ = _limitador(Espia)
    limite = lim.capacidad - lim.reserva_interactiva
    errores = []

    def trabajo():
        try:
            for _ in range(12):
                lim.esperar_turno(CLAVE)
        except BaseException as exc:  # noqa: BLE001
            errores.append(exc)

    hilos = [threading.Thread(target=trabajo) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    assert not errores and not any(h.is_alive() for h in hilos)
    assert len(lim.concedidas) == 96
    assert _nunca_mas_de(lim.concedidas, limite, lim.ventana)


def test_con_hilos_de_verdad_y_una_ventana_minima_nunca_se_pasa():
    lim = Espia(capacidad=4, reserva_interactiva=0, ventana=0.2, tramo=0.01)
    hilos = [threading.Thread(target=lambda: [lim.esperar_turno(CLAVE) for _ in range(3)]) for _ in range(6)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=10)
    assert not any(h.is_alive() for h in hilos)
    assert len(lim.concedidas) == 18
    assert _nunca_mas_de(lim.concedidas, 4, 0.2)


def test_se_duerme_sin_el_cerrojo_cogido():
    """Mientras un recorrido espera su hueco, otro hilo puede pedir el suyo (y una consulta pasa enseguida)."""
    durmiendo, seguir = threading.Event(), threading.Event()
    cogido_al_dormir = []

    def dormir(s):
        cogido_al_dormir.append(lim._cerrojo.locked())
        durmiendo.set()
        seguir.wait(5)
        reloj.ahora += 60

    reloj = Reloj()
    lim = Limitador(capacidad=3, reserva_interactiva=1, reloj=reloj, dormir=dormir, tramo=60)
    lim.esperar_turno(CLAVE)
    lim.esperar_turno(CLAVE)
    recorrido = threading.Thread(target=lambda: lim.esperar_turno(CLAVE))
    recorrido.start()
    assert durmiendo.wait(5)
    consulta = threading.Thread(target=lambda: lim.esperar_turno(CLAVE, interactiva=True))
    consulta.start()
    consulta.join(timeout=5)
    assert not consulta.is_alive()  # con el cerrojo cogido durante la espera, se quedaría aquí
    seguir.set()
    recorrido.join(timeout=5)
    assert not recorrido.is_alive()
    assert cogido_al_dormir == [False]


# --- Consultas interactivas -------------------------------------------------

def test_una_consulta_no_se_pone_a_la_cola_de_un_recorrido():
    lim, reloj = _limitador()
    for _ in range(lim.capacidad - lim.reserva_interactiva):
        lim.esperar_turno(CLAVE)
    for _ in range(lim.reserva_interactiva):
        assert lim.esperar_turno(CLAVE, interactiva=True) == 0
    assert reloj.dormidas == []


def test_una_consulta_que_tendria_que_esperar_mucho_falla_con_un_mensaje_claro_sin_dormir():
    lim, reloj = _limitador(capacidad=2, reserva_interactiva=1)
    lim.esperar_turno(CLAVE, interactiva=True)
    lim.esperar_turno(CLAVE, interactiva=True)
    with pytest.raises(IntegrationError) as e:
        lim.esperar_turno(CLAVE, interactiva=True)
    assert "límite de peticiones por minuto" in str(e.value) and "60 s" in str(e.value)
    assert e.value.status is None
    assert reloj.dormidas == []


def test_una_consulta_espera_si_es_poco():
    lim, reloj = _limitador(capacidad=2, reserva_interactiva=1)
    lim.esperar_turno(CLAVE, interactiva=True)
    lim.esperar_turno(CLAVE, interactiva=True)
    reloj.ahora += 50
    assert lim.esperar_turno(CLAVE, interactiva=True) == pytest.approx(10.0)


# --- 429 --------------------------------------------------------------------

def test_un_429_pausa_a_todos_los_hilos_con_esa_clave():
    lim, reloj = _limitador()
    lim.penalizar(CLAVE, 60)
    esperado = []
    hilo = threading.Thread(target=lambda: esperado.append(lim.esperar_turno(CLAVE)))
    hilo.start()
    hilo.join(timeout=10)
    assert esperado == [pytest.approx(60.0)]
    assert lim.esperar_turno("OTRA") == 0  # otra clave no está penalizada


def test_durante_la_pausa_de_un_429_una_consulta_falla_enseguida():
    lim, reloj = _limitador()
    lim.penalizar(CLAVE, 60)
    with pytest.raises(IntegrationError, match="prueba dentro de 60 s"):
        lim.esperar_turno(CLAVE, interactiva=True)
    assert reloj.dormidas == []


def test_un_segundo_429_no_acorta_la_pausa():
    lim, reloj = _limitador()
    lim.penalizar(CLAVE, 60)
    lim.penalizar(CLAVE, 5)
    assert lim.esperar_turno(CLAVE) == pytest.approx(60.0)


def test_penalizar_nunca_lanza():
    def roto():
        raise RuntimeError("reloj roto")

    Limitador(reloj=roto).penalizar(CLAVE)


def test_el_429_de_una_pagina_pausa_tambien_a_las_consultas(monkeypatch, limitador_emuwarez):
    """El 429 lo recibe el recorrido de peticiones; el perfil, pedido justo después desde otro hilo, no sale."""
    respuestas = [IntegrationError("HTTP 429", status=429),
                  {"data": [{"id": 1}], "meta": {"last_page": 1, "total": 1}}]
    pedidas = []

    def falso(method, url):
        pedidas.append(url)
        r = respuestas.pop(0)
        if isinstance(r, Exception):
            # Mientras la pausa sigue, el perfil no llega a pedirse.
            raise r
        return r

    monkeypatch.setattr(emu, "request_json", falso)
    lim = limitador_emuwarez
    original = lim.reloj.dormir
    errores_perfil = []

    def dormir(s):
        if not errores_perfil:
            hilo = threading.Thread(target=lambda: _perfil(errores_perfil))
            hilo.start()
            hilo.join(timeout=5)
        original(s)

    lim._dormir = dormir
    assert emu.emu_fetch_all_pages(CLAVE)[0] == [{"id": 1}]
    assert len(pedidas) == 2  # la página dos veces, el perfil ninguna
    assert "límite de peticiones" in str(errores_perfil[0])


def _perfil(errores):
    try:
        emu.emu_get_user(CLAVE)
    except IntegrationError as exc:
        errores.append(exc)


# --- Nunca se ve la clave ---------------------------------------------------

def test_esperar_no_lanza_ni_enseña_la_clave_en_el_registro(caplog):
    lim, reloj = _limitador()
    caplog.set_level(logging.DEBUG, logger="emuwarez.emu")
    lim.penalizar(CLAVE, 600)
    assert lim.esperar_turno(CLAVE) == pytest.approx(600.0)
    assert "ha esperado 600 s" in caplog.text
    assert CLAVE not in caplog.text and "api_token" not in caplog.text and "http" not in caplog.text


def test_un_429_real_por_emu_no_enseña_la_url_ni_la_clave(monkeypatch, caplog):
    import io
    import urllib.error

    from emuwarez_uploadrr.integrations import base

    def urlopen(req, timeout=None, context=None):
        raise urllib.error.HTTPError(req.full_url, 429, "x", {}, io.BytesIO(f"lento: {req.full_url}".encode()))

    monkeypatch.setattr(base.urllib.request, "urlopen", urlopen)
    caplog.set_level(logging.DEBUG, logger="emuwarez.emu")
    with pytest.raises(IntegrationError) as e:
        emu.emu_get_user(CLAVE)
    with pytest.raises(IntegrationError) as e2:
        emu.emu_get_user(CLAVE)  # ya penalizado: el limitador corta sin salir
    for texto in (str(e.value), str(e2.value), caplog.text):
        assert CLAVE not in texto and "api_token" not in texto


# --- Quién pasa por el limitador -------------------------------------------

def test_el_catalogo_largo_se_reparte_en_minutos_y_deja_sitio_al_perfil(monkeypatch, limitador_emuwarez):
    lim = limitador_emuwarez
    limite = lim.capacidad - lim.reserva_interactiva
    paginas = limite + 5
    monkeypatch.setattr(emu, "request_json", lambda method, url: {"data": [{"id": 1}] * 100})
    emu.emu_fetch_all_torrents(CLAVE, max_pages=paginas)
    assert sum(lim.reloj.dormidas) == pytest.approx(60.0)  # la página limite+1 espera al minuto siguiente
    monkeypatch.setattr(emu, "request_json", lambda method, url: {"username": "yo"})
    antes = len(lim.reloj.dormidas)
    assert emu.emu_get_user(CLAVE)["username"] == "yo"
    assert len(lim.reloj.dormidas) == antes


def test_probar_conexion_y_detalle_son_consultas_y_el_catalogo_espera(monkeypatch, limitador_emuwarez):
    lim = limitador_emuwarez
    monkeypatch.setattr(emu, "request_json", lambda method, url: {})
    lim.penalizar(CLAVE, 60)
    with pytest.raises(IntegrationError, match="límite"):
        emu.emu_test_connection(CLAVE)
    with pytest.raises(IntegrationError, match="límite"):
        emu.emu_get_request_detail(CLAVE, 1)
    emu.emu_test_connection(CLAVE, interactiva=False)  # el primer paso de la sincronización espera
    assert sum(lim.reloj.dormidas) == pytest.approx(60.0)


def test_la_prueba_de_conexion_de_ajustes_pasa_por_el_limitador(monkeypatch, limitador_emuwarez):
    import io
    import urllib.error

    from emuwarez_uploadrr.services.integration_tests import test_emuwarez_connection

    llamadas = []

    def urlopen(req, timeout=None):
        llamadas.append(req)
        raise urllib.error.HTTPError(req.full_url, 429, "x", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    primero = test_emuwarez_connection(api_key=CLAVE, base_url="https://t.x")
    assert primero["ok"] is False
    segundo = test_emuwarez_connection(api_key=CLAVE, base_url="https://t.x")
    assert segundo["ok"] is False and segundo["status"] == "rate_limited"
    assert len(llamadas) == 1  # el 429 pausa: la segunda no sale
    assert CLAVE not in str(segundo)


def test_el_limitador_de_la_aplicacion_usa_el_reloj_monotono():
    import inspect
    assert inspect.signature(Limitador).parameters["reloj"].default is time.monotonic
