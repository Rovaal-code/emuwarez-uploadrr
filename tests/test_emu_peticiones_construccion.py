"""Cómo se construyen las peticiones a eMuwarez y cómo se recorren sus páginas.

Todo con `request_json` falso: ningún test habla con el tracker."""
from __future__ import annotations

import io
import types
import urllib.error
import urllib.parse
from unittest.mock import patch

import pytest

from emuwarez_uploadrr.integrations import emu
from emuwarez_uploadrr.integrations.base import IntegrationError


@pytest.fixture
def pedidas(monkeypatch):
    """Guarda cada URL pedida y responde con lo que haya en `respuestas` (o {}); si es una
    excepción, la lanza. Las esperas no duermen: se anotan en `dormidas`."""
    registro = {"urls": [], "respuestas": [], "dormidas": []}

    def falso(method, url, **kw):
        registro["urls"].append(url)
        respuesta = registro["respuestas"].pop(0) if registro["respuestas"] else {}
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(emu, "request_json", falso)
    monkeypatch.setattr(emu, "time", types.SimpleNamespace(sleep=registro["dormidas"].append))
    return registro


def _partes(url):
    p = urllib.parse.urlsplit(url)
    return p.netloc, p.path, dict(urllib.parse.parse_qsl(p.query))


def _pagina_de(url):
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["page"][0]


def test_probar_conexion_pide_un_solo_torrent(pedidas):
    emu.emu_test_connection("KEY", base_url="https://t.x/")
    assert _partes(pedidas["urls"][0]) == ("t.x", "/api/torrents/filter", {"api_token": "KEY", "perPage": "1"})


def test_peticiones_abiertas_de_peliculas_series_y_documentales(pedidas):
    emu.emu_get_requests("KEY", base_url="https://t.x", page=3, per_page=50)
    url = pedidas["urls"][0]
    assert _partes(url)[:2] == ("t.x", "/api/requests/filter")
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(url).query) == {
        "api_token": ["KEY"], "page": ["3"], "perPage": ["50"],
        "filled": ["0"], "category_id[]": ["1", "2", "4"],
    }


def test_por_defecto_pide_paginas_de_cien(pedidas):
    emu.emu_get_requests("KEY")
    assert _partes(pedidas["urls"][0])[2]["perPage"] == "100"


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

def _pagina_peticiones(ids, pagina=1, ultima=1, total=None):
    return {
        "data": [{"id": i} for i in ids],
        "meta": {"current_page": pagina, "last_page": ultima, "total": len(ids) if total is None else total},
    }


def test_recorre_todas_las_paginas_con_seis_segundos_entre_cada_una(pedidas):
    pedidas["respuestas"] = [
        _pagina_peticiones([1, 2], 1, 3, total=5),
        _pagina_peticiones([3, 4], 2, 3, total=5),
        _pagina_peticiones([5], 3, 3, total=5),
    ]
    filas, total = emu.emu_fetch_all_pages("KEY")
    assert [f["id"] for f in filas] == [1, 2, 3, 4, 5]
    assert total == 5
    assert [_pagina_de(u) for u in pedidas["urls"]] == ["1", "2", "3"]
    assert pedidas["dormidas"] == [6.0, 6.0]


def test_una_sola_pagina_no_espera(pedidas):
    pedidas["respuestas"] = [_pagina_peticiones([1, 2])]
    assert emu.emu_fetch_all_pages("KEY") == ([{"id": 1}, {"id": 2}], 2)
    assert pedidas["dormidas"] == []


def test_sin_peticiones_abiertas_es_un_recorrido_completo_y_vacio(pedidas):
    pedidas["respuestas"] = [_pagina_peticiones([])]
    assert emu.emu_fetch_all_pages("KEY") == ([], 0)


def test_un_429_espera_un_minuto_y_repite_la_misma_pagina(pedidas):
    pedidas["respuestas"] = [IntegrationError("HTTP 429", status=429), _pagina_peticiones([1])]
    filas, _ = emu.emu_fetch_all_pages("KEY")
    assert filas == [{"id": 1}]
    assert pedidas["dormidas"] == [60.0]
    assert [_pagina_de(u) for u in pedidas["urls"]] == ["1", "1"]


def test_un_429_que_no_se_va_acaba_en_un_error_claro(pedidas):
    pedidas["respuestas"] = [IntegrationError("HTTP 429 en https://emu-warez.com/api/requests/filter", status=429)] * 4
    with pytest.raises(IntegrationError) as e:
        emu.emu_fetch_all_pages("KEY")
    assert str(e.value) == "eMuwarez ha limitado las peticiones; prueba en unos minutos"
    assert e.value.status == 429
    assert pedidas["dormidas"] == [60.0, 60.0, 60.0]
    assert len(pedidas["urls"]) == 4


@pytest.mark.parametrize("estado", [401, 403])
def test_una_clave_rechazada_para_enseguida(pedidas, estado):
    pedidas["respuestas"] = [IntegrationError(f"HTTP {estado} en https://emu-warez.com/x: Unauthenticated.", status=estado)]
    with pytest.raises(IntegrationError) as e:
        emu.emu_fetch_all_pages("KEY")
    assert str(e.value) == "eMuwarez ha rechazado la API key (¿ratio por debajo de 1?)"
    assert len(pedidas["urls"]) == 1 and pedidas["dormidas"] == []


@pytest.mark.parametrize("estado, texto", [
    (401, "eMuwarez ha rechazado la API key (¿ratio por debajo de 1?)"),
    (429, "eMuwarez ha limitado las peticiones; prueba en unos minutos"),
    (500, None),
])
def test_ningun_error_lleva_la_clave(monkeypatch, estado, texto):
    """Con request_json de verdad: ni el mensaje claro ni el que pasa tal cual enseñan la clave."""
    monkeypatch.setattr(emu, "time", types.SimpleNamespace(sleep=lambda s: None))
    clave = "CLAVESECRETA123"

    def responde(req, **kw):
        raise urllib.error.HTTPError(req.full_url, estado, "x", {}, io.BytesIO(f"error con {req.full_url}".encode()))

    with patch("urllib.request.urlopen", side_effect=responde):
        with pytest.raises(IntegrationError) as e:
            emu.emu_fetch_all_pages(clave)
    assert clave not in str(e.value)
    assert texto is None or str(e.value) == texto


@pytest.mark.parametrize("respuesta", [[{"id": 1}], "texto", {"data": None}, {"otra": 1}])
def test_una_respuesta_que_no_se_reconoce_no_se_da_por_buena(pedidas, respuesta):
    pedidas["respuestas"] = [respuesta]
    with pytest.raises(IntegrationError, match="no se reconoce"):
        emu.emu_fetch_all_pages("KEY")


def test_mas_paginas_de_las_permitidas_es_un_error_sin_seguir_pidiendo(pedidas):
    pedidas["respuestas"] = [_pagina_peticiones([1], 1, emu.EMU_PETICIONES_MAX_PAGINAS + 1)]
    with pytest.raises(IntegrationError, match="más de"):
        emu.emu_fetch_all_pages("KEY")
    assert len(pedidas["urls"]) == 1


def test_si_el_total_cambia_a_mitad_del_recorrido_no_se_da_por_completo(pedidas):
    pedidas["respuestas"] = [_pagina_peticiones([1], 1, 2, total=3), _pagina_peticiones([2], 2, 2, total=2)]
    _, total = emu.emu_fetch_all_pages("KEY")
    assert total is None


def test_sin_meta_es_una_pagina_y_no_hay_total(pedidas):
    pedidas["respuestas"] = [{"data": [{"id": 1}]}]
    assert emu.emu_fetch_all_pages("KEY") == ([{"id": 1}], None)


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
