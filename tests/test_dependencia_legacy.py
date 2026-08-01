"""legacy.py ya no existe: esta es la prueba de que no vuelve.

El monolito del que salió la aplicación (hallazgo 1.1 de la auditoría) se
desmontó el 2026-08-01 en cinco pasos y se borró: lo que era de todos vive en
constants.py y en services/ (media_probe, uploadrr_yaml, emu_title,
cli_config), y lo que quedaba era el motor del CLI interactivo antiguo, que en
el contenedor ni siquiera podía funcionar.

Este fichero conserva el trinquete por si alguien lo recupera de git y lo
vuelve a enchufar: mide lo mismo que medía antes y ahora exige cero.
"""
from __future__ import annotations

import ast
import io
import pathlib
import re
import tokenize

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "emuwarez_uploadrr"


def _codigo_sin_comentarios(src: str) -> str:
    """El fichero sin comentarios ni cadenas, para no contar menciones en prosa."""
    try:
        piezas = [
            t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.STRING)
        ]
    except tokenize.TokenError:
        return src
    return " ".join(piezas)


def _medir(ruta: pathlib.Path) -> tuple[int, int]:
    src = ruta.read_text()
    prefijo = len(re.findall(r"\blegacy\s*\.\s*[A-Za-z_]", _codigo_sin_comentarios(src)))
    directos = 0
    for nodo in ast.walk(ast.parse(src)):
        if isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.module.endswith("legacy"):
            directos += len(nodo.names)
    return prefijo, directos


def test_legacy_no_existe():
    assert not (RAIZ / "legacy.py").exists(), (
        "ha vuelto emuwarez_uploadrr/legacy.py. Si es a propósito, este test "
        "sobra; si no, algo lo ha recuperado de git."
    )


def test_nadie_llama_a_legacy():
    """Ni con prefijo ni importando nombres, en ningún fichero del paquete."""
    culpables = []
    for f in sorted(RAIZ.rglob("*.py")):
        prefijo, directos = _medir(f)
        if prefijo or directos:
            culpables.append(f"{f.relative_to(RAIZ)}: {prefijo} con prefijo, {directos} directos")
    assert not culpables, (
        "\nCódigo llamando a legacy.py, que ya no existe:\n  " + "\n  ".join(culpables)
        + "\n\nLo que necesites está en constants.py o en services/"
          " (media_probe, uploadrr_yaml, emu_title, cli_config)."
    )


def test_constants_es_dueno_y_no_alias():
    """constants.py define las constantes; era un alias de legacy hasta que se
    invirtió la dependencia. Si vuelve a importar de algo llamado legacy, la
    inversión se ha deshecho."""
    prefijo, directos = _medir(RAIZ / "constants.py")
    assert (prefijo, directos) == (0, 0)
    fuente = (RAIZ / "constants.py").read_text()
    assert "LANG_MAP" in fuente and "SOURCE_PATTERNS" in fuente, (
        "constants.py ha dejado de definir las tablas que era su razón de ser"
    )
