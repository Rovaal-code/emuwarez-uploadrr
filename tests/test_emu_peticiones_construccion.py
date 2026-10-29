"""Cómo se construyen las peticiones a eMuwarez y cómo se recorren sus páginas.

Todo con `request_json` falso: ningún test habla con el tracker."""
from __future__ import annotations

import urllib.parse

import pytest

from emuwarez_uploadrr.integrations import emu
from emuwarez_uploadrr.integrations.base import IntegrationError


@pytest.fixture
def pedidas(monkeypatch):
    """Guarda cada URL pedida y responde con lo que haya en `respuestas` (o {})."""
    registro = {"urls": [], "respuestas": []}

    def falso(method, url, **kw):
        registro["urls"].append(url)
        return registro["respuestas"].pop(0) if registro["respuestas"] else {}

    monkeypatch.setattr(emu, "request_json", falso)
    return registro


def _partes(url):
    p = urllib.parse.urlsplit(url)
    return p.netloc, p.path, dict(urllib.parse.parse_qsl(p.query))


def test_probar_conexion_pide_un_solo_torrent(pedidas):
    emu.emu_test_connection("KEY", base_url="https://t.x/")
    assert _partes(pedidas["urls"][0]) == ("t.x", "/api/torrents/filter", {"api_token": "KEY", "perPage": "1"})


def test_peticiones_paginadas(pedidas):
    emu.emu_get_requests("KEY", base_url="https://t.x", page=3, per_page=50)
    assert _partes(pedidas["urls"][0])[1:] == ("/api/requests", {"api_token": "KEY", "page": "3", "perPage": "50"})


def test_detalle_de_una_peticion(pedidas):
    emu.emu_get_request_detail("KEY", 42, base_url="https://t.x")
    assert _partes(pedidas["urls"][0])[1] == "/api/requests/42"


def test_busqueda_de_duplicados_por_tmdb_nombre_y_categoria(pedidas):
    emu.emu_search_existing("KEY", query="Dune", base_url="https://t.x", tmdb_id=438631, category="1")
    _, ruta, params = _partes(pedidas["urls"][0])
    assert ruta == "/api/torrents/filter"
    assert params == {"api_token": "KEY", "perPage": "25", "tmdbId": "438631", "name": "Dune", "categories[]": "1"}


def test_busqueda_sin_filtros_solo_lleva_la_clave(pedidas):
    emu.emu_search_existing("KEY", base_url="https://t.x")
    assert _partes(pedidas["urls"][0])[2] == {"api_token": "KEY", "perPage": "25"}


def test_por_defecto_va_al_dominio_de_emuwarez(pedidas):
    emu.emu_get_requests("KEY")
    assert _partes(pedidas["urls"][0])[0] == urllib.parse.urlsplit(emu.EMU_BASE_URL).netloc


# --- Recorrer las páginas de peticiones ------------------------------------

def test_recorre_todas_las_paginas_de_peticiones(pedidas):
    pedidas["respuestas"] = [
        {"data": [{"id": 1}], "meta": {"current_page": 1, "last_page": 2}},
        {"data": [{"id": 2}], "meta": {"current_page": 2, "last_page": 2}},
    ]
    assert emu.emu_fetch_all_pages("KEY") == [{"id": 1}, {"id": 2}]
    assert len(pedidas["urls"]) == 2


def test_una_respuesta_en_lista_se_toma_entera(pedidas):
    pedidas["respuestas"] = [[{"id": 1}, {"id": 2}]]
    assert emu.emu_fetch_all_pages("KEY") == [{"id": 1}, {"id": 2}]


@pytest.mark.parametrize("respuesta", [{"data": []}, {"data": None}, "texto"])
def test_una_pagina_vacia_o_rara_termina(pedidas, respuesta):
    pedidas["respuestas"] = [respuesta]
    assert emu.emu_fetch_all_pages("KEY") == []


# --- Catálogo de torrents ---------------------------------------------------

def _pagina(ids, last_page=1, total=None):
    return {"data": [{"id": i} for i in ids], "meta": {"last_page": last_page, "total": total or len(ids)}}


def test_catalogo_completo_hasta_una_pagina_corta(pedidas):
    pedidas["respuestas"] = [_pagina([5, 4], last_page=2, total=3), _pagina([3], last_page=2, total=3)]
    progreso = []
    out = emu.emu_fetch_all_torrents("KEY", per_page=2, min_interval=0, progress=lambda *a: progreso.append(a))
    assert [t["id"] for t in out] == [5, 4, 3]
    assert progreso == [(1, 2, 2, 3), (2, 2, 3, 3)]
    assert [_partes(u)[2]["page"] for u in pedidas["urls"]] == ["1", "2"]


def test_catalogo_incremental_para_en_el_primer_torrent_conocido(pedidas):
    pedidas["respuestas"] = [_pagina([9, 8], last_page=5), _pagina([7, 6], last_page=5)]
    out = emu.emu_fetch_all_torrents("KEY", per_page=2, min_interval=0, stop_after_id=7)
    assert [t["id"] for t in out] == [9, 8]
    assert len(pedidas["urls"]) == 2


def test_un_fallo_del_progreso_no_corta_la_descarga(pedidas):
    pedidas["respuestas"] = [_pagina([1])]

    def roto(*a):
        raise RuntimeError("barra rota")

    assert [t["id"] for t in emu.emu_fetch_all_torrents("KEY", min_interval=0, progress=roto)] == [1]


# --- Funciones heredadas ----------------------------------------------------

def test_get_requests_sin_endpoint_configurado(monkeypatch):
    monkeypatch.delenv("EMUWAREZ_REQUESTS_URL", raising=False)
    with pytest.raises(IntegrationError, match="no configurado"):
        emu.get_requests("KEY")


@pytest.mark.parametrize("respuesta", [[{"id": 1}], {"requests": [{"id": 1}]}, {"items": [{"id": 1}]}])
def test_get_requests_acepta_varias_formas(pedidas, respuesta):
    pedidas["respuestas"] = [respuesta]
    assert emu.get_requests("KEY", endpoint_url="https://t.x/r") == [{"id": 1}]


def test_get_requests_rechaza_una_forma_desconocida(pedidas):
    pedidas["respuestas"] = [{"otra": 1}]
    with pytest.raises(IntegrationError, match="formato"):
        emu.get_requests("KEY", endpoint_url="https://t.x/r")


def test_crear_peticiones_no_esta_activo():
    with pytest.raises(IntegrationError):
        emu.create_request("KEY", title="X")
