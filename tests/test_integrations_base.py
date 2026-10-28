"""Tests for integrations/base.py::request_json's hard wall-clock deadline.

urlopen's own `timeout=` parameter only bounds the connect/read phases once a
socket exists — DNS resolution (getaddrinfo, which runs first) is NOT covered
by it, so a stuck/misconfigured resolver can hang past `timeout` forever with
no exception ever raised. request_json now runs the call in a worker thread
and enforces `.result(timeout=...)` on the calling side, which bounds the
WHOLE call regardless of what's actually stuck.
"""
from __future__ import annotations

import io
import time
import urllib.error
from unittest.mock import patch

import pytest

from emuwarez_uploadrr.integrations.base import IntegrationError, request_json, url_sin_claves


def test_hanging_call_raises_within_the_deadline_not_forever():
    """Simulates a DNS-level hang: urlopen never returns and never raises —
    request_json must still come back with a clear error well before the
    caller would consider it "frozen"."""
    def _hangs_forever(*args, **kwargs):
        time.sleep(3600)

    start = time.monotonic()
    with patch("urllib.request.urlopen", side_effect=_hangs_forever):
        with pytest.raises(IntegrationError, match="Tiempo de espera agotado") as info:
            request_json("GET", "https://example.invalid/api?api_key=CLAVETMDB456", timeout=1)
    elapsed = time.monotonic() - start
    assert elapsed < 10
    assert "CLAVETMDB456" not in str(info.value)


def test_normal_call_still_returns_the_response():
    class _FakeResp:
        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    with patch("urllib.request.urlopen", return_value=_FakeResp()):
        result = request_json("GET", "https://example.invalid/api")
    assert result == {"ok": True}


_URL_CON_CLAVE = "https://emuwarez.invalid/api/requests?api_token=CLAVESECRETA123&page=1"


class _RespNoJson:
    def read(self):
        return b"<html>mantenimiento</html>"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("fallo", [
    urllib.error.HTTPError(_URL_CON_CLAVE, 401, "Unauthorized", None, io.BytesIO(b"no autorizado")),
    urllib.error.URLError("Name or service not known"),
])
def test_el_error_no_lleva_la_clave(fallo):
    """Estos mensajes acaban en app.log, task_runs y la respuesta HTTP."""
    with patch("urllib.request.urlopen", side_effect=fallo):
        with pytest.raises(IntegrationError) as info:
            request_json("GET", _URL_CON_CLAVE)
    assert "CLAVESECRETA123" not in str(info.value)
    assert "api_token=***" in str(info.value)


def test_una_respuesta_no_json_no_lleva_la_clave():
    with patch("urllib.request.urlopen", return_value=_RespNoJson()):
        with pytest.raises(IntegrationError) as info:
            request_json("GET", _URL_CON_CLAVE)
    assert "CLAVESECRETA123" not in str(info.value)


def test_url_sin_claves_deja_el_resto_igual():
    assert url_sin_claves(_URL_CON_CLAVE) == "https://emuwarez.invalid/api/requests?api_token=***&page=1"
    assert url_sin_claves("http://radarr:7878/api/v3/movie") == "http://radarr:7878/api/v3/movie"


def test_url_sin_claves_quita_usuario_y_contrasena():
    assert url_sin_claves("http://usu:pass@radarr:7878/api?apikey=K") == "http://radarr:7878/api?apikey=***"


def test_el_cuerpo_del_error_no_repite_la_clave():
    cuerpo = io.BytesIO(b"Bad request for /api?api_token=CLAVESECRETA123")
    fallo = urllib.error.HTTPError(_URL_CON_CLAVE, 400, "Bad", None, cuerpo)
    with patch("urllib.request.urlopen", side_effect=fallo):
        with pytest.raises(IntegrationError) as info:
            request_json("GET", _URL_CON_CLAVE)
    assert "CLAVESECRETA123" not in str(info.value)
