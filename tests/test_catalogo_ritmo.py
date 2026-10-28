"""La descarga del catálogo de eMuwarez: un 429 repite la página en vez de abortar la sincronización."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.integrations import emu
from emuwarez_uploadrr.integrations.base import IntegrationError


def _pagina(ids):
    return {"data": [{"id": i} for i in ids], "meta": {"last_page": 1, "total": len(ids)}}


def test_un_429_repite_la_pagina(monkeypatch):
    respuestas = [IntegrationError("HTTP 429", status=429), _pagina([3, 2, 1])]
    esperas = []

    def falso(method, url):
        r = respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(emu, "request_json", falso)
    monkeypatch.setattr(emu.time, "sleep", esperas.append)
    assert [t["id"] for t in emu.emu_fetch_all_torrents("k", per_page=100)] == [3, 2, 1]
    assert esperas == [emu.EMU_ESPERA_429]


def test_otros_errores_no_se_reintentan(monkeypatch):
    llamadas = []

    def falso(method, url):
        llamadas.append(url)
        raise IntegrationError("HTTP 500", status=500)

    monkeypatch.setattr(emu, "request_json", falso)
    monkeypatch.setattr(emu.time, "sleep", lambda s: None)
    with pytest.raises(IntegrationError):
        emu.emu_fetch_all_torrents("k")
    assert len(llamadas) == 1
