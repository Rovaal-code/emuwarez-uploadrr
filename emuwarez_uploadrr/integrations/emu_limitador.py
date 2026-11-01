"""Un solo limitador para todas las peticiones a la API de eMuwarez.

eMuwarez (UNIT3D) deja 30 peticiones por minuto por API key (cabecera x-ratelimit-limit: 30). Antes cada recorrido
se pausaba por su cuenta y nada coordinaba a los que llaman a la vez: la sincronización del catálogo, la de
peticiones, el perfil, «Probar conexión» y la comprobación de antes de subir salen de hilos distintos del mismo
proceso (el threadpool de FastAPI, el planificador, los hilos de subida). Todos pasan ahora por aquí.

- Ventana deslizante de 60 s por API key (se guarda su huella, no la clave). Una ventana deslizante con N en
  cualquier tramo de 60 s también cumple con la ventana fija por minuto que cuenta Laravel.
- Se planifica para 28, no 30: la misma clave la usan también otras aplicaciones del usuario.
- Los recorridos largos (páginas del catálogo y de peticiones) solo pueden llenar `capacidad - reserva_interactiva`
  huecos de la ventana; el resto queda para las consultas sueltas, que así no se ponen a la cola de un catálogo de
  130 páginas. Una consulta suelta que tendría que esperar más de `espera_maxima_interactiva` no espera: falla con
  un mensaje claro (solo pasa justo después de un 429).
- Un 429 pausa a todos los que usan esa clave (`penalizar`), no solo al que lo recibió.
- La espera se calcula con el cerrojo cogido y se duerme fuera, a tramos cortos, volviendo a mirar después de cada
  uno: un 429 que llega mientras tanto alarga la espera de los demás. Nunca se duerme con el cerrojo cogido.
- No hay hilos propios: espera el hilo que llama, y los recorridos largos van en hilos daemon, así que apagar la
  aplicación no se queda esperando al limitador.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import deque
from typing import Callable, Optional

from .base import IntegrationError

logger = logging.getLogger("emuwarez.emu")

EMU_LIMITE_POR_MINUTO = 28  # eMuwarez deja 30; dos de margen
EMU_VENTANA = 60.0
EMU_RESERVA_INTERACTIVA = 8  # los recorridos largos se quedan en 20 por minuto
EMU_ESPERA_MAXIMA_INTERACTIVA = 15.0
# Tras un 429 sin más datos: una ventana entera, que es lo máximo que puede faltar para que se vacíe.
EMU_ESPERA_429 = 60.0
_TRAMO = 1.0  # cada cuánto se vuelve a mirar mientras se espera
_AVISO_ESPERA = 10.0  # una espera así de larga se apunta en el registro


class _Estado:
    __slots__ = ("marcas", "penalizado_hasta")

    def __init__(self) -> None:
        self.marcas: deque[float] = deque()
        self.penalizado_hasta = 0.0


class Limitador:
    def __init__(
        self,
        *,
        capacidad: int = EMU_LIMITE_POR_MINUTO,
        ventana: float = EMU_VENTANA,
        reserva_interactiva: int = EMU_RESERVA_INTERACTIVA,
        espera_maxima_interactiva: float = EMU_ESPERA_MAXIMA_INTERACTIVA,
        tramo: float = _TRAMO,
        reloj: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], object] = time.sleep,
    ) -> None:
        if not 0 <= reserva_interactiva < capacidad:
            raise ValueError("la reserva interactiva tiene que dejar algún hueco a los recorridos")
        self.capacidad = capacidad
        self.ventana = ventana
        self.reserva_interactiva = reserva_interactiva
        self.espera_maxima_interactiva = espera_maxima_interactiva
        self.tramo = tramo
        self._reloj = reloj
        self._dormir = dormir
        self._cerrojo = threading.Lock()
        self._claves: dict[str, _Estado] = {}

    # -- con el cerrojo cogido ----------------------------------------------

    def _estado(self, huella: str, ahora: float) -> _Estado:
        # Las claves que ya no tienen nada pendiente se olvidan (p. ej. una clave escrita para probarla).
        for otra in [h for h, e in self._claves.items()
                     if h != huella and e.penalizado_hasta <= ahora
                     and (not e.marcas or e.marcas[-1] <= ahora - self.ventana)]:
            del self._claves[otra]
        return self._claves.setdefault(huella, _Estado())

    def _espera(self, estado: _Estado, ahora: float, interactiva: bool) -> float:
        marcas = estado.marcas
        while marcas and marcas[0] <= ahora - self.ventana:
            marcas.popleft()
        if estado.penalizado_hasta > ahora:
            return estado.penalizado_hasta - ahora
        limite = self.capacidad if interactiva else self.capacidad - self.reserva_interactiva
        if len(marcas) < limite:
            return 0.0
        # Hay hueco cuando la marca que deja `limite - 1` más nuevas sale de la ventana.
        return marcas[len(marcas) - limite] + self.ventana - ahora

    # -- lo que usan los conectores -----------------------------------------

    def esperar_turno(self, api_key: Optional[str], *, interactiva: bool = False) -> float:
        """Espera a que haya hueco para una petición con esta clave y la apunta. Devuelve lo que ha esperado.

        Una consulta interactiva que tendría que esperar más de `espera_maxima_interactiva` lanza IntegrationError
        (sin URL ni clave) en vez de esperar; un recorrido largo espera lo que haga falta."""
        huella = _huella(api_key)
        inicio = self._reloj()
        while True:
            with self._cerrojo:
                ahora = self._reloj()
                espera = self._espera(self._estado(huella, ahora), ahora, interactiva)
                if espera <= 0:
                    self._claves[huella].marcas.append(ahora)
                    break
            if interactiva and (ahora - inicio) + espera > self.espera_maxima_interactiva:
                raise IntegrationError(
                    "eMuwarez: se ha llegado al límite de peticiones por minuto de la API key; "
                    f"prueba dentro de {max(1, round(espera))} s")
            self._dormir(min(espera, self.tramo))
        esperado = ahora - inicio
        if esperado >= _AVISO_ESPERA:
            logger.info("eMuwarez: %s ha esperado %.0f s por el límite de peticiones por minuto",
                        "una consulta" if interactiva else "una página", esperado)
        elif esperado > 0:
            logger.debug("eMuwarez: espera de %.1f s por el límite de peticiones", esperado)
        return esperado

    def penalizar(self, api_key: Optional[str], segundos: float = EMU_ESPERA_429) -> None:
        """eMuwarez ha respondido 429: nadie más usa esta clave hasta dentro de `segundos`. Nunca lanza."""
        try:
            with self._cerrojo:
                ahora = self._reloj()
                estado = self._estado(_huella(api_key), ahora)
                estado.penalizado_hasta = max(estado.penalizado_hasta, ahora + segundos)
            logger.warning("eMuwarez ha limitado las peticiones (429): todas esperan %.0f s", segundos)
        except Exception:  # noqa: BLE001 — quien llama ya está tratando el 429
            logger.debug("No se pudo apuntar el 429 de eMuwarez", exc_info=True)


def _huella(api_key: Optional[str]) -> str:
    return hashlib.sha256((api_key or "").encode()).hexdigest()


# El de la aplicación. Se busca cada vez (no se copia en otros módulos) para que los tests lo puedan cambiar.
LIMITADOR = Limitador()


def esperar_turno(api_key: Optional[str], *, interactiva: bool = False) -> float:
    return LIMITADOR.esperar_turno(api_key, interactiva=interactiva)


def penalizar(api_key: Optional[str], segundos: float = EMU_ESPERA_429) -> None:
    LIMITADOR.penalizar(api_key, segundos)
