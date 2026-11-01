"""Modern console entry point for eMuwarez Uploadrr.

This CLI is the functional mirror of the future web interface.  The original
single-path uploader is still available and is used for prepare/upload actions.
"""
from __future__ import annotations

import sys
from typing import Optional

from .database import BaseMasNuevaError
from .integrations.base import IntegrationError
from .comandos.parser import build_parser
from .comandos.comunes import _open_conn, _status_arg  # noqa: F401  (_status_arg: lo importan los tests desde aquí)
from .comandos.biblioteca import (
    cmd_arr, cmd_instances, cmd_library, cmd_missing, cmd_requests, cmd_sync,
)
from .comandos.nomenclatura import cmd_mkv_title, cmd_nomenclature
from .comandos.subida import cmd_logs, cmd_tasks, cmd_upload
from .comandos.web import (
    cmd_web_create_admin, cmd_web_doctor, cmd_web_info, cmd_web_reset_password,
    cmd_web_serve, cmd_web_setup_status,
)
from .comandos.mantenimiento import cmd_demo, cmd_maintenance

MODERN_COMMANDS = {
    "instances", "sync", "library",
    "requests", "missing", "upload", "tasks", "logs",
    "db", "web", "nomenclature", "maintenance", "arr",
    "demo", "mkv-title",
}


def modern_main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "db":
            if args.db_command == "path":
                print(args.db)
                return 0
            with _open_conn(args):
                print(f"✓ SQLite lista: {args.db}")
                return 0
        if args.command == "instances":
            return cmd_instances(args)
        if args.command == "sync":
            return cmd_sync(args)
        if args.command == "library":
            return cmd_library(args)
        if args.command == "requests":
            return cmd_requests(args)
        if args.command == "missing":
            return cmd_missing(args)
        if args.command == "nomenclature":
            return cmd_nomenclature(args)
        if args.command == "upload":
            return cmd_upload(args)
        if args.command == "tasks":
            return cmd_tasks(args)
        if args.command == "logs":
            return cmd_logs(args)
        if args.command == "web":
            if args.web_command == "info":
                return cmd_web_info()
            if args.web_command == "serve":
                return cmd_web_serve(args)
            if args.web_command == "setup-status":
                return cmd_web_setup_status()
            if args.web_command == "doctor":
                return cmd_web_doctor()
            if args.web_command == "create-admin":
                return cmd_web_create_admin(args)
            if args.web_command == "reset-password":
                return cmd_web_reset_password(args)
        if args.command == "maintenance":
            return cmd_maintenance(args)
        if args.command == "arr":
            return cmd_arr(args)
        if args.command == "demo":
            return cmd_demo(args)
        if args.command == "mkv-title":
            return cmd_mkv_title(args)
        parser.error("Comando no soportado")
        return 2
    except (IntegrationError, BaseMasNuevaError) as exc:
        print(f"✗ {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nInterrumpido.")
        return 130


def main(argv: Optional[list[str]] = None) -> int:
    """Punto de entrada. Hasta el 2026-08-01, lo que no fuera un comando
    conocido caía en el CLI interactivo antiguo; ese CLI se borró (asumía un
    ./Uploadrr y un ./.venv junto al script que en el contenedor no existen, y
    su asistente escribía una segunda configuración que la aplicación no usa).
    Ahora un comando desconocido es un error, que es lo que siempre fue."""
    return modern_main(list(sys.argv[1:] if argv is None else argv))


__all__ = ["main", "modern_main", "build_parser"]
