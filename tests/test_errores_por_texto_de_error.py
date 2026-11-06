"""El texto de una excepción capturada pasa por `integrations.base.texto_de_error`.

#237 tapó las claves en cada sitio que metía `str(exc)` en una respuesta, una columna o una notificación: eMuwarez y
TMDb llevan la clave en la URL y el texto de una excepción de red o de HTTP puede repetirla. Esto impide que un sitio
nuevo lo olvide: en web/ y services/, el nombre de un `except ... as X` no puede acabar en `str(X)`, `repr(X)`,
`f"{X}"`, `"%s" % X`, `"...".format(X)` ni concatenado. Se usa `texto_de_error(X)` (o `tapar_claves`).

Los argumentos de una llamada a `logger.*`/`logging.*` no cuentan: la fábrica de `LogRecord` de
`web/logging_setup.py` tapa mensaje, traceback y stack de cualquier registro. Lo demás que sea seguro va en
`PERMITIDOS`, por fichero y función, con su motivo.
"""
from __future__ import annotations

import ast
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "emuwarez_uploadrr"
CARPETAS = ("web", "services")

# (fichero relativo a emuwarez_uploadrr/, función con su clase si la tiene): motivo.
PERMITIDOS: dict[tuple[str, str], str] = {
    ("web/api/setup.py", "setup_admin"): "aquí SetupError solo lleva un texto fijo de setup_service",
    ("web/api/setup.py", "setup_complete"): "aquí SetupError solo lleva un texto fijo de setup_service",
    ("web/api/maintenance.py", "upload_backup"): "el ValueError lo lanza CopiaSubida con un texto nuestro",
    ("services/backup_service.py", "_motivo_de_rechazo"): "FilterError de tarfile sobre un miembro de la copia local",
}

_REGISTRO = {"logger", "log", "logging", "_log", "_logger"}


def _es_registro(llamada: ast.Call) -> bool:
    f = llamada.func
    return isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in _REGISTRO


def _es(nodo: ast.AST, nombre: str) -> bool:
    return isinstance(nodo, ast.Name) and nodo.id == nombre


class _Buscador(ast.NodeVisitor):
    def __init__(self) -> None:
        self.funciones: list[str] = []
        self.capturadas: list[str] = []
        self.en_registro = 0
        self.hallados: list[tuple[str, int]] = []

    def _anota(self, nodo: ast.AST) -> None:
        if not self.en_registro:
            self.hallados.append((".".join(self.funciones) or "<módulo>", nodo.lineno))

    def _ambito(self, nodo):
        self.funciones.append(nodo.name)
        self.generic_visit(nodo)
        self.funciones.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _ambito

    def visit_ExceptHandler(self, nodo: ast.ExceptHandler) -> None:
        if nodo.name:
            self.capturadas.append(nodo.name)
        self.generic_visit(nodo)
        if nodo.name:
            self.capturadas.pop()

    def visit_Call(self, nodo: ast.Call) -> None:
        registro = _es_registro(nodo)
        self.en_registro += registro
        nombres = self.capturadas
        if isinstance(nodo.func, ast.Name) and nodo.func.id in ("str", "repr") and nodo.args \
                and any(_es(nodo.args[0], n) for n in nombres):
            self._anota(nodo)
        if isinstance(nodo.func, ast.Attribute) and nodo.func.attr == "format" \
                and any(_es(a, n) for a in [*nodo.args, *(k.value for k in nodo.keywords)] for n in nombres):
            self._anota(nodo)
        self.generic_visit(nodo)
        self.en_registro -= registro

    def visit_FormattedValue(self, nodo: ast.FormattedValue) -> None:
        if any(_es(nodo.value, n) for n in self.capturadas):
            self._anota(nodo)
        self.generic_visit(nodo)

    def visit_BinOp(self, nodo: ast.BinOp) -> None:
        for n in self.capturadas:
            if isinstance(nodo.op, ast.Mod) and (
                    _es(nodo.right, n) or isinstance(nodo.right, ast.Tuple) and any(_es(e, n) for e in nodo.right.elts)):
                self._anota(nodo)
            elif isinstance(nodo.op, ast.Add) and (_es(nodo.left, n) or _es(nodo.right, n)):
                self._anota(nodo)
        self.generic_visit(nodo)


def _sitios() -> dict[tuple[str, str], list[int]]:
    sitios: dict[tuple[str, str], list[int]] = {}
    for carpeta in CARPETAS:
        for f in sorted((RAIZ / carpeta).rglob("*.py")):
            buscador = _Buscador()
            buscador.visit(ast.parse(f.read_text(encoding="utf-8")))
            for funcion, linea in buscador.hallados:
                sitios.setdefault((str(f.relative_to(RAIZ)), funcion), []).append(linea)
    return sitios


def test_el_texto_de_una_excepcion_pasa_por_texto_de_error():
    culpables = {k: v for k, v in _sitios().items() if k not in PERMITIDOS}
    assert not culpables, (
        "\nTexto de una excepción sin pasar por texto_de_error:\n  "
        + "\n  ".join(f"{f}:{','.join(map(str, lineas))} ({fn})" for (f, fn), lineas in sorted(culpables.items()))
        + "\n\nUsa integrations.base.texto_de_error(exc): una excepción de integración puede llevar la URL con la"
          "\nclave. Si el texto es seguro (una excepción propia con un texto nuestro), añádelo a PERMITIDOS con su motivo."
    )


def test_la_lista_de_permitidos_no_guarda_sitios_que_ya_no_existen():
    sobran = sorted(set(PERMITIDOS) - set(_sitios()))
    assert not sobran, f"Sitios en PERMITIDOS que ya no usan el texto de la excepción: {sobran}"


def test_el_detector_ve_cada_forma():
    codigo = (
        "def f():\n"
        "    try:\n        pass\n"
        "    except Exception as exc:\n"
        "        a = str(exc)\n        b = f'{exc!r}'\n        c = repr(exc)\n        d = '%s' % exc\n"
        "        e = '%s %s' % (1, exc)\n        g = '{}'.format(exc)\n        h = 'x: ' + exc\n"
        "        logger.warning(f'no cuenta {exc}')\n        i = texto_de_error(exc)\n"
    )
    buscador = _Buscador()
    buscador.visit(ast.parse(codigo))
    assert [linea for _, linea in buscador.hallados] == [5, 6, 7, 8, 9, 10, 11]
