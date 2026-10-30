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


def test_el_manifiesto_se_escribe_en_utf8(monkeypatch, tmp_path):
    """La app lo lee como UTF-8. Sin `encoding`, en Windows salía en cp1252 y
    la tarjeta de Diagnóstico fallaba en la primera tilde de la nota. En Linux
    el defecto ya es UTF-8, así que se mira el argumento y no los bytes."""
    publicar = _cargar("publicar_version")
    codificaciones = []
    original = pathlib.Path.write_text

    def _write_text(self, datos, *args, **kwargs):
        codificaciones.append(kwargs.get("encoding"))
        return original(self, datos, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "write_text", _write_text)
    monkeypatch.setattr(publicar.subprocess, "run", lambda *a, **k: None)
    monkeypatch.chdir(tmp_path)

    publicar.publicar({"commit": "abc1234", "notas": "Actualización"}, "x/y")
    monkeypatch.setattr("sys.argv", ["publicar_version.py", "--notas", "Actualización"])
    monkeypatch.setattr(publicar, "_git", lambda *a: "abc1234")
    assert publicar.main() == 0

    assert codificaciones == ["utf-8", "utf-8"]
    assert "ó" in (tmp_path / "latest.json").read_bytes().decode("utf-8")


def test_solo_comprobar_para_antes_de_construir_si_la_version_ya_esta(monkeypatch, tmp_path):
    """desplegar.sh lo llama antes de construir: repetir una versión ya publicada
    movería :latest y :X.Y.Z a otro digest mientras el manifiesto sigue en el viejo."""
    publicar = _cargar("publicar_version")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(publicar, "_git", lambda *a: "abc1234")
    monkeypatch.setattr(publicar, "publicar", lambda *a: pytest.fail("no debe publicar"))
    monkeypatch.setattr("sys.argv", ["publicar_version.py", "--solo-comprobar",
                                     "--notas", "Mejoras", "--repo"])

    monkeypatch.setattr(publicar, "version_publicada", lambda repo: publicar._leer_version())
    assert publicar.main() == 1

    monkeypatch.setattr(publicar, "version_publicada", lambda repo: "0.0.1")
    assert publicar.main() == 0
    assert not (tmp_path / "latest.json").exists()


def test_si_no_se_puede_leer_el_manifiesto_se_para(monkeypatch):
    """Un manifiesto que no existe es «nada publicado»; uno que no se puede leer
    (sin red, sin permiso) no: comprobar a ciegas dejaría repetir una versión."""
    publicar = _cargar("publicar_version")

    def _gh(stderr):
        def run(*a, **k):
            raise publicar.subprocess.CalledProcessError(1, "gh", stderr=stderr)
        return run

    monkeypatch.setattr(publicar.subprocess, "run", _gh("gh: Not Found (HTTP 404)"))
    assert publicar.version_publicada("x/y") is None

    monkeypatch.setattr(publicar.subprocess, "run", _gh("gh: Bad credentials (HTTP 401)"))
    with pytest.raises(RuntimeError):
        publicar.version_publicada("x/y")

    monkeypatch.setattr(publicar, "_git", lambda *a: "abc1234")
    monkeypatch.setattr("sys.argv", ["publicar_version.py", "--solo-comprobar",
                                     "--notas", "Mejoras", "--repo"])
    assert publicar.main() == 1
