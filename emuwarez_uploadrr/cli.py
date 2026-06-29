"""Modern console entry point for eMuwarez Uploadrr.

This CLI is the functional mirror of the future web interface.  The original
single-path uploader is still available and is used for prepare/upload actions.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Optional

from . import legacy
from .database import connect, init_db, db_path, get_state
from .integrations.base import IntegrationError
from .models import LocalStatus, NomenclatureStatus, RequestStatus
from .services import instances as instance_service
from .services import library as library_service
from .services import requests as request_service
from .services import tasks as task_service

MODERN_COMMANDS = {
    "configure", "doctor", "test-apis", "instances", "sync", "library",
    "requests", "missing", "prepare", "upload", "tasks", "logs", "legacy",
    "web-contract", "db", "web", "nomenclature",
}


def _print_table(headers: list[str], rows: list[list[Any]]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell) if cell is not None else ""))
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["─" * w for w in widths]))
    for row in rows:
        print(fmt.format(*["" if c is None else str(c) for c in row]))


def _status_arg(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lookup = {
        "available": LocalStatus.AVAILABLE.value,
        "disponible": LocalStatus.AVAILABLE.value,
        "missing": LocalStatus.MISSING.value,
        "faltante": LocalStatus.MISSING.value,
        "uploading": LocalStatus.UPLOADING.value,
        "subiendo": LocalStatus.UPLOADING.value,
        "uploaded": LocalStatus.UPLOADED.value,
        "subido": LocalStatus.UPLOADED.value,
        "error": LocalStatus.ERROR.value,
    }
    return lookup.get(value.lower(), value)


def _request_arg(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lookup = {
        "none": RequestStatus.NONE.value,
        "sin": RequestStatus.NONE.value,
        "compatible": RequestStatus.COMPATIBLE.value,
        "partial": RequestStatus.PARTIAL.value,
        "parcial": RequestStatus.PARTIAL.value,
        "not-compatible": RequestStatus.NOT_COMPATIBLE.value,
        "no-compatible": RequestStatus.NOT_COMPATIBLE.value,
        "filled": RequestStatus.FILLED.value,
        "llena": RequestStatus.FILLED.value,
    }
    return lookup.get(value.lower(), value)


def _nomenclature_arg(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lookup = {
        "correct": NomenclatureStatus.CORRECT.value,
        "correcta": NomenclatureStatus.CORRECT.value,
        "missing": NomenclatureStatus.NOT_ADAPTED.value,
        "not-adapted": NomenclatureStatus.NOT_ADAPTED.value,
        "no-adaptada": NomenclatureStatus.NOT_ADAPTED.value,
        "na": NomenclatureStatus.NA.value,
        "n/a": NomenclatureStatus.NA.value,
    }
    return lookup.get(value.lower(), value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emuwarez-uploadrr",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="CLI modular de eMuwarez Uploadrr. Espejo funcional de la futura interfaz web.",
    )
    parser.add_argument("--db", default=str(db_path()), help="Ruta de SQLite. Por defecto: ~/.config/emuwarez-renamer/emuwarez_uploadrr.db")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("configure", help="Ejecutar configuración heredada del uploader")
    sub.add_parser("doctor", help="Comprobar entorno/configuración heredada")
    sub.add_parser("test-apis", help="Probar APIs configuradas")

    p_db = sub.add_parser("db", help="Operaciones de base de datos local")
    db_sub = p_db.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("init", help="Crear/actualizar tablas SQLite")
    db_sub.add_parser("path", help="Mostrar ruta de SQLite")

    p_inst = sub.add_parser("instances", help="Gestionar instancias Radarr/Sonarr")
    inst_sub = p_inst.add_subparsers(dest="instances_command", required=True)
    inst_sub.add_parser("list", help="Listar instancias")
    p_add = inst_sub.add_parser("add", help="Añadir o actualizar instancia")
    p_add.add_argument("type", choices=["radarr", "sonarr"])
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--url", required=True)
    p_add.add_argument("--api-key", required=True)
    p_test = inst_sub.add_parser("test", help="Probar conexión")
    p_test.add_argument("id", nargs="?", type=int)
    p_remove = inst_sub.add_parser("remove", help="Eliminar instancia")
    p_remove.add_argument("id", type=int)

    p_sync = sub.add_parser("sync", help="Sincronizar biblioteca desde Radarr/Sonarr")
    p_sync.add_argument("--episodes", action="store_true", help="En Sonarr, importar también episodios")

    p_lib = sub.add_parser("library", help="Biblioteca local sincronizada")
    lib_sub = p_lib.add_subparsers(dest="library_command", required=True)
    p_lib_list = lib_sub.add_parser("list", help="Listar biblioteca")
    p_lib_list.add_argument("--status")
    p_lib_list.add_argument("--request")
    p_lib_list.add_argument("--nomenclature")
    p_lib_list.add_argument("--type")
    p_lib_list.add_argument("--search")
    p_lib_list.add_argument("--limit", type=int, default=50)
    p_lib_show = lib_sub.add_parser("show", help="Ver detalle de item")
    p_lib_show.add_argument("id", type=int)

    p_req = sub.add_parser("requests", help="Peticiones EMU")
    req_sub = p_req.add_subparsers(dest="requests_command", required=True)
    p_req_sync = req_sub.add_parser("sync", help="Sincronizar peticiones EMU. Mínimo 1 vez/hora salvo --force")
    p_req_sync.add_argument("--endpoint-url", help="Endpoint capturado de eMuwarez para listar peticiones")
    p_req_sync.add_argument("--force", action="store_true", help="Forzar sincronización ignorando el límite de una hora")
    p_req_list = req_sub.add_parser("list", help="Listar peticiones sincronizadas")
    p_req_list.add_argument("--search")
    p_req_list.add_argument("--limit", type=int, default=50)
    p_req_show = req_sub.add_parser("show", help="Detalle de petición y cruce con biblioteca")
    p_req_show.add_argument("id", type=int)
    p_req_endpoint = req_sub.add_parser("set-endpoint", help="Guardar endpoint de lectura de peticiones EMU")
    p_req_endpoint.add_argument("url")
    req_sub.add_parser("match", help="Recalcular cruces petición/biblioteca")
    p_req_reviewed = req_sub.add_parser("mark-reviewed", help="Marcar petición como revisada")
    p_req_reviewed.add_argument("id", type=int)
    p_req_create = req_sub.add_parser("create", help="Preparado para futuro: crear petición EMU")
    p_req_create.add_argument("library_id", type=int)
    p_req_create.add_argument("--dry-run", action="store_true")

    p_missing = sub.add_parser("missing", help="Contenido faltante")
    missing_sub = p_missing.add_subparsers(dest="missing_command", required=True)
    p_missing_list = missing_sub.add_parser("list", help="Listar faltantes")
    p_missing_list.add_argument("--limit", type=int, default=50)
    p_missing_req = missing_sub.add_parser("create-request", help="Preparado para futuro: crear petición EMU desde faltante")
    p_missing_req.add_argument("library_id", type=int)
    p_missing_req.add_argument("--dry-run", action="store_true")

    p_nomenclature = sub.add_parser("nomenclature", help="Previsualización de nomenclatura eMuwarez (no modifica archivos)")
    nom_sub = p_nomenclature.add_subparsers(dest="nomenclature_command", required=True)
    p_nom_preview = nom_sub.add_parser("preview", help="Generar propuesta de nomenclatura para un item")
    p_nom_preview.add_argument("id", type=int, help="ID del library_item")
    p_nom_preview.add_argument("--force", action="store_true", help="Forzar regeneración aunque ya exista propuesta")
    p_nom_show = nom_sub.add_parser("show", help="Mostrar última propuesta de nomenclatura")
    p_nom_show.add_argument("id", type=int, help="ID del library_item")
    p_nom_apply = nom_sub.add_parser("apply", help="Adaptar nomenclatura creando hardlink preparado")
    p_nom_apply.add_argument("id", type=int, help="ID del library_item")
    p_nom_apply.add_argument("--dry-run", action="store_true", help="Solo previsualización (no escribe nada)")
    p_nom_apply.add_argument("--apply", action="store_true", dest="nom_apply", help="Aplicar cambios reales")
    p_nom_apply.add_argument("--confirm", metavar="TOKEN", dest="confirm_token", help="Token de confirmación: APLICAR_NOMENCLATURA")

    p_prepare = sub.add_parser("prepare", help="Adaptar nomenclatura / generar propuesta")
    p_prepare.add_argument("target", help="ID de biblioteca o ruta")
    p_prepare.add_argument("--apply", action="store_true", help="Aplicar preparación. Sin esto se usa dry-run")
    p_prepare.add_argument("legacy_args", nargs=argparse.REMAINDER, help="Argumentos extra para el uploader heredado")

    p_upload = sub.add_parser("upload", help="Subir contenido / preflight Uploadrr")
    up_sub = p_upload.add_subparsers(dest="upload_command")
    p_up_preflight = up_sub.add_parser("preflight", help="Validar precondiciones de subida (no ejecuta Uploadrr)")
    p_up_preflight.add_argument("id", type=int, help="ID del library_item")
    p_up_preflight.add_argument("--request-id", type=int, default=None, help="ID opcional de request_item vinculada")
    p_up_job = up_sub.add_parser("job", help="Ver detalle de un upload job/preflight")
    p_up_job.add_argument("id", type=int, help="ID del upload job")
    up_sub.add_parser("jobs", help="Listar upload jobs/preflights")

    p_tasks = sub.add_parser("tasks", help="Tareas ejecutadas")
    tasks_sub = p_tasks.add_subparsers(dest="tasks_command", required=True)
    p_tasks_list = tasks_sub.add_parser("list", help="Listar últimas tareas")
    p_tasks_list.add_argument("--limit", type=int, default=20)

    p_logs = sub.add_parser("logs", help="Logs del uploader heredado")
    p_logs.add_argument("--tail", type=int, default=80)

    p_legacy = sub.add_parser("legacy", help="Pasar argumentos directamente al uploader heredado")
    p_legacy.add_argument("legacy_args", nargs=argparse.REMAINDER)

    sub.add_parser("web-contract", help="Mostrar contrato funcional para la futura interfaz")

    p_web = sub.add_parser("web", help="Servidor web backend FastAPI")
    web_sub = p_web.add_subparsers(dest="web_command", required=True)
    web_sub.add_parser("info", help="Mostrar información del servidor web")
    p_serve = web_sub.add_parser("serve", help="Arrancar servidor web")
    p_serve.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    p_serve.add_argument("--port", type=int, default=9494, help="Puerto (default: 9494)")
    p_serve.add_argument("--reload", action="store_true", help="Recarga automática (solo desarrollo)")
    web_sub.add_parser("setup-status", help="Mostrar estado del asistente de configuración")
    p_create_admin = web_sub.add_parser("create-admin", help="Crear usuario administrador web")
    p_create_admin.add_argument("--username", required=True, help="Nombre de usuario admin")

    return parser


def _open_conn(args) -> Any:
    conn = connect(Path(args.db))
    init_db(conn)
    return conn


def _target_to_path(conn, target: str) -> str:
    if target.isdigit():
        item = library_service.get_library_item(conn, int(target))
        if not item:
            raise SystemExit(f"No existe LibraryItem con ID {target}")
        if not item.get("path"):
            raise SystemExit(f"El item {target} no tiene ruta local utilizable")
        return str(item["path"])
    return target


def cmd_instances(args) -> int:
    with _open_conn(args) as conn:
        if args.instances_command == "add":
            item_id = instance_service.add_instance(conn, args.type, args.name, args.url, args.api_key)
            print(f"✓ Instancia guardada con ID {item_id}")
            return 0
        if args.instances_command == "list":
            rows = [
                [i.id, i.type, i.name, i.url, "sí" if i.enabled else "no"]
                for i in instance_service.list_instances(conn)
            ]
            _print_table(["ID", "Tipo", "Nombre", "URL", "Activa"], rows)
            return 0
        if args.instances_command == "test":
            items = [instance_service.get_instance(conn, args.id)] if args.id else instance_service.list_instances(conn)
            items = [i for i in items if i]
            if not items:
                print("No hay instancias configuradas.")
                return 1
            ok = True
            for item in items:
                try:
                    status = instance_service.test_instance(item)
                    version = status.get("version") or status.get("appVersion") or "OK"
                    print(f"✓ {item.type} {item.name}: conectado ({version})")
                except Exception as exc:
                    ok = False
                    print(f"✗ {item.type} {item.name}: {exc}")
            return 0 if ok else 1
        if args.instances_command == "remove":
            print("✓ Eliminada" if instance_service.remove_instance(conn, args.id) else "No encontrada")
            return 0
    return 1


def cmd_sync(args) -> int:
    with _open_conn(args) as conn:
        result = library_service.sync_all(conn, include_episodes=args.episodes)
        print(f"✓ Biblioteca sincronizada: {result['imported']} elementos, {result['missing']} faltantes, {result['instances']} instancias")
    return 0


def cmd_library(args) -> int:
    with _open_conn(args) as conn:
        if args.library_command == "list":
            rows = library_service.list_library(
                conn,
                status=_status_arg(args.status),
                request=_request_arg(args.request),
                nomenclature=_nomenclature_arg(args.nomenclature),
                item_type=args.type,
                search=args.search,
                limit=args.limit,
            )
            _print_table(
                ["ID", "Tipo", "Estado", "Petición", "Nomenclatura", "Origen", "Título"],
                [[r["id"], r["item_type"], r["local_status"], r["request_status"], r["nomenclature_status"], r["instance_name"], r["title"]] for r in rows],
            )
            return 0
        if args.library_command == "show":
            item = library_service.get_library_item(conn, args.id)
            if not item:
                print("No encontrado")
                return 1
            for key in [
                "id", "title", "item_type", "year", "instance_name", "local_status", "request_status",
                "nomenclature_status", "tmdb_id", "imdb_id", "quality", "resolution", "source", "path",
            ]:
                print(f"{key:22} {item.get(key) or ''}")
            return 0
    return 1


def cmd_requests(args) -> int:
    with _open_conn(args) as conn:
        if args.requests_command == "set-endpoint":
            request_service.set_requests_endpoint(conn, args.url)
            print("✓ Endpoint de peticiones guardado")
            return 0
        if args.requests_command == "sync":
            ep = getattr(args, "endpoint_url", None)
            if ep:
                result = request_service.sync_requests(conn, endpoint_url=ep, force=args.force)
            else:
                result = request_service.sync_emu_requests(conn, force=args.force)
            if result.get("status") == "throttled":
                wait = int(result["wait_seconds"])
                print(f"⚠ Peticiones actualizadas hace menos de una hora. Disponible en {wait // 60} min {wait % 60} s.")
                return 0
            imported = result.get("imported", 0)
            matched = result.get("matched", 0)
            print(f"✓ Peticiones sincronizadas: {imported} importadas, {matched} cruces")
            return 0
        if args.requests_command == "list":
            rows = request_service.list_requests(conn, limit=args.limit, search=args.search)
            _print_table(
                ["ID", "Estado", "Resolución", "Source", "Puntos", "Título"],
                [[r["id"], r.get("emu_status"), r.get("requested_resolution"), r.get("requested_source"), r.get("points"), r["title"]] for r in rows],
            )
            return 0
        if args.requests_command == "show":
            req = request_service.get_request(conn, args.id)
            if not req:
                print("No encontrada")
                return 1
            for key in ["id", "emu_id", "title", "category", "requested_resolution", "requested_source", "emu_status", "points", "comments", "tmdb_id", "imdb_id", "url"]:
                print(f"{key:24} {req.get(key) or ''}")
            match = request_service.get_match_for_request(conn, args.id)
            if match:
                print("\nCruce con biblioteca")
                for key in ["status", "confidence", "library_title", "local_status", "local_resolution", "local_source", "local_path"]:
                    print(f"{key:24} {match.get(key) or ''}")
                if match.get("reasons"):
                    print("\nMotivos:")
                    for line in str(match["reasons"]).splitlines():
                        print(f"  - {line}")
            return 0
        if args.requests_command == "match":
            count = request_service.match_all_requests(conn)
            print(f"✓ Cruces recalculados: {count}")
            return 0
        if args.requests_command == "mark-reviewed":
            found = request_service.mark_request_reviewed(conn, args.id)
            if found:
                print(f"✓ Petición {args.id} marcada como revisada")
            else:
                print(f"✗ Petición {args.id} no encontrada")
            return 0 if found else 1
        if args.requests_command == "create":
            print("⚠ Crear peticiones EMU está preparado, pero no activado todavía.")
            print("  Falta capturar la request real desde DevTools > Network en eMuwarez.")
            return 0
    return 1


def cmd_missing(args) -> int:
    with _open_conn(args) as conn:
        if args.missing_command == "list":
            rows = library_service.list_missing(conn, limit=args.limit)
            _print_table(
                ["ID", "Tipo", "Petición", "Origen", "Título"],
                [[r["id"], r["item_type"], r["request_status"], r["instance_name"], r["title"]] for r in rows],
            )
            return 0
        if args.missing_command == "create-request":
            print("⚠ Crear peticiones EMU está preparado, pero no activado todavía.")
            print("  Cuando capturemos el POST real, este comando usará el LibraryItem indicado.")
            return 0
    return 1


def _print_nomenclature_proposal(proposal: dict) -> None:
    import json as _json
    warnings = []
    errors_list = []
    try:
        warnings = _json.loads(proposal.get("warnings_json") or "[]")
    except Exception:
        pass
    try:
        errors_list = _json.loads(proposal.get("errors_json") or "[]")
    except Exception:
        pass
    print("\n── Nomenclatura / Propuesta ─────────────────────────────")
    print(f"\nTítulo actual:     {proposal.get('current_name') or '–'}")
    print(f"Título propuesto:  {proposal.get('proposed_title') or '–'}")
    print(f"Archivo propuesto: {proposal.get('proposed_filename') or '–'}")
    print(f"Carpeta propuesta: {proposal.get('proposed_folder') or '–'}")
    print(f"Resolución:        {proposal.get('resolution') or '–'}")
    print(f"Source:            {proposal.get('source') or '–'}")
    print(f"Vídeo:             {proposal.get('video_codec') or '–'}")
    print(f"\nEstado: {proposal.get('status', '–')}")
    if warnings:
        print("\nAvisos:")
        for w in warnings:
            print(f"  - {w}")
    if errors_list:
        print("\nErrores:")
        for e in errors_list:
            print(f"  ✗ {e}")
    print("\nAcción: No se ha modificado ningún archivo.")


def cmd_nomenclature(args) -> int:
    from .services.nomenclature import (
        build_nomenclature_proposal, get_latest_nomenclature_proposal
    )
    with _open_conn(args) as conn:
        if args.nomenclature_command == "preview":
            proposal = build_nomenclature_proposal(args.id, force_refresh=args.force, conn=conn)
            _print_nomenclature_proposal(proposal)
            return 0
        if args.nomenclature_command == "show":
            proposal = get_latest_nomenclature_proposal(args.id, conn=conn)
            if not proposal:
                print("No hay propuesta de nomenclatura generada. Usa 'nomenclature preview' para generar una.")
                return 1
            _print_nomenclature_proposal(proposal)
            return 0
        if args.nomenclature_command == "apply":
            from .services.nomenclature import apply_nomenclature_proposal, CONFIRMATION_TOKEN
            do_apply = getattr(args, "nom_apply", False)
            dry_run = getattr(args, "dry_run", False) or not do_apply
            confirmation = getattr(args, "confirm_token", None)
            result = apply_nomenclature_proposal(
                args.id,
                dry_run=dry_run,
                apply=do_apply,
                confirmation=confirmation,
                conn=conn,
            )
            mode = "Previsualización" if result.get("dry_run") else "Aplicar"
            print(f"\n── Nomenclatura / {mode} ─────────────────────────────")
            print(f"\nArchivo original:\n  {result.get('source_path') or '–'}")
            print(f"\nArchivo preparado:\n  {result.get('destination_path') or '–'}")
            print(f"\nEstado:\n  {result.get('status', '–')}")
            if result.get("warnings"):
                print("\nAvisos:")
                for w in result["warnings"]:
                    print(f"  - {w}")
            if result.get("errors"):
                print("\nErrores:")
                for e in result["errors"]:
                    print(f"  ✗ {e}")
            if result.get("message"):
                print(f"\nMensaje:\n  {result['message']}")
            print("\nSeguridad:")
            print("  ✓ El archivo original no se ha renombrado.")
            print("  ✓ Uploadrr no se ha ejecutado.")
            print("  ✓ mkvpropedit no se ha ejecutado.")
            return 0
    return 1


def cmd_upload_modern(args) -> int:
    from .services.upload_preflight import (
        build_upload_preflight, get_upload_job, list_upload_jobs
    )
    with _open_conn(args) as conn:
        if args.upload_command == "preflight":
            result = build_upload_preflight(args.id, request_id=args.request_id, conn=conn)
            print(f"\n── Upload Preflight (library_item {args.id}) ──────────────")
            print(f"Estado: {result['status']}")
            cmd = result.get("command_preview", {})
            if cmd:
                print(f"Tracker:    {cmd.get('tracker', '–')}")
                print(f"Categoría:  {cmd.get('category', '–')}")
                print(f"TMDb:       {cmd.get('tmdb_id', '–')}")
                print(f"Resolución: {cmd.get('resolution', '–')}")
                print(f"Origen:     {cmd.get('source_path', '–')}")
                if cmd.get("command_preview"):
                    print(f"\nComando previsto:")
                    print(f"  {cmd['command_preview']}")
            if result.get("warnings"):
                print("\nAvisos:")
                for w in result["warnings"]:
                    print(f"  - {w}")
            if result.get("errors"):
                print("\nErrores:")
                for e in result["errors"]:
                    print(f"  ✗ {e}")
            print("\nNota: No se ha ejecutado Uploadrr ni subido ningún archivo.")
            return 0
        if args.upload_command == "job":
            job = get_upload_job(args.id, conn=conn)
            if not job:
                print(f"✗ Job {args.id} no encontrado")
                return 1
            for key in ["id", "library_item_id", "status", "stage", "title", "source_path", "error_message", "created_at"]:
                print(f"{key:24} {job.get(key) or ''}")
            return 0
        if args.upload_command == "jobs":
            jobs = list_upload_jobs(conn=conn)
            if not jobs:
                print("No hay preflights de subida registrados.")
                return 0
            _print_table(
                ["ID", "Estado", "Etapa", "Título", "Creado"],
                [[j["id"], j.get("status"), j.get("stage"), j.get("title"), j.get("created_at")] for j in jobs],
            )
            return 0
    return 1


def cmd_prepare(args) -> int:
    with _open_conn(args) as conn:
        path = _target_to_path(conn, args.target)
    legacy_args = [path]
    if not args.apply:
        legacy_args.append("--dry-run")
    legacy_args.extend(args.legacy_args or [])
    return legacy.main(legacy_args)


def cmd_upload(args) -> int:
    if getattr(args, "upload_command", None):
        return cmd_upload_modern(args)
    # Legacy upload path (no subcommand) — not reachable with new parser structure
    print("Usa: upload preflight <id> | upload job <id> | upload jobs")
    return 1


def cmd_tasks(args) -> int:
    with _open_conn(args) as conn:
        rows = task_service.list_tasks(conn, limit=args.limit)
        _print_table(
            ["ID", "Tarea", "Estado", "Inicio", "Fin", "Resumen"],
            [[r["id"], r["name"], r["status"], r["started_at"], r["finished_at"], r["summary"]] for r in rows],
        )
    return 0


def cmd_logs(args) -> int:
    log_file = legacy.current_log_file()
    if not log_file.exists():
        print(f"No existe todavía: {log_file}")
        return 1
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-args.tail:]
    print("\n".join(lines))
    return 0


def cmd_web_contract() -> int:
    print("""eMuwarez Uploadrr — Contrato funcional UI/Backend (v1.0)

Documentación completa:
  docs/ui_backend_contract.md   — especificación detallada de UI, estados, API y flujo
  docs/ui_backend_contract.json — contrato estructurado en JSON (validado)

Secciones de la UI:
  Dashboard · Biblioteca · Faltantes · Peticiones · Subidas · Tareas · Instancias · Logs · Configuración

Estados definitivos:
  LocalStatus:        available · missing · queued · downloading · pending_import
                      import_error · search_error · uploading · uploaded · error · unknown
  RequestStatus:      none · compatible · partial · not_compatible · filled · active_unmatched
  NomenclatureStatus: correct · not_adapted · not_applicable
  EmuExistenceStatus: not_checked · exists · not_exists · possible_duplicate · duplicate_confirmed

Equivalencia CLI ↔ UI:
  sync                          → Dashboard: Sincronizar biblioteca
  requests sync [--force]       → Dashboard: Sincronizar peticiones
  library list/show             → Biblioteca
  missing list                  → Faltantes
  requests list/show/match      → Peticiones
  instances add/list/test       → Instancias
  prepare <id>                  → Adaptar nomenclatura
  upload <id>                   → Subir
  tasks list                    → Tareas

Stubs activos (pendientes de implementación real):
  requests create <id>                → endpoint POST de eMuwarez pendiente de capturar
  missing create-request <id>         → mismo motivo

Puerto web futuro: 9494
Healthcheck: GET /api/health
""")
    return 0


def cmd_web_setup_status() -> int:
    try:
        with connect(db_path()) as conn:
            init_db(conn)
            from .web.services.setup_service import get_setup_state, next_step
            state = get_setup_state(conn)
    except Exception as exc:
        print(f"✗ No se pudo leer el estado del setup: {exc}")
        return 1
    flags = [
        ("Admin configurado", state["admin_configured"]),
        ("Base configurada", state["base_configured"]),
        ("Uploadrr configurado", state["uploadrr_configured"]),
        ("TMDb configurado", state["tmdb_configured"]),
        ("eMuwarez configurado", state["emu_configured"]),
        ("Instancias Radarr", state["radarr_instances"]),
        ("Instancias Sonarr", state["sonarr_instances"]),
        ("Inicializado", state["initialized"]),
    ]
    for label, value in flags:
        mark = "✓" if value else "✗"
        print(f"  {mark}  {label}: {value}")
    ns = next_step(state)
    print(f"\nSiguiente paso: {ns or 'ninguno (setup completo)'}")
    return 0


def cmd_web_create_admin(args) -> int:
    import getpass
    password = os.environ.get("EMUWAREZ_ADMIN_PASSWORD")
    if not password:
        try:
            password = getpass.getpass("Contraseña para el admin: ")
            if not password:
                print("✗ La contraseña no puede estar vacía")
                return 1
            confirm = getpass.getpass("Confirmar contraseña: ")
            if password != confirm:
                print("✗ Las contraseñas no coinciden")
                return 1
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return 1
    from .web.security import validate_password_strength
    err = validate_password_strength(password)
    if err:
        print(f"✗ {err}")
        return 1
    try:
        with connect(db_path()) as conn:
            init_db(conn)
            from .web.services.auth_service import admin_exists, create_user
            if admin_exists(conn):
                print("✗ Ya existe un usuario administrador.")
                return 1
            uid = create_user(conn, args.username, password, role="admin")
            conn.commit()
        print(f"✓ Usuario administrador '{args.username}' creado con ID {uid}")
    except Exception as exc:
        print(f"✗ {exc}")
        return 1
    return 0


def cmd_web_info() -> int:
    print(
        "Backend: FastAPI\n"
        "App: eMuwarez Uploadrr\n"
        "Backend URL:    http://localhost:9494\n"
        "Frontend dev:   http://localhost:5173\n"
        "\n"
        "── Frontend ────────────────────────────────────────\n"
        "  cd frontend && npm install\n"
        "  npm run dev      # servidor de desarrollo (proxy → :9494)\n"
        "  npm run build    # construir para producción en frontend/dist\n"
        "  npm run preview  # previsualizar el build en :4173\n"
        "\n"
        "── Backend + Frontend producción ───────────────────\n"
        "  npm run build    # (en frontend/)\n"
        "  python3 emuwarez_uploader.py web serve --port 9494\n"
        "  # Sirve API en /api/* y frontend en /* desde frontend/dist\n"
        "\n"
        "── Endpoints de salud y runtime ────────────────────\n"
        "  GET  http://localhost:9494/api/health\n"
        "  GET  http://localhost:9494/api/runtime\n"
        "\n"
        "── Setup wizard ─────────────────────────────────────\n"
        "  GET  http://localhost:9494/api/setup/status\n"
        "  POST http://localhost:9494/api/setup/admin      (primer arranque, sin auth)\n"
        "  POST http://localhost:9494/api/setup/base       (requiere Bearer token)\n"
        "  POST http://localhost:9494/api/setup/uploadrr   (requiere Bearer token)\n"
        "  POST http://localhost:9494/api/setup/tmdb       (requiere Bearer token)\n"
        "  POST http://localhost:9494/api/setup/emu        (requiere Bearer token)\n"
        "  POST http://localhost:9494/api/setup/instances  (requiere Bearer token)\n"
        "  POST http://localhost:9494/api/setup/complete   (requiere Bearer token)\n"
        "\n"
        "── Autenticación ────────────────────────────────────\n"
        "  POST http://localhost:9494/api/auth/login\n"
        "  GET  http://localhost:9494/api/auth/me          (requiere Bearer token)\n"
        "  POST http://localhost:9494/api/auth/logout      (requiere Bearer token)\n"
        "\n"
        "── Biblioteca ───────────────────────────────────────\n"
        "  POST http://localhost:9494/api/sync\n"
        "  GET  http://localhost:9494/api/library\n"
        "  GET  http://localhost:9494/api/library/{id}\n"
        "  GET  http://localhost:9494/api/missing\n"
        "  GET  http://localhost:9494/api/instances\n"
        "  GET  http://localhost:9494/api/dashboard/summary\n"
        "  GET  http://localhost:9494/api/dashboard/activity\n"
        "\n"
        "── Documentación interactiva ────────────────────────\n"
        "  http://localhost:9494/api/docs\n"
        "  http://localhost:9494/api/openapi.json\n"
        "\n"
        "── Setup desde CLI ──────────────────────────────────\n"
        "  python3 emuwarez_uploader.py web setup-status\n"
        "  python3 emuwarez_uploader.py web create-admin --username admin\n"
        "\n"
        "Instalar dependencias web:\n"
        "  pip install -e \".[web]\""
    )
    return 0


def cmd_web_serve(args) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "✗ Faltan dependencias web. Instala el proyecto con las dependencias web:\n"
            "  pip install -e \".[web]\"\n"
            "O instala uvicorn y fastapi directamente:\n"
            "  pip install uvicorn fastapi pydantic"
        )
        return 1
    uvicorn.run(
        "emuwarez_uploadrr.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def modern_main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "configure":
            return legacy.main(["--configure"])
        if args.command == "doctor":
            return legacy.main(["--doctor"])
        if args.command == "test-apis":
            return legacy.main(["--test-apis"])
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
        if args.command == "prepare":
            return cmd_prepare(args)
        if args.command == "upload":
            return cmd_upload(args)
        if args.command == "tasks":
            return cmd_tasks(args)
        if args.command == "logs":
            return cmd_logs(args)
        if args.command == "legacy":
            return legacy.main(args.legacy_args or [])
        if args.command == "web-contract":
            return cmd_web_contract()
        if args.command == "web":
            if args.web_command == "info":
                return cmd_web_info()
            if args.web_command == "serve":
                return cmd_web_serve(args)
            if args.web_command == "setup-status":
                return cmd_web_setup_status()
            if args.web_command == "create-admin":
                return cmd_web_create_admin(args)
        parser.error("Comando no soportado")
        return 2
    except IntegrationError as exc:
        print(f"✗ {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nInterrumpido.")
        return 130


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Compatibility mode: old usage still works exactly as before.
    if not argv:
        return legacy.main(argv)
    first = argv[0]
    if first not in MODERN_COMMANDS:
        return legacy.main(argv)
    return modern_main(argv)


# Backwards-compatible exports used by earlier refactor modules/tests.
parse_args = legacy.parse_args
process_path = legacy.process_path
configure = legacy.configure
doctor = legacy.doctor
test_apis = legacy.test_apis

__all__ = ["main", "modern_main", "build_parser", "parse_args", "process_path", "configure", "doctor", "test_apis"]
