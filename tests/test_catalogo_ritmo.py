"""La descarga del catálogo de eMuwarez: un 429 repite la página en vez de abortar la sincronización."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.integrations import emu
from emuwarez_uploadrr.integrations.base import IntegrationError


def _pagina(ids):
    return {"data": [{"id": i} for i in ids], "meta": {"last_page": 1, "total": len(ids)}}


def test_un_429_repite_la_pagina(monkeypatch, limitador_emuwarez):
    respuestas = [IntegrationError("HTTP 429", status=429), _pagina([3, 2, 1])]

    def falso(method, url):
        r = respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(emu, "request_json", falso)
    assert [t["id"] for t in emu.emu_fetch_all_torrents("k", per_page=100)] == [3, 2, 1]
    assert sum(limitador_emuwarez.reloj.dormidas) == pytest.approx(emu.EMU_ESPERA_429)


def test_otros_errores_no_se_reintentan(monkeypatch):
    llamadas = []

    def falso(method, url):
        llamadas.append(url)
        raise IntegrationError("HTTP 503", status=503)

    monkeypatch.setattr(emu, "request_json", falso)
    with pytest.raises(IntegrationError):
        emu.emu_fetch_all_torrents("k")
    assert len(llamadas) == 1


def test_un_429_real_llega_como_status_y_se_reintenta(monkeypatch, http_falso):
    from tests.http_falso import respuesta

    http_falso.responde(
        respuesta(429, cuerpo=b"slow down"),
        respuesta(200, json={"data": [{"id": 5}], "meta": {"last_page": 1}}),
    )
    assert [t["id"] for t in emu.emu_fetch_all_torrents("k")] == [5]
    assert len(http_falso.peticiones) == 2