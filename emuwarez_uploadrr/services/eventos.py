"""Avisos del servidor a las interfaces abiertas.

Hasta ahora la interfaz PREGUNTA cada pocos segundos si ha cambiado algo: once
sondeos distintos, unas 25 peticiones por minuto con la aplicación quieta. Esto
es el camino contrario, que el servidor AVISE cuando algo cambia de verdad.

Es un bus en memoria, y eso se sostiene sobre un hecho concreto: `cli.py` llama
a `uvicorn.run()` sin `workers`, o sea un único proceso web. Con varios procesos
un aviso publicado en uno no llegaría a los clientes conectados al otro, y haría
falta algo por fuera (Redis o similar). Si algún día se pasa a varios workers,
ESTE módulo es el que hay que cambiar, y no se enterará solo: lo vigila
tests/test_eventos.py.

Las subidas corren en otro proceso (`subprocess.Popen`), pero eso no rompe nada
aquí: el proceso web es quien lee su salida línea a línea y la parsea, así que
ya tiene el progreso en la mano antes de escribirlo en la base de datos. Cuando
toque publicarlo (fase 2) el gancho estará dentro de este proceso.

Publicar NUNCA puede tumbar a quien publica. Un aviso perdido cuesta que la
interfaz tarde un poco más en enterarse; una excepción propagada desde aquí
cortaría una sincronización a medias. Por eso todo lo de abajo traga.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Un aviso significa "esto ha cambiado, vuelve a pedirlo", no lleva los datos.
# El cliente recarga por la API de siempre, así que un aviso perdido o repetido
# no descuadra nada.
EVENTO_SYNC_TERMINADA = "sync-terminada"
# Una subida cambió de estado (encolada, subiendo, terminada, fallida...).
EVENTO_SUBIDA_ESTADO = "subida-estado"
# Una subida avanzó dentro de su fase.
EVENTO_SUBIDA_PROGRESO = "subida-progreso"
# Hay líneas nuevas en el registro de una subida. No lleva las líneas: el
# proceso escupe cientos por segundo y mandarlas por aquí sería convertir el
# canal en una tubería de logs. Solo dice que las hay, y quien mire esa pantalla
# las pide.
EVENTO_SUBIDA_LOG = "subida-log"

# Cuántos avisos se le guardan a un cliente que no lee. Al llenarse se tira el
# más viejo: son órdenes de recargar, y la última vale por todas las anteriores.
# Un cliente atascado no puede hacer crecer la memoria del servidor.
_MAX_EN_COLA = 32


@dataclass
class _Suscriptor:
    cola: asyncio.Queue
    # El bucle en el que vive esta cola. Se guarda porque quien publica es casi
    # siempre un HILO (la sincronización corre en un thread), y una asyncio.Queue
    # no se puede tocar desde fuera de su bucle sin call_soon_threadsafe.
    bucle: asyncio.AbstractEventLoop
    id: int = field(default=0)


_suscriptores: list[_Suscriptor] = []
_candado = threading.Lock()
_siguiente_id = 0


def _nuevo_id() -> int:
    global _siguiente_id
    _siguiente_id += 1
    return _siguiente_id


def suscribir() -> _Suscriptor:
    """Da de alta una conexión. Se llama DESDE el bucle de eventos."""
    global _suscriptores
    sus = _Suscriptor(cola=asyncio.Queue(maxsize=_MAX_EN_COLA),
                      bucle=asyncio.get_running_loop())
    with _candado:
        sus.id = _nuevo_id()
        _suscriptores = [*_suscriptores, sus]
    return sus


def desuscribir(sus: _Suscriptor) -> None:
    """Da de baja una conexión. Llamarlo siempre, también si se cortó mal."""
    global _suscriptores
    with _candado:
        _suscriptores = [s for s in _suscriptores if s.id != sus.id]


def cuantos_escuchan() -> int:
    with _candado:
        return len(_suscriptores)


def _encolar(sus: _Suscriptor, aviso: dict) -> None:
    """Mete el aviso en la cola de un suscriptor, desde el bucle de este."""
    try:
        sus.cola.put_nowait(aviso)
    except asyncio.QueueFull:
        # Cliente atascado: se tira el más viejo y entra el nuevo. Perder un
        # "recarga" antiguo no importa cuando hay otro más reciente detrás.
        try:
            sus.cola.get_nowait()
            sus.cola.put_nowait(aviso)
        except Exception:
            pass


def publicar(tipo: str, datos: Optional[dict[str, Any]] = None) -> int:
    """Avisa a todas las interfaces conectadas. Devuelve a cuántas.

    Se puede llamar desde cualquier hilo, y no lanza nunca: quien publica está
    terminando una sincronización o una subida, y eso no se corta porque un
    cliente se haya desconectado mal.
    """
    try:
        aviso = {"tipo": tipo, **(datos or {})}
        with _candado:
            destinatarios = list(_suscriptores)
        enviados = 0
        for sus in destinatarios:
            try:
                if sus.bucle.is_closed():
                    continue
                sus.bucle.call_soon_threadsafe(_encolar, sus, aviso)
                enviados += 1
            except Exception:                   # bucle parado, cola muerta, lo que sea
                logger.debug("no se pudo avisar a un suscriptor", exc_info=True)
        return enviados
    except Exception:
        # La red exterior, y no es paranoia: esto se llama desde el `finally` de
        # una sincronización, así que cualquier cosa que se escape de aquí la
        # cortaría a medias. Un aviso perdido cuesta que la interfaz tarde un
        # poco más en enterarse; una sincronización rota cuesta bastante más.
        logger.exception("fallo publicando un aviso")
        return 0


_ultimo_agrupado: dict[str, float] = {}
_candado_agrupar = threading.Lock()


def publicar_agrupado(clave: str, tipo: str, datos: Optional[dict[str, Any]] = None,
                      cada: float = 1.0, *, reloj=None) -> bool:
    """Publica como mucho una vez cada `cada` segundos para la misma `clave`.

    Para lo que ocurre a chorro. El registro de una subida escupe cientos de
    líneas por segundo, y un aviso por línea convertiría el canal en una
    tubería de logs: la interfaz recargaría sin parar y sería más caro que el
    sondeo que viene a sustituir.

    Se puede tirar sin miedo porque un aviso solo dice "esto ha cambiado, vuelve
    a pedirlo": el que sí sale trae consigo todo lo que se perdieron los que no.

    Devuelve True si lo publicó.
    """
    ahora = (reloj or time.monotonic)()
    with _candado_agrupar:
        anterior = _ultimo_agrupado.get(clave)
        if anterior is not None and (ahora - anterior) < cada:
            return False
        _ultimo_agrupado[clave] = ahora
    publicar(tipo, datos)
    return True


def olvidar_todos() -> None:
    """Vacía la lista de suscriptores. Para los tests."""
    global _suscriptores
    with _candado:
        _suscriptores = []
    with _candado_agrupar:
        _ultimo_agrupado.clear()
