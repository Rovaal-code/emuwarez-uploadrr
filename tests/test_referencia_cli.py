"""README_CLI_READY.md sale de build_parser(). Si falla: python3 scripts/referencia_cli.py"""
import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def test_la_referencia_de_la_cli_esta_al_dia():
    spec = importlib.util.spec_from_file_location("referencia_cli", RAIZ / "scripts" / "referencia_cli.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    actual = (RAIZ / "README_CLI_READY.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == modulo.generar()
