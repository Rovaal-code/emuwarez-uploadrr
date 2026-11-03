"""La imagen Docker: dependencias fijadas, nada escribible en /opt/Uploadrr y el entrypoint sobre /config."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

RAIZ = Path(__file__).resolve().parent.parent
DOCKERFILE = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
WORKFLOWS = RAIZ / ".github" / "workflows"


def _pins() -> dict[str, Version]:
    pins = {}
    for linea in (RAIZ / "constraints.txt").read_text(encoding="utf-8").splitlines():
        if linea.strip() and not linea.startswith("#"):
            req = Requirement(linea)
            espec = list(req.specifier)
            assert len(espec) == 1 and espec[0].operator == "==", f"{linea}: tiene que ser una versión exacta"
            pins[canonicalize_name(req.name)] = Version(espec[0].version)
    return pins


def test_constraints_fija_las_dependencias_web():
    """Cada dependencia del extra `web` tiene pin, y el pin cumple lo que pide pyproject."""
    web = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"]["web"]
    pins = _pins()
    for texto in web:
        req = Requirement(texto)
        nombre = canonicalize_name(req.name)
        assert nombre in pins, f"{req.name} no está en constraints.txt"
        assert req.specifier.contains(pins[nombre]), f"{req.name}=={pins[nombre]} no cumple {req.specifier}"


def test_las_dependencias_van_antes_que_el_codigo_en_el_dockerfile():
    deps = DOCKERFILE.index("pip install --no-cache-dir -c constraints.txt")
    assert deps < DOCKERFILE.index("COPY emuwarez_uploadrr/")
    assert "pip install --no-cache-dir --no-deps -e ." in DOCKERFILE


def test_dockerfile_npm_ci_sin_alternativa_y_nada_de_uploadrr_escribible():
    assert "|| npm install" not in DOCKERFILE
    assert "a+rwX" not in DOCKERFILE
    assert "chmod 1777 /opt/Uploadrr/data" in DOCKERFILE


def test_node_26_en_la_imagen_y_en_los_workflows():
    assert "FROM node:26-alpine" in DOCKERFILE
    for nombre in ("ci.yml", "bundle.yml"):
        assert 'node-version: "26"' in (WORKFLOWS / nombre).read_text(encoding="utf-8")


def test_todos_los_jobs_tienen_limite_de_tiempo():
    """Sin él, un job colgado gasta hasta 6 h. Los que llaman a otro workflow (`uses:`) no admiten la clave."""
    for flujo in WORKFLOWS.glob("*.yml"):
        for nombre, job in yaml.safe_load(flujo.read_text(encoding="utf-8"))["jobs"].items():
            if "uses" not in job:
                assert "timeout-minutes" in job, f"{flujo.name}: el job {nombre} no tiene timeout-minutes"


def test_gitattributes_fuerza_lf():
    assert "* text=auto eol=lf" in (RAIZ / ".gitattributes").read_text(encoding="utf-8")


# ── docker-entrypoint.sh ─────────────────────────────────────────────────────

solo_sh = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("sh") is None, reason="el entrypoint es un script sh"
)


def _imagen(tmp_path: Path) -> tuple[Path, Path]:
    """/opt/Uploadrr como lo deja el Dockerfile: data/ real y los enlaces hacia /config/Uploadrr."""
    uploadrr, estado = tmp_path / "opt" / "Uploadrr", tmp_path / "config" / "Uploadrr"
    (uploadrr / "data" / "backup").mkdir(parents=True)
    (uploadrr / "data" / "backup" / "example_config.yaml").write_text("DEFAULT:\n  tmdb: ''\n", encoding="utf-8")
    (uploadrr / "data" / "services.json").write_text('{"de": "la imagen nueva"}', encoding="utf-8")
    for nombre in ("config.yaml", "config.yaml.bak", "cookies"):
        os.symlink(estado / "data" / nombre, uploadrr / "data" / nombre)
    os.symlink(estado / "tmp", uploadrr / "tmp")
    return uploadrr, estado


def _foto(raiz: Path) -> list[tuple[str, str]]:
    """Qué hay bajo `raiz`: ruta y destino del enlace, para ver si algo cambió."""
    return sorted(
        (str(p.relative_to(raiz)), os.readlink(p) if p.is_symlink() else "")
        for p in raiz.rglob("*")
    )


def _arrancar(tmp_path: Path, uploadrr: Path, estado: Path, *orden: str) -> subprocess.CompletedProcess:
    script = (RAIZ / "docker-entrypoint.sh").read_text(encoding="utf-8")
    script = script.replace('"/opt/Uploadrr"', f'"{uploadrr}"').replace('"/config/Uploadrr"', f'"{estado}"')
    assert str(uploadrr) in script and str(estado) in script
    fichero = tmp_path / "entrypoint.sh"
    fichero.write_text(script, encoding="utf-8", newline="\n")
    return subprocess.run(["sh", str(fichero), *orden], capture_output=True, text=True, timeout=30)


@solo_sh
def test_primer_arranque_crea_el_estado_y_siembra_el_config(tmp_path):
    uploadrr, estado = _imagen(tmp_path)
    res = _arrancar(tmp_path, uploadrr, estado, "echo", "hola")
    assert (res.returncode, res.stdout.strip()) == (0, "hola"), res.stderr
    for carpeta in ("data/cookies", "tmp", "uploads"):
        assert (estado / carpeta).is_dir()
    assert (estado / "data" / "config.yaml").read_text(encoding="utf-8") == "DEFAULT:\n  tmdb: ''\n"
    # Lo que está en data/ lo ve Uploadrr-EMU a través de los enlaces; lo demás sigue siendo de la imagen.
    assert (uploadrr / "data" / "config.yaml").read_text(encoding="utf-8") == "DEFAULT:\n  tmdb: ''\n"
    assert not (estado / "data" / "services.json").exists()


@solo_sh
def test_una_instalacion_anterior_conserva_su_estado_y_recibe_los_datos_nuevos(tmp_path):
    """/config de una imagen antigua: copia completa de data/. Su config.yaml manda; lo demás ya viene de la imagen."""
    uploadrr, estado = _imagen(tmp_path)
    (estado / "data" / "cookies").mkdir(parents=True)
    (estado / "data" / "cookies" / "EMU.pkl").write_bytes(b"sesion")
    (estado / "data" / "config.yaml").write_text("DEFAULT:\n  tmdb: mi-clave\n", encoding="utf-8")
    (estado / "data" / "config.yaml.bak").write_text("DEFAULT:\n  tmdb: mi-clave\n", encoding="utf-8")
    (estado / "data" / "services.json").write_text('{"de": "la imagen vieja"}', encoding="utf-8")

    assert _arrancar(tmp_path, uploadrr, estado, "true").returncode == 0

    assert (uploadrr / "data" / "config.yaml").read_text(encoding="utf-8") == "DEFAULT:\n  tmdb: mi-clave\n"
    assert (uploadrr / "data" / "config.yaml.bak").exists()
    assert (uploadrr / "data" / "cookies" / "EMU.pkl").read_bytes() == b"sesion"
    assert "imagen nueva" in (uploadrr / "data" / "services.json").read_text(encoding="utf-8")
    # La copia vieja no se borra, solo deja de usarse.
    assert "imagen vieja" in (estado / "data" / "services.json").read_text(encoding="utf-8")


@solo_sh
def test_arrancar_otra_vez_no_toca_el_config_editado(tmp_path):
    uploadrr, estado = _imagen(tmp_path)
    _arrancar(tmp_path, uploadrr, estado, "true")
    (estado / "data" / "config.yaml").write_text("editado a mano\n", encoding="utf-8")
    _arrancar(tmp_path, uploadrr, estado, "true")
    assert (estado / "data" / "config.yaml").read_text(encoding="utf-8") == "editado a mano\n"


@solo_sh
def test_no_escribe_en_uploadrr(tmp_path):
    """Con `user: 1000:10` solo data/ admite escritura, así que el entrypoint no puede crear ni borrar nada ahí."""
    uploadrr, estado = _imagen(tmp_path)
    antes = _foto(uploadrr)
    assert _arrancar(tmp_path, uploadrr, estado, "true").returncode == 0
    assert _foto(uploadrr) == antes


@solo_sh
def test_un_data_montado_a_mano_se_deja_como_esta(tmp_path):
    """Un compose antiguo que monta data/ y tmp/: el entrypoint no los toca ni siembra un config.yaml que no se usaría."""
    uploadrr, estado = tmp_path / "opt" / "Uploadrr", tmp_path / "config" / "Uploadrr"
    (uploadrr / "data").mkdir(parents=True)
    (uploadrr / "tmp").mkdir()
    (uploadrr / "data" / "config.yaml").write_text("el del usuario\n", encoding="utf-8")
    antes = _foto(uploadrr)
    res = _arrancar(tmp_path, uploadrr, estado, "true")
    assert res.returncode == 0, res.stderr
    assert _foto(uploadrr) == antes
    assert (uploadrr / "data" / "config.yaml").read_text(encoding="utf-8") == "el del usuario\n"
    assert not (estado / "data" / "config.yaml").exists()
