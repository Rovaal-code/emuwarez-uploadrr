"""desplegar.sh con docker, gh y curl simulados y remotos git locales.

Lo que se prueba es el orden, el mismo de publicar.yml: la imagen como :<sha>,
la etiqueta de git, :X.Y.Z y :latest, y el manifiesto lo último. Así, si algo
falla a medias, relanzar completa la versión.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import types

import pytest

from emuwarez_uploadrr import __version__

RAIZ = pathlib.Path(__file__).resolve().parents[1]

# Cada push apunta la etiqueta de imagen y las etiquetas de git que hay ya en GitHub.
_DOCKER = r"""#!/bin/sh
case "$1" in
  build) for a; do case "$a" in APP_COMMIT=*) echo "${a#*=}" > "$FALSO/sello" ;; esac; done
         cat > /dev/null; echo build >> "$FALSO/docker.log" ;;
  image) case "$*" in *RepoDigests*) echo "x@sha256:abc" ;; *) cat "$FALSO/sello" ;; esac ;;
  push)  [ "${2#*:}" != "$FALLA" ] || exit 1
         echo "push ${2#*:} $(git --git-dir="$FALSO/origen.git" tag)" >> "$FALSO/docker.log" ;;
esac
"""
_GH = r"""#!/bin/sh
case "$1 $2" in
  "auth token") echo x ;;
  "api repos/Kisnov/uploadrr-version/contents/latest.json")
    git --git-dir="$FALSO/manifiesto.git" show HEAD:latest.json | base64 ;;
  "repo clone") git clone -q --depth 1 "file://$FALSO/manifiesto.git" "$4" ;;
  *) echo "gh simulado no sabe: $*" >&2; exit 1 ;;
esac
"""
_CURL = "#!/bin/sh\ncat > /dev/null\n"


@pytest.fixture
def entorno(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for nombre, codigo in (("docker", _DOCKER), ("gh", _GH), ("curl", _CURL)):
        (bin_ / nombre).write_text(codigo)
        (bin_ / nombre).chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}", "FALSO": str(tmp_path),
           "TMPDIR": str(tmp_path), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t",
           # El fork, a un repo local.
           "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": f"url.file://{tmp_path}/fork.git.insteadOf",
           "GIT_CONFIG_VALUE_0": "https://github.com/Kisnov/Uploadrr-EMU.git"}

    def git(*args, cwd=tmp_path):
        return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                              capture_output=True, text=True).stdout.strip()

    repo = tmp_path / "repo"
    for fichero in ("scripts/desplegar.sh", "scripts/publicar_version.py",
                    "scripts/subir_version.py", "emuwarez_uploadrr/__init__.py"):
        (repo / fichero).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(RAIZ / fichero, repo / fichero)
    git("init", "-q", "-b", "master", cwd=repo)
    git("add", ".", cwd=repo)
    git("commit", "-qm", "inicio", cwd=repo)
    git("init", "-q", "--bare", "origen.git")
    git("init", "-q", "--bare", "fork.git")
    git("remote", "add", "origin", str(tmp_path / "origen.git"), cwd=repo)
    git("push", "-q", "origin", "master", cwd=repo)
    git("push", "-q", str(tmp_path / "fork.git"), "master:main", cwd=repo)

    manifiesto = tmp_path / "m"
    git("init", "-q", "-b", "main", str(manifiesto))
    (manifiesto / "latest.json").write_text(json.dumps({"version": "0.0.1", "commit": "0" * 40}))
    git("add", ".", cwd=manifiesto)
    git("commit", "-qm", "0.0.1", cwd=manifiesto)
    git("clone", "-q", "--bare", str(manifiesto), "manifiesto.git")

    return types.SimpleNamespace(dir=tmp_path, repo=repo, env=env, git=git,
                                 commit=git("rev-parse", "HEAD", cwd=repo))


def _desplegar(entorno, *args, falla=""):
    return subprocess.run(["bash", "scripts/desplegar.sh", *args], cwd=entorno.repo,
                          env={**entorno.env, "FALLA": falla}, capture_output=True, text=True)


def _docker(entorno):
    log = entorno.dir / "docker.log"
    return [linea.split() for linea in log.read_text().splitlines()] if log.exists() else []


def _manifiesto(entorno):
    return json.loads(entorno.git("--git-dir=manifiesto.git", "show", "HEAD:latest.json"))


def test_publica_en_el_orden_del_workflow(entorno):
    r = _desplegar(entorno, "--notas", "Mejoras")
    assert r.returncode == 0, r.stderr

    v = __version__
    assert _docker(entorno) == [["build"], ["push", entorno.commit],
                                ["push", v, f"v{v}"], ["push", "latest", f"v{v}"],
                                ["push", "edge", f"v{v}"]]
    assert entorno.git("--git-dir=origen.git", "rev-parse", f"v{v}^{{commit}}") == entorno.commit
    assert _manifiesto(entorno) | {"fecha": None} == {
        "commit": entorno.commit, "version": v, "digest": "sha256:abc", "notas": "Mejoras", "fecha": None}


def test_relanzar_completa_una_version_a_medias(entorno):
    """Si :latest no se sube, el manifiesto sigue en la anterior: relanzar la completa."""
    assert _desplegar(entorno, "--notas", "Mejoras", falla="latest").returncode != 0
    assert _manifiesto(entorno)["version"] == "0.0.1"

    r = _desplegar(entorno, "--notas", "Mejoras")
    assert r.returncode == 0, r.stderr
    assert "La etiqueta" in r.stdout and "ya está en GitHub" in r.stdout
    assert _manifiesto(entorno)["commit"] == entorno.commit


def test_solo_prueba_sube_solo_edge(entorno):
    r = _desplegar(entorno, "--solo-prueba")
    assert r.returncode == 0, r.stderr

    assert _docker(entorno) == [["build"], ["push", "edge"]]
    assert entorno.git("--git-dir=origen.git", "tag") == ""
    assert _manifiesto(entorno)["version"] == "0.0.1"


def test_una_etiqueta_en_otro_commit_para_antes_de_construir(entorno):
    entorno.git("commit", "-q", "--allow-empty", "-m", "otro", cwd=entorno.repo)
    entorno.git("push", "-q", "origin", f"HEAD:refs/tags/v{__version__}", cwd=entorno.repo)
    entorno.git("reset", "-q", "--hard", "HEAD~1", cwd=entorno.repo)

    r = _desplegar(entorno, "--notas", "Mejoras")
    assert r.returncode == 1
    assert "ya está en GitHub" in r.stderr
    assert _docker(entorno) == []
