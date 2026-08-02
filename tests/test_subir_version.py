"""El número de versión que anuncia la notificación.

La tarjeta y la notificación anuncian la versión por su NÚMERO ("Hay una
versión más nueva: v0.2.1"). Si dos despliegues llevan el mismo número, quien
lo lea no puede distinguirlos: el aviso dice lo mismo las dos veces. La
comparación interna se hace por commit y sigue funcionando, pero el mensaje al
usuario deja de servir.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]


def _cargar(nombre: str):
    ruta = RAIZ / "scripts" / f"{nombre}.py"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


subir = _cargar("subir_version")


@pytest.mark.parametrize("actual,escala,esperada", [
    ("0.2.0", "patch", "0.2.1"),
    ("0.2.9", "patch", "0.2.10"),
    ("0.2.1", "minor", "0.3.0"),
    ("0.2.1", "major", "1.0.0"),
    ("1.9.9", "minor", "1.10.0"),
])
def test_la_escala_correcta(actual, escala, esperada):
    assert subir.siguiente(actual, escala) == esperada


def test_subir_minor_pone_el_parche_a_cero():
    """0.2.7 -> 0.3.0, no 0.3.7."""
    assert subir.siguiente("0.2.7", "minor") == "0.3.0"
    assert subir.siguiente("0.2.7", "major") == "1.0.0"


@pytest.mark.parametrize("mala", ["0.2", "1.2.3.4", "v0.2.0", "0.2.x", ""])
def test_una_version_rara_se_rechaza_en_vez_de_inventar(mala):
    with pytest.raises(ValueError):
        subir.siguiente(mala, "patch")


def test_lee_la_version_del_paquete():
    from emuwarez_uploadrr import __version__
    texto = (RAIZ / "emuwarez_uploadrr" / "__init__.py").read_text()
    assert subir.leer_version(texto) == __version__


def test_la_version_del_paquete_es_la_que_publica_el_manifiesto():
    """Las dos leen el mismo sitio: si se separan, la imagen diría una cosa y
    el manifiesto otra."""
    publicar = _cargar("publicar_version")
    from emuwarez_uploadrr import __version__
    assert publicar._leer_version() == __version__
