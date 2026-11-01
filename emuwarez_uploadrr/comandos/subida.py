"""Comandos de subida, tareas y registros."""
from __future__ import annotations

from ..constants import LOG_DIR
from ..services import tasks as task_service
from .comunes import _open_conn, _print_table


def cmd_upload_modern(args) -> int:
    from ..services.upload_preflight import (
        build_upload_preflight,
    )
    from ..services.upload_execution import (
        get_upload_job, list_upload_jobs, get_upload_job_logs,
        get_upload_job_artifacts, start_upload_job, cancel_upload_job,
        retry_upload_job,
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
                    print("\nComando previsto:")
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

        if args.upload_command in ("job", "status"):
            job = get_upload_job(args.id, conn=conn)
            if not job:
                print(f"✗ Job {args.id} no encontrado")
                return 1
            fields = [
                "id", "library_item_id", "status", "stage", "title",
                "source_path", "prepared_path", "exit_code", "duration_seconds",
                "result_url", "result_torrent_id", "error_message",
                "retry_count", "retry_of_job_id",
                "started_at", "finished_at", "created_at",
            ]
            for key in fields:
                val = job.get(key)
                if val is not None:
                    print(f"{key:28} {val}")
            return 0

        if args.upload_command == "jobs":
            status_filter = getattr(args, "status", None)
            filters = {"limit": 200}
            if status_filter:
                filters["status"] = status_filter
            jobs = list_upload_jobs(filters=filters, conn=conn)
            if not jobs:
                msg = f"No hay jobs con estado '{status_filter}'." if status_filter else "No hay preflights de subida registrados."
                print(msg)
                return 0
            _print_table(
                ["ID", "Estado", "Duración", "Exit", "Resultado", "Título"],
                [
                    [
                        j["id"],
                        j.get("status"),
                        f"{j['duration_seconds']}s" if j.get("duration_seconds") is not None else "–",
                        j.get("exit_code") if j.get("exit_code") is not None else "–",
                        j.get("result_url", "")[:40] if j.get("result_url") else "–",
                        j.get("title"),
                    ]
                    for j in jobs
                ],
            )
            return 0

        if args.upload_command == "logs":
            result = get_upload_job_logs(args.id, limit=args.limit, conn=conn)
            logs = result.get("logs", [])
            if not logs:
                print(f"No hay logs para el job {args.id}.")
                return 0
            print(f"\n── Logs / Job {args.id} ({result['total']} entradas) ──────────")
            for entry in logs:
                ts = entry.get("created_at", "")[:19].replace("T", " ")
                stream = entry.get("stream", "system")
                level = entry.get("level", "info")
                msg = entry.get("message", "")
                print(f"[{ts}] [{stream}/{level}] {msg}")
            return 0

        if args.upload_command == "artifacts":
            artifacts = get_upload_job_artifacts(args.id, conn=conn)
            if not artifacts:
                print(f"No hay artefactos para el job {args.id}.")
                return 0
            print(f"\n── Artefactos / Job {args.id} ─────────────────────────")
            for a in artifacts:
                parts = [f"[{a['artifact_type']}]"]
                if a.get("name"):
                    parts.append(a["name"])
                if a.get("url"):
                    parts.append(f"url={a['url']}")
                if a.get("path"):
                    parts.append(f"path={a['path']}")
                if a.get("value"):
                    parts.append(f"value={a['value']}")
                print("  " + "  ".join(parts))
            return 0

        if args.upload_command == "start":
            do_apply = getattr(args, "up_apply", False)
            confirmation = getattr(args, "up_confirm", None)
            dry_run = not do_apply
            result = start_upload_job(
                args.id,
                dry_run=dry_run,
                start=do_apply,
                confirmation=confirmation,
                conn=conn,
                wait=do_apply,
            )
            action = result.get("action", "unknown")
            if dry_run or action == "dry_run":
                print("\n── Uploadrr / Start dry-run ─────────────────────────────")
                print(f"\nJob:\n  {args.id}")
                print(f"\nEstado:\n  {result.get('status', '–')}")
                print(f"\nComando previsto:\n  {result.get('command_preview', '–')}")
                if result.get("warnings"):
                    print("\nAvisos:")
                    for w in result["warnings"]:
                        print(f"  - {w}")
                if result.get("errors"):
                    print("\nErrores:")
                    for e in result["errors"]:
                        print(f"  ✗ {e}")
                print(f"\nAcción:\n  {result.get('message', 'No se ha ejecutado Uploadrr.')}")
                return 0 if result.get("valid", True) else 1
            if action == "blocked":
                print("\n── Uploadrr / Bloqueado ─────────────────────────────")
                for e in result.get("errors", []):
                    print(f"  ✗ {e}")
                return 1
            if action == "started":
                print("\n── Uploadrr / Ejecución ─────────────────────────────")
                print(f"\nJob:\n  {args.id}")
                print(f"\nEstado:\n  {result.get('status', '–')}")
                print("\nSeguridad:")
                print("  ✓ Se usa archivo preparado." if result.get("using_prepared_path") else "  ⚠ Se usa el archivo original.")
                print("  ✓ No se modifica Uploadrr/.")
                print("  ✓ No se ejecuta mkvpropedit.")
                print("  ✓ Secretos ocultos en logs.")
                print(f"\nMensaje:\n  {result.get('message', '–')}")
                print(f"\nUsa 'upload logs {args.id}' para ver el detalle.")
                return 0 if result.get("status") == "completed" else 1
            return 1

        if args.upload_command == "retry":
            do_apply = getattr(args, "up_apply", False)
            confirmation = getattr(args, "up_confirm", None)
            dry_run = not do_apply
            result = retry_upload_job(
                args.id,
                dry_run=dry_run,
                start=do_apply,
                confirmation=confirmation,
                wait=do_apply,
            )
            if dry_run or result.get("action") == "dry_run":
                print("\n── Retry dry-run ────────────────────")
                original = get_upload_job(args.id, conn=conn)
                orig_status = original.get("status", "–") if original else "–"
                print(f"Job original: {args.id} ({orig_status})")
                print("Job nuevo (simulado): no creado")
                print(f"Reintentos previstos: {result.get('retry_count_would_be', '–')}")
                if result.get("command_preview"):
                    print(f"Comando previsto: {result['command_preview']}")
                print("No se ha ejecutado Uploadrr.")
                return 0
            if result.get("action") == "blocked":
                for e in result.get("errors") or [result.get("message") or "Bloqueado."]:
                    print(f"✗ {e}")
                return 1
            print("\n── Retry iniciado ────────────────────")
            new_job_id = result.get("new_job_id", "–")
            print(f"Job nuevo: {new_job_id}")
            print(f"Reintento: {result.get('retry_count', '–')}")
            print(f"Estado: {result.get('status', '–')}")
            print(f"Mensaje: {result.get('message', '–')}")
            print(f"\nUsa 'upload logs {new_job_id}' para ver el detalle.")
            return 0 if result.get("status") == "completed" else 1

        if args.upload_command == "cancel":
            result = cancel_upload_job(args.id, conn=conn)
            mark = "✓" if result.get("ok") else "✗"
            print(f"{mark} {result.get('message', '')}")
            return 0 if result.get("ok") else 1
    return 1


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
    log_file = LOG_DIR / "emuwarez-renamer.log"
    if not log_file.exists():
        print(f"No existe todavía: {log_file}")
        return 1
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-args.tail:]
    print("\n".join(lines))
    return 0
