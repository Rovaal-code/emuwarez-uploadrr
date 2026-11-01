#!/usr/bin/env python3
"""Escribe README_CLI_READY.md a partir de `build_parser()`: la referencia de la CLI no se edita a mano.

    python3 scripts/referencia_cli.py
"""
from __future__ import annotations

import argparse
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from emuwarez_uploadrr.cli import build_parser  # noqa: E402


def _subcomandos(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for accion in parser._actions:
        if isinstance(accion, argparse._SubParsersAction):
            return dict(accion.choices)
    return {}


def _argumentos(parser: argparse.ArgumentParser) -> str:
    partes = []
    for a in parser._actions:
        if isinstance(a, (argparse._HelpAction, argparse._SubParsersAction)):
            continue
        if a.option_strings:
            texto = a.option_strings[0] + ("" if a.nargs == 0 else f" {a.metavar or a.dest.upper()}")
            partes.append(texto if a.required else f"[{texto}]")
        else:
            nombre = a.metavar or ("{" + ",".join(map(str, a.choices)) + "}" if a.choices else a.dest.upper())
            partes.append(f"[{nombre}]" if a.nargs in ("?", "*") else nombre)
    return " ".join(partes)


def _descripcion(ayuda: str, parser: argparse.ArgumentParser) -> str:
    """La ayuda del comando y la de cada argumento (ahí está, p. ej., el token de `--confirm`)."""
    args = []
    for a in parser._actions:
        if isinstance(a, (argparse._HelpAction, argparse._SubParsersAction)) or not a.help:
            continue
        args.append(f"`{a.option_strings[0] if a.option_strings else a.dest}`: {a.help}")
    return ayuda + (". " + "; ".join(args) if args else "")


def _filas(parser: argparse.ArgumentParser, prefijo: str, ayudas: dict[str, str]) -> list[tuple[str, str]]:
    filas = []
    for nombre, hijo in _subcomandos(parser).items():
        ruta = f"{prefijo} {nombre}".strip()
        subs = _subcomandos(hijo)
        if subs:
            filas += _filas(hijo, ruta, ayudas)
        else:
            args = _argumentos(hijo)
            filas.append((f"{ruta} {args}".strip(), _descripcion(ayudas.get(ruta, ""), hijo)))
    return filas


def _ayudas(parser: argparse.ArgumentParser, prefijo: str = "") -> dict[str, str]:
    ayudas = {}
    for accion in parser._actions:
        if isinstance(accion, argparse._SubParsersAction):
            for elegida in accion._choices_actions:
                ruta = f"{prefijo} {elegida.dest}".strip()
                ayudas[ruta] = elegida.help or ""
            for nombre, hijo in accion.choices.items():
                ayudas.update(_ayudas(hijo, f"{prefijo} {nombre}".strip()))
    return ayudas


def generar() -> str:
    parser = build_parser()
    ayudas = _ayudas(parser)
    salida = [
        "# Referencia de la CLI",
        "",
        "Generada con `python3 scripts/referencia_cli.py` a partir de `build_parser()`: no se edita a mano.",
        "",
        "```bash",
        "docker exec emuwarez-uploadrr python3 emuwarez_uploader.py <comando>",
        "```",
        "",
        "Sin Docker, `python3 emuwarez_uploader.py <comando>`. La opción global `--db RUTA` elige otra base SQLite.",
        "Los argumentos entre corchetes son opcionales. El historial de la CLI anterior está en "
        "[`docs/historial_cli.md`](docs/historial_cli.md).",
        "",
    ]
    for nombre, hijo in _subcomandos(parser).items():
        salida += [f"## `{nombre}` — {ayudas.get(nombre, '')}", "", "| Comando | Qué hace |", "|---|---|"]
        subs = _subcomandos(hijo)
        filas = _filas(hijo, nombre, ayudas) if subs else [
            (f"{nombre} {_argumentos(hijo)}".strip(), _descripcion(ayudas.get(nombre, ""), hijo))]
        for comando, ayuda in filas:
            salida.append(f"| `{comando}` | {ayuda.replace('|', '/')} |")
        salida.append("")
    return "\n".join(salida)


if __name__ == "__main__":
    (RAIZ / "README_CLI_READY.md").write_text(generar(), encoding="utf-8", newline="\n")
