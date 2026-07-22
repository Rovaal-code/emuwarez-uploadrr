"""Tests for integrations/base.py::request_json's hard wall-clock deadline.

urlopen's own `timeout=` parameter only bounds the connect/read phases once a
socket exists — DNS resolution (getaddrinfo, which runs first) is NOT covered
by it, so a stuck/misconfigured resolver can hang past `timeout` forever with
no exception ever raised. request_json now runs the call in a worker thread
and enforces `.result(timeout=...)` on the calling side, which bounds the
WHOLE call regardless of what's actually stuck.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from emuwarez_uploadrr.integrations.base import IntegrationError, request_json


def test_hanging_call_raises_within_the_deadline_not_forever():
    """Simulates a DNS-level hang: urlopen never returns and never raises —
    request_json must still come back with a clear error well before the
    caller would consider it "frozen"."""
    def _hangs_forever(*args, **kwargs):
        time.sleep(3600)

    start = time.monotonic()
    with patch("urllib.request.urlopen", side_effect=_hangs_forever):
        with pytest.raises(IntegrationError, match="Tiempo de espera agotado"):
            request_json("GET", "https://example.invalid/api", timeout=1)
    elapsed = time.monotonic() - start
    assert elapsed < 10


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
