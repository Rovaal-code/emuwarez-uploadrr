"""Las respuestas grandes de la API van comprimidas, y el canal de avisos no.

La lista de Biblioteca con un filtro amplio eran 21 MB de JSON sin comprimir.
"""
from __future__ import annotations

from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES, GZipMiddleware


def test_las_respuestas_grandes_van_comprimidas(client):
    r = client.get("/api/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_el_canal_de_avisos_no_se_comprime(client):
    """Comprimido, el navegador no recibiría ningún aviso hasta llenar el búfer."""
    gzip = next(m for m in client.app.user_middleware if m.cls is GZipMiddleware)
    assert "text/event-stream" in gzip.kwargs.get("exclude_content_types", DEFAULT_EXCLUDED_CONTENT_TYPES)
