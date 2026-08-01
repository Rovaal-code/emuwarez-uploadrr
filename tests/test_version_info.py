"""La comprobación de versión nueva.

El repositorio y el paquete son privados, así que la aplicación no puede
preguntarle al registro. Compara el commit sellado en la imagen con el de un
manifiesto público. Lo que se prueba aquí es que NO MIENTE en ninguno de los
casos raros: sin sellar, sin manifiesto, con la red caída o con un JSON roto.
"""
from __future__ import annotations

import json

import pytest

from emuwarez_uploadrr.services import version_info as vi


@pytest.fixture(autouse=True)
def _sin_cache():
    vi._cache.update({"cuando": 0.0, "datos": None, "error": None})
    yield
    vi._cache.update({"cuando": 0.0, "datos": None, "error": None})


def _sellar(monkeypatch, commit=None, fecha=None):
    monkeypatch.setenv("APP_COMMIT", commit or "")
    monkeypatch.setenv("APP_BUILD_DATE", fecha or "")


def _manifiesto(monkeypatch, datos=None, error=None):
    monkeypatch.setattr(vi, "_descargar_manifiesto", lambda: (datos, error))


def test_al_dia_cuando_el_commit_coincide(monkeypatch):
    _sellar(monkeypatch, "abc123def456")
    _manifiesto(monkeypatch, {"commit": "abc123def456", "digest": "sha256:xyz",
                              "fecha": "2026-08-02", "notas": "algo"})
    r = vi.estado_de_version()
    assert r["estado"] == "al_dia"
    assert r["digest"] == "sha256:xyz"       # al día, el digest publicado es el tuyo
    assert r["commit_corto"] == "abc123d"


def test_avisa_cuando_hay_una_mas_nueva(monkeypatch):
    _sellar(monkeypatch, "viejo000")
    _manifiesto(monkeypatch, {"commit": "nuevo111", "digest": "sha256:nuevo",
                              "fecha": "2026-08-02", "notas": "el arreglo del 480p"})
    r = vi.estado_de_version()
    assert r["estado"] == "hay_novedad"
    assert r["ultima"]["notas"] == "el arreglo del 480p"
    # Y NO se enseña el digest publicado como si fuera el tuyo.
    assert r["digest"] is None
    assert r["ultima"]["digest"] == "sha256:nuevo"


def test_sin_sellar_no_se_inventa_un_estado(monkeypatch):
    """Ejecutando desde el código fuente en vez de desde la imagen."""
    _sellar(monkeypatch, None)
    _manifiesto(monkeypatch, {"commit": "loquesea"})
    r = vi.estado_de_version()
    assert r["estado"] == "desconocido"
    assert "no lleva sellado el commit" in r["motivo"]


def test_sin_manifiesto_lo_dice(monkeypatch):
    _sellar(monkeypatch, "abc123")
    _manifiesto(monkeypatch, None, "El manifiesto de versiones no existe todavía.")
    r = vi.estado_de_version()
    assert r["estado"] == "desconocido"
    assert "no existe todavía" in r["motivo"]


def test_la_red_caida_no_rompe_nada(monkeypatch):
    _sellar(monkeypatch, "abc123")
    _manifiesto(monkeypatch, None, "No se pudo consultar el manifiesto: timeout")
    r = vi.estado_de_version()
    assert r["estado"] == "desconocido"
    assert r["version"]                       # lo propio se sigue enseñando
    assert r["commit_corto"] == "abc123"


def test_un_manifiesto_sin_commit_no_cuenta(monkeypatch):
    _sellar(monkeypatch, "abc123")
    _manifiesto(monkeypatch, {"digest": "sha256:x"})
    assert vi.estado_de_version()["estado"] == "desconocido"


def test_la_cache_evita_consultar_en_cada_carga(monkeypatch):
    _sellar(monkeypatch, "abc123")
    llamadas = []

    def falso():
        llamadas.append(1)
        return {"commit": "abc123"}, None

    monkeypatch.setattr(vi, "_descargar_manifiesto", falso)
    vi.estado_de_version()
    vi.estado_de_version()
    assert len(llamadas) == 1, "consulta en cada carga de la pestaña"
    vi.estado_de_version(forzar=True)          # el botón "Comprobar ahora"
    assert len(llamadas) == 2


def test_un_json_roto_se_trata_como_error(monkeypatch):
    class _R:
        def read(self): return b"{ esto no es json"
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(vi.urllib.request, "urlopen", lambda *a, **kw: _R())
    datos, error = vi._descargar_manifiesto()
    assert datos is None and "No se pudo leer" in error
