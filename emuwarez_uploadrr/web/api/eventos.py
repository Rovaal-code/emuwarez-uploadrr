"""GET /api/eventos — el canal por el que el servidor avisa a la interfaz.

Server-Sent Events: HTTP normal, una respuesta que no termina, y el servidor va
escribiendo líneas. No son websockets porque el tráfico que falta va en un solo
sentido —servidor → interfaz—; las acciones ya viajan por la API REST de
siempre.

Un aviso solo dice "esto ha cambiado, vuelve a pedirlo". No lleva datos, así
que perderse uno o recibirlo repetido no descuadra nada: el cliente recarga por
donde recargaba. Eso es lo que permite que este canal sea un extra y no una
pieza crítica — si se cae, la aplicación sigue funcionando como antes.

Autenticación: `require_auth` de siempre. Se puede usar aquí porque el cliente
NO usa `EventSource` (que no sabe mandar cabeceras) sino `fetch` leyendo la
respuesta a trozos, que sí manda el `Authorization: Bearer`. La alternativa
habría sido meter el token en la URL, y ahí acaba en los registros del
servidor y en el historial del navegador.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ...services import eventos as bus
from ..dependencies import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eventos", tags=["eventos"])

# Cada cuánto se manda un latido si no ha pasado nada. Sirve para dos cosas:
# detectar la conexión muerta (escribir en un socket cerrado falla, y así se
# limpia el suscriptor) y evitar que un proxy o el navegador corten un flujo
# que lleva mucho callado. Es un comentario SSE (empieza por ':'), el cliente
# lo ignora solo.
_LATIDO_S = 20.0


def _formatear(aviso: dict) -> str:
    """Un aviso en el formato de SSE: una línea 'data:' y una en blanco."""
    return f"data: {json.dumps(aviso, ensure_ascii=False)}\n\n"


@router.get("")
async def eventos(request: Request, _: dict = Depends(require_auth)) -> StreamingResponse:
    """Deja la conexión abierta y va mandando los avisos según ocurren."""

    async def flujo() -> AsyncIterator[str]:
        sus = bus.suscribir()
        try:
            # Un primer latido inmediato: hasta que no llega algo, `fetch` no
            # resuelve, y el cliente no sabría si el canal está vivo o colgado.
            yield ": conectado\n\n"
            while True:
                # Se corta en cuanto el cliente se va. Sin esto un navegador
                # cerrado dejaría el suscriptor y su cola vivos hasta el
                # siguiente intento de escritura.
                if await request.is_disconnected():
                    break
                try:
                    aviso = await asyncio.wait_for(sus.cola.get(), timeout=_LATIDO_S)
                except asyncio.TimeoutError:
                    yield ": latido\n\n"
                    continue
                yield _formatear(aviso)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Que se caiga un cliente no puede ensuciar los registros con una
            # traza cada vez; y desde luego no puede tumbar nada más.
            logger.debug("se cortó un cliente de /api/eventos", exc_info=True)
        finally:
            bus.desuscribir(sus)

    return StreamingResponse(
        flujo(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Sin esto, nginx delante bufferiza el flujo y no llega nada hasta
            # que se llena el búfer: el fallo es silencioso y desconcertante.
            "X-Accel-Buffering": "no",
        },
    )
