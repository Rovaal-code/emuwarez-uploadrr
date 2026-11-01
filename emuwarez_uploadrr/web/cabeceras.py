"""Cabeceras de seguridad de todas las respuestas.

Un XSS en la interfaz se llevaría el token (vive en localStorage) y, con él, todas las claves de detrás: la CSP
limita de dónde se carga y adónde se conecta la página. La interfaz es de un solo origen: scripts, estilos, fuentes
(en /assets) y fetch, todos de 'self'; los pósters vienen de TMDb y TheTVDB por https y el favicon de Google.
"""
from __future__ import annotations

CSP = (
    "default-src 'self'; img-src 'self' https: data:; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)

_CABECERAS = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"same-origin"),
)

# Swagger y ReDoc cargan su JS de un CDN y arrancan con un script en línea: la CSP los rompería.
_SIN_CSP = ("/api/docs", "/api/redoc")


class CabecerasDeSeguridad:
    """Middleware ASGI puro: un BaseHTTPMiddleware más pondría un envoltorio entre el canal de avisos
    (text/event-stream) y el navegador. Lo que una ruta ya haya puesto, se respeta."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        extra = list(_CABECERAS)
        if not scope["path"].startswith(_SIN_CSP):
            extra.append((b"content-security-policy", CSP.encode("ascii")))

        async def enviar(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                puestas = {nombre.lower() for nombre, _ in headers}
                message["headers"] = headers + [(n, v) for n, v in extra if n not in puestas]
            await send(message)

        await self.app(scope, receive, enviar)
