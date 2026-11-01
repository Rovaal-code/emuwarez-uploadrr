"""El bus de avisos del servidor a las interfaces (fase 1 del push).

Lo que se vigila aquí son las tres cosas que, si se rompen, rompen algo más
grande que ellas:

1. Que publicar NO lance nunca. Se publica desde el `finally` de una
   sincronización; una excepción ahí la cortaría a medias.
2. Que un cliente atascado no haga crecer la memoria del servidor.
3. Que se siga sirviendo con UN solo proceso, que es la premisa sobre la que
   se sostiene un bus en memoria.
"""
from __future__ import annotations

import asyncio
import pathlib
import re

import pytest

from emuwarez_uploadrr.services import eventos


@pytest.fixture(autouse=True)
def _sin_suscriptores():
    eventos.olvidar_todos()
    yield
    eventos.olvidar_todos()


def test_publicar_sin_nadie_escuchando_no_lanza():
    """El caso normal: nadie tiene la aplicación abierta y hay una tarea
    programada sincronizando. No puede pasar nada."""
    assert eventos.publicar(eventos.EVENTO_SYNC_TERMINADA) == 0


def test_un_suscriptor_recibe_lo_publicado():
    async def escenario():
        sus = eventos.suscribir()
        try:
            eventos.publicar(eventos.EVENTO_SYNC_TERMINADA, {"que": "biblioteca"})
            aviso = await asyncio.wait_for(sus.cola.get(), timeout=2)
            assert aviso == {"tipo": "sync-terminada", "que": "biblioteca"}
        finally:
            eventos.desuscribir(sus)

    asyncio.run(escenario())


def test_lo_reciben_todas_las_pestanas_abiertas():
    async def escenario():
        unos = [eventos.suscribir() for _ in range(3)]
        try:
            assert eventos.publicar(eventos.EVENTO_SYNC_TERMINADA) == 3
            for sus in unos:
                assert (await asyncio.wait_for(sus.cola.get(), timeout=2))["tipo"] == "sync-terminada"
        finally:
            for sus in unos:
                eventos.desuscribir(sus)

    asyncio.run(escenario())


def test_desuscribir_deja_de_recibir():
    async def escenario():
        sus = eventos.suscribir()
        eventos.desuscribir(sus)
        assert eventos.publicar(eventos.EVENTO_SYNC_TERMINADA) == 0
        assert sus.cola.empty()

    asyncio.run(escenario())


def test_desuscribir_dos_veces_no_lanza():
    """Pasa de verdad: el `finally` del endpoint corre aunque el cliente ya se
    hubiera ido por otro camino."""
    async def escenario():
        sus = eventos.suscribir()
        eventos.desuscribir(sus)
        eventos.desuscribir(sus)
        assert eventos.cuantos_escuchan() == 0

    asyncio.run(escenario())


def test_un_cliente_atascado_no_crece_sin_limite():
    """Un navegador que no lee (portátil suspendido, pestaña congelada) no
    puede hacer que la memoria del servidor suba sin tope."""
    async def escenario():
        sus = eventos.suscribir()
        try:
            for i in range(eventos._MAX_EN_COLA * 3):
                eventos.publicar(eventos.EVENTO_SYNC_TERMINADA, {"n": i})
            await asyncio.sleep(0)          # que corran los call_soon
            assert sus.cola.qsize() <= eventos._MAX_EN_COLA
            # Y lo que queda es lo ÚLTIMO, no lo primero: un "recarga" viejo no
            # vale nada cuando hay otro más reciente detrás.
            ultimo = None
            while not sus.cola.empty():
                ultimo = sus.cola.get_nowait()
            assert ultimo["n"] == eventos._MAX_EN_COLA * 3 - 1
        finally:
            eventos.desuscribir(sus)

    asyncio.run(escenario())


def test_publicar_desde_otro_hilo_llega():
    """El caso real: la sincronización corre en un thread y el suscriptor vive
    en el bucle de asyncio. Es justo lo que `call_soon_threadsafe` resuelve."""
    import threading

    async def escenario():
        sus = eventos.suscribir()
        try:
            hilo = threading.Thread(
                target=lambda: eventos.publicar(eventos.EVENTO_SYNC_TERMINADA, {"que": "biblioteca"}))
            hilo.start()
            hilo.join()
            aviso = await asyncio.wait_for(sus.cola.get(), timeout=2)
            assert aviso["que"] == "biblioteca"
        finally:
            eventos.desuscribir(sus)

    asyncio.run(escenario())


def test_un_bucle_muerto_no_rompe_a_los_vivos():
    """Una pestaña que se fue mal deja un suscriptor con el bucle cerrado. El
    aviso tiene que seguir llegando a las demás."""
    bucle_muerto = asyncio.new_event_loop()
    asyncio.set_event_loop(bucle_muerto)
    zombi = bucle_muerto.run_until_complete(_suscribir())
    bucle_muerto.close()

    async def escenario():
        vivo = eventos.suscribir()
        try:
            assert eventos.publicar(eventos.EVENTO_SYNC_TERMINADA) == 1
            assert (await asyncio.wait_for(vivo.cola.get(), timeout=2))["tipo"] == "sync-terminada"
        finally:
            eventos.desuscribir(vivo)
            eventos.desuscribir(zombi)

    asyncio.run(escenario())


async def _suscribir():
    return eventos.suscribir()


# ─────────────────────────────────────────────────────────────────────────────
# La premisa: un bus en memoria solo vale con UN proceso.
# ─────────────────────────────────────────────────────────────────────────────

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def test_se_sigue_sirviendo_con_un_solo_proceso():
    """El bus de avisos vive en la memoria de UN proceso. Con varios workers,
    lo publicado en uno no llegaría a los clientes conectados al otro y la
    interfaz se quedaría muda a medias — un fallo que no da la cara.

    Si algún día hace falta escalar a varios workers, hay que sacar el bus
    fuera (Redis o similar) ANTES, y este test es el que avisa."""
    fuente = (RAIZ / "emuwarez_uploadrr" / "comandos" / "web.py").read_text()
    llamada = re.search(r"uvicorn\.run\((.*?)\n    \)", fuente, re.S)
    assert llamada, "no encuentro la llamada a uvicorn.run en comandos/web.py"
    assert "workers" not in llamada.group(1), (
        "comandos/web.py ahora arranca uvicorn con varios workers, y services/eventos.py "
        "es un bus EN MEMORIA: los avisos publicados en un proceso no llegan a "
        "los clientes conectados a otro. Saca el bus fuera antes de esto."
    )


def test_parar_el_servidor_no_espera_a_los_clientes_de_eventos(monkeypatch):
    """/api/eventos deja la conexión abierta mientras la pestaña lo esté, y
    uvicorn, al parar, espera a que se cierren todas. Sin un tope, `docker
    stop` agota el stop_grace_period y acaba en SIGKILL (código 137). El tope
    tiene que caber en los 10 s que Docker da por defecto."""
    import argparse

    import uvicorn

    from emuwarez_uploadrr import cli

    recibido = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: recibido.update(kw))
    cli.cmd_web_serve(argparse.Namespace(host="127.0.0.1", port=9494, reload=False))

    tope = recibido.get("timeout_graceful_shutdown")
    assert tope is not None, "uvicorn.run sin timeout_graceful_shutdown"
    assert 0 < tope < 10


# ─────────────────────────────────────────────────────────────────────────────
# Agrupar: para lo que ocurre a chorro (fase 2)
# ─────────────────────────────────────────────────────────────────────────────

class _Reloj:
    """Un reloj de mentira, para no dormir en los tests."""

    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def avanzar(self, s: float) -> None:
        self.t += s


def test_el_primero_sale_siempre():
    reloj = _Reloj()
    assert eventos.publicar_agrupado("log-1", "subida-log", cada=1.0, reloj=reloj) is True


def test_lo_que_viene_pegado_detras_no_sale():
    """El registro de una subida escupe cientos de líneas por segundo. Un aviso
    por línea convertiría el canal en una tubería de logs y saldría más caro
    que el sondeo que viene a sustituir."""
    reloj = _Reloj()
    eventos.publicar_agrupado("log-1", "subida-log", cada=1.0, reloj=reloj)
    for _ in range(500):
        reloj.avanzar(0.001)
        assert eventos.publicar_agrupado("log-1", "subida-log", cada=1.0, reloj=reloj) is False


def test_pasado_el_rato_vuelve_a_salir():
    reloj = _Reloj()
    eventos.publicar_agrupado("log-1", "subida-log", cada=1.0, reloj=reloj)
    reloj.avanzar(1.0)
    assert eventos.publicar_agrupado("log-1", "subida-log", cada=1.0, reloj=reloj) is True


def test_cada_subida_lleva_su_propia_cuenta():
    """Dos subidas a la vez no pueden taparse la una a la otra."""
    reloj = _Reloj()
    assert eventos.publicar_agrupado("log-1", "subida-log", cada=1.0, reloj=reloj) is True
    assert eventos.publicar_agrupado("log-2", "subida-log", cada=1.0, reloj=reloj) is True


def test_el_que_sale_trae_lo_que_se_perdieron_los_que_no():
    """Por qué se puede tirar sin miedo: el aviso no lleva estado, solo dice
    'vuelve a pedirlo'. El que sale vale por todos los que no salieron."""
    async def escenario():
        reloj = _Reloj()
        sus = eventos.suscribir()
        try:
            for i in range(50):
                reloj.avanzar(0.01)
                eventos.publicar_agrupado("progreso-7", eventos.EVENTO_SUBIDA_PROGRESO,
                                          {"job_id": 7, "pct": i}, cada=1.0, reloj=reloj)
            await asyncio.sleep(0)
            # Uno solo, el primero; los 49 siguientes se agruparon en él. Y la
            # interfaz, al recargar, verá el 49 igualmente.
            assert sus.cola.qsize() == 1
        finally:
            eventos.desuscribir(sus)

    asyncio.run(escenario())
