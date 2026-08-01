"""Trinquete sobre la dependencia de legacy.py.

legacy.py es el monolito del que se está saliendo (hallazgo 1.1 de la
auditoría). Este test NO exige que la dependencia sea cero: exige que no
CREZCA. Cada paso de la migración baja un número de la tabla de abajo; si algo
lo sube, este test falla y hay que justificarlo a mano.

Se cuenta de dos formas porque hay dos maneras de llegar a legacy:
  - `legacy.algo`      -> uso con prefijo, tras `from .. import legacy`
  - `from ..legacy import algo` -> nombres traídos directamente

Los comentarios y las cadenas NO cuentan: se descartan con el analizador de
Python, porque si no, una frase como "esto venía de legacy.py" sumaba uno y el
recuento mentía (pasó de verdad al medir la auditoría).
"""
from __future__ import annotations

import ast
import io
import pathlib
import re
import tokenize

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "emuwarez_uploadrr"

# fichero -> (usos con prefijo, nombres importados directamente)
# Bajar estos números al migrar. Nunca subirlos sin una razón escrita.
PRESUPUESTO: dict[str, tuple[int, int]] = {
    "cli.py": (13, 0),
    # legacy.py ya no define las constantes: las importa de constants.py, que
    # pasó a ser su dueño. Esta entrada es la de constants.py mirando al revés
    # y por eso no está aquí: la vigila test_constants_no_depende_de_legacy.
    #
    # Solo queda cli.py, y sus 13 usos son casi todos `legacy.main(argv)`: el
    # CLI antiguo delegando en su propio motor, que es lo que legacy.py es hoy.
    # Bajar de aquí ya no es refactorizar, es decidir si ese CLI sigue
    # existiendo.
}

# La aplicación no puede tocar legacy.py: habla por la terminal (die() lanza
# SystemExit, varias funciones preguntan por teclado) y eso dentro de una
# petición HTTP tumba el hilo o se queda colgado. Ya pasó dos veces.
CAPAS_PROHIBIDAS = ("web", "services", "integrations")


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


def _todos_los_modulos() -> list[pathlib.Path]:
    return [f for f in sorted(RAIZ.rglob("*.py")) if f.name != "legacy.py"]


def test_la_dependencia_de_legacy_no_crece():
    excesos = []
    for f in _todos_los_modulos():
        rel = str(f.relative_to(RAIZ))
        prefijo, directos = _medir(f)
        if prefijo == 0 and directos == 0:
            continue
        tope_p, tope_d = PRESUPUESTO.get(rel, (0, 0))
        if prefijo > tope_p or directos > tope_d:
            excesos.append(f"{rel}: {prefijo} con prefijo (tope {tope_p}), "
                           f"{directos} directos (tope {tope_d})")
    assert not excesos, (
        "\nHa crecido la dependencia de legacy.py:\n  " + "\n  ".join(excesos)
        + "\n\nSi es a propósito, sube el tope en PRESUPUESTO y explica por qué."
    )


def test_el_presupuesto_no_se_queda_obsoleto():
    """Si un fichero ya no toca legacy, su entrada sobra: que se borre, para
    que la tabla diga la verdad y el siguiente sepa qué queda de verdad."""
    sobran = []
    for rel, (tope_p, tope_d) in PRESUPUESTO.items():
        prefijo, directos = _medir(RAIZ / rel)
        if prefijo < tope_p or directos < tope_d:
            sobran.append(f"{rel}: el tope dice ({tope_p}, {tope_d}) pero ya solo usa ({prefijo}, {directos})")
    assert not sobran, (
        "\nHay topes por encima de lo real (baja el número o borra la entrada):\n  "
        + "\n  ".join(sobran)
    )


def test_constants_no_depende_de_legacy():
    """constants.py es el dueño de las constantes, no un alias. Si vuelve a
    importar de legacy, la inversión del 2026-08-01 se ha deshecho."""
    prefijo, directos = _medir(RAIZ / "constants.py")
    assert (prefijo, directos) == (0, 0), "constants.py ha vuelto a depender de legacy.py"


def test_la_aplicacion_no_toca_legacy():
    """web/, services/ e integrations/ no pueden llegar a legacy.py, ni con
    prefijo ni importando nombres. Esta es la línea que no se cruza: lo de
    PRESUPUESTO es deuda que se va pagando, esto es una regla."""
    culpables = []
    for f in _todos_los_modulos():
        rel = str(f.relative_to(RAIZ))
        if not rel.startswith(CAPAS_PROHIBIDAS):
            continue
        prefijo, directos = _medir(f)
        if prefijo or directos:
            culpables.append(f"{rel}: {prefijo} con prefijo, {directos} directos")
    assert not culpables, (
        "\nCódigo de la aplicación llamando a legacy.py:\n  " + "\n  ".join(culpables)
        + "\n\nlegacy.py es el motor del CLI: habla por la terminal. Lo que necesites"
          "\nestá en services/ (media_probe, uploadrr_yaml, emu_title, cli_config) o"
          "\nen constants.py."
    )
