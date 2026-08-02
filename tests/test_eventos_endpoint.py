"""GET /api/eventos, el canal abierto, y quién publica en él.

El bus por dentro está en test_eventos.py. Aquí, las dos cosas que solo se ven
desde fuera: que el canal esté protegido igual que el resto de la API, y que
una sincronización que termina avise de verdad, que es todo el sentido de la
fase 1.

El flujo se prueba tirando del generador a mano en vez de con `client.stream`.
No es por comodidad: la respuesta NO TERMINA nunca —esa es su gracia— y el
cliente de pruebas se queda esperando un final que no llega. Tirando del
generador se lee exactamente lo que se quiere comprobar y se cierra.
"""
from __future__ import annotations

import asyncio

import pytest

from emuwarez_uploadrr.services import eventos
from emuwarez_uploadrr.web.api import eventos as endpoint


@pytest.fixture(autouse=True)
def _sin_suscriptores():
    eventos.olvidar_todos()
    yield
    eventos.olvidar_todos()


class _PeticionFalsa:
    """Lo justo que el endpoint usa de Request: si el cliente sigue ahí."""

    def __init__(self, cortes: int | None = None):
        self.consultas = 0
        self._cortar_en = cortes

    async def is_disconnected(self) -> bool:
        self.consultas += 1
        return self._cortar_en is not None and self.consultas > self._cortar_en


async def _abrir(peticion) -> object:
    respuesta = await endpoint.eventos(peticion, _={})
    return respuesta.body_iterator


async def _siguiente(flujo, timeout: float = 2.0) -> str:
    trozo = await asyncio.wait_for(flujo.__anext__(), timeout)
    return trozo.decode() if isinstance(trozo, bytes) else trozo


# ─────────────────────────── el canal ───────────────────────────

def test_el_canal_pide_autenticacion(client):
    """Un canal abierto sin token sería una forma de saber cuándo alguien está
    sincronizando sin haber entrado."""
    assert client.get("/api/eventos").status_code == 401


def test_dice_que_esta_vivo_nada_mas_abrirse():
    """El primer latido sale de inmediato a propósito: hasta que no llega algo,
    el `fetch` del cliente no resuelve y no sabría si está conectado o colgado."""
    async def escenario():
        flujo = await _abrir(_PeticionFalsa())
        assert (await _siguiente(flujo)).startswith(":")
        await flujo.aclose()

    asyncio.run(escenario())


def test_las_cabeceras_evitan_que_un_proxy_se_trague_el_flujo():
    async def escenario():
        respuesta = await endpoint.eventos(_PeticionFalsa(), _={})
        assert respuesta.media_type == "text/event-stream"
        # Sin esto, un nginx por delante bufferiza y no llega nada hasta que se
        # llena su búfer. El fallo es silencioso y desconcertante.
        assert respuesta.headers.get("x-accel-buffering") == "no"
        assert respuesta.headers.get("cache-control") == "no-cache"

    asyncio.run(escenario())


def test_lo_publicado_sale_por_el_canal():
    async def escenario():
        peticion = _PeticionFalsa()
        flujo = await _abrir(peticion)
        await _siguiente(flujo)                         # el latido de bienvenida
        eventos.publicar(eventos.EVENTO_SYNC_TERMINADA, {"que": "biblioteca"})
        trozo = await _siguiente(flujo)
        assert trozo.startswith("data: ")
        assert trozo.endswith("\n\n")                   # el fin de mensaje de SSE
        assert '"tipo": "sync-terminada"' in trozo
        assert '"que": "biblioteca"' in trozo
        await flujo.aclose()

    asyncio.run(escenario())


def test_si_no_pasa_nada_manda_un_latido(monkeypatch):
    """Sirve para detectar la conexión muerta y para que un proxy no corte un
    flujo que lleva mucho callado."""
    monkeypatch.setattr(endpoint, "_LATIDO_S", 0.05)

    async def escenario():
        flujo = await _abrir(_PeticionFalsa())
        await _siguiente(flujo)                         # bienvenida
        assert (await _siguiente(flujo)).startswith(":")
        await flujo.aclose()

    asyncio.run(escenario())


def test_al_irse_el_cliente_se_suelta_su_sitio(monkeypatch):
    """Un navegador cerrado no puede dejar su suscriptor y su cola vivos."""
    monkeypatch.setattr(endpoint, "_LATIDO_S", 0.05)

    async def escenario():
        flujo = await _abrir(_PeticionFalsa(cortes=1))
        await _siguiente(flujo)
        assert eventos.cuantos_escuchan() == 1
        with pytest.raises(StopAsyncIteration):         # el flujo se cierra solo
            while True:
                await _siguiente(flujo)
        assert eventos.cuantos_escuchan() == 0

    asyncio.run(escenario())


def test_cerrar_el_flujo_tambien_suelta_el_sitio():
    """El otro camino: el servidor se apaga y cancela los generadores."""
    async def escenario():
        flujo = await _abrir(_PeticionFalsa())
        await _siguiente(flujo)
        assert eventos.cuantos_escuchan() == 1
        await flujo.aclose()
        assert eventos.cuantos_escuchan() == 0

    asyncio.run(escenario())


# ─────────────────────────── quién publica ───────────────────────────

def test_al_terminar_una_sync_de_biblioteca_se_avisa(monkeypatch):
    """El gancho está en el `finally` de `_lib_sync_guard`, que es por donde
    pasan las tres formas de lanzar una sincronización (el botón, la tarea
    programada y el asistente de setup). En cualquier otro sitio se dejaría
    alguna fuera."""
    from emuwarez_uploadrr.services import library

    avisos: list[tuple] = []
    monkeypatch.setattr(library, "publicar",
                        lambda tipo, datos=None: avisos.append((tipo, datos)) or 0)

    with library._lib_sync_guard():
        pass

    assert avisos == [("sync-terminada", {"que": "biblioteca"})]


def test_se_avisa_tambien_cuando_la_sync_falla(monkeypatch):
    """Una sincronización que revienta a la mitad deja datos a medio importar,
    así que lo que hubiera cargado tampoco vale: hay que avisar igual."""
    from emuwarez_uploadrr.services import library

    avisos: list[tuple] = []
    monkeypatch.setattr(library, "publicar",
                        lambda tipo, datos=None: avisos.append((tipo, datos)) or 0)

    with pytest.raises(RuntimeError):
        with library._lib_sync_guard():
            raise RuntimeError("se cayó Sonarr")

    assert avisos == [("sync-terminada", {"que": "biblioteca"})]


def test_avisar_no_puede_tumbar_una_sincronizacion():
    """La garantía que sostiene todo esto.

    El aviso se publica desde el `finally` de una sincronización, o sea desde
    dentro de algo que ya está terminando. Si `publicar` dejara escapar una
    excepción, la cortaría a medias — y encima justo al final, con el trabajo
    hecho y sin marcarlo. Así que `publicar` traga con todo y devuelve 0.
    """
    class _SuscriptorRoto:
        id = 1

        @property
        def bucle(self):
            raise RuntimeError("esto no debería tumbar nada")

    eventos._suscriptores = [_SuscriptorRoto()]
    try:
        assert eventos.publicar(eventos.EVENTO_SYNC_TERMINADA) == 0
    finally:
        eventos.olvidar_todos()
