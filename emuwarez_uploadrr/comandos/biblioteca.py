"""Comandos de instancias, sincronización, biblioteca, peticiones, faltantes y *arr."""
from __future__ import annotations

from ..services import instances as instance_service
from ..services import library as library_service
from ..services import requests as request_service
from .comunes import _nomenclature_arg, _open_conn, _print_table, _request_arg, _status_arg


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
                "file_exists", "file_verified_at", "arr_queue_status", "recommended_action", "diagnostic_summary",
            ]:
                print(f"{key:26} {item.get(key) if item.get(key) is not None else ''}")
            return 0
        if args.library_command == "verify-files":
            from ..services.library_verification import verify_library_files
            filters: dict = {}
            if getattr(args, "status", None):
                filters["status"] = args.status
            result = verify_library_files(conn, filters=filters, limit=getattr(args, "limit", None))
            print(f"✓ Verificados: {result['items_checked']}  |  Encontrados: {result['files_found']}  |  Errores: {result['errors']}  |  Advertencias: {result['warnings']}")
            return 0
        if args.library_command == "verify-file":
            from ..services.library_verification import verify_library_item_file
            result = verify_library_item_file(args.id, conn)
            if result.get("error"):
                print(f"✗ {result['error']}")
                return 1
            print(f"ID {args.id}: {result.get('title')}")
            print(f"  path:       {result.get('path') or '–'}")
            print(f"  existe:     {'sí' if result.get('file_exists') else 'no'}")
            print(f"  es vídeo:   {'sí' if result.get('file_is_video') else 'no'}")
            print(f"  tamaño:     {result.get('file_size_on_disk') or '–'} bytes")
            if result.get("file_verification_error"):
                print(f"  error:      {result['file_verification_error']}")
            return 0
        if args.library_command == "recommendations":
            from ..services.recommendations import refresh_recommendations
            result = refresh_recommendations(conn)
            print(f"✓ Recomendaciones recalculadas: {result['items_updated']}  |  Errores: {result['errors']}")
            return 0
        if args.library_command == "recommendation":
            from ..services.recommendations import get_recommendation_for_item
            rec = get_recommendation_for_item(args.id, conn)
            if not rec:
                print("No encontrado")
                return 1
            print(f"ID {args.id}: {rec.get('title')}")
            print(f"  diagnóstico:       {rec.get('diagnostic_status') or '–'}")
            print(f"  resumen:           {rec.get('diagnostic_summary') or '–'}")
            print(f"  acción recomend.:  {rec.get('recommended_action') or '–'}")
            reasons = rec.get("recommendation_reasons") or []
            if reasons:
                print("  razones:")
                for r in reasons:
                    print(f"    - {r}")
            return 0
        if args.library_command == "diagnostics":
            limit = getattr(args, "limit", 50)
            status_filter = getattr(args, "status", None)
            where = ""
            params: list = []
            if status_filter:
                where = "WHERE local_status = ?"
                params.append(status_filter)
            rows = conn.execute(
                f"""
                SELECT id, title, local_status, file_exists, arr_queue_status,
                       diagnostic_status, recommended_action
                FROM library_items {where} ORDER BY updated_at DESC LIMIT ?
                """,
                params + [limit],
            ).fetchall()
            if not rows:
                if not conn.execute("SELECT COUNT(*) FROM library_items").fetchone()[0]:
                    print("Biblioteca vacía. Ejecuta: python3 emuwarez_uploader.py sync")
                else:
                    print("Sin resultados con ese filtro.")
                return 0
            _print_table(
                ["ID", "Estado", "Archivo", "Queue", "Diagnóstico", "Acción recomendada", "Título"],
                [
                    [
                        r["id"],
                        r["local_status"],
                        "OK" if r["file_exists"] else ("–" if r["file_exists"] is None else "NO"),
                        r["arr_queue_status"] or "–",
                        r["diagnostic_status"] or "–",
                        r["recommended_action"] or "–",
                        r["title"],
                    ]
                    for r in rows
                ],
            )
            return 0
    return 1


def cmd_requests(args) -> int:
    with _open_conn(args) as conn:
        if args.requests_command == "sync":
            result = request_service.sync_emu_requests(conn, force=args.force)
            if result.get("status") == "throttled":
                wait = int(result["wait_seconds"])
                print(f"⚠ Peticiones actualizadas hace menos de una hora. Disponible en {wait // 60} min {wait % 60} s.")
                return 0
            if result.get("status") == "busy":
                print(f"⚠ {result['message']}")
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
        # Phase 8B
        if args.requests_command == "readiness-refresh":
            from ..services.request_readiness import refresh_request_readiness
            result = refresh_request_readiness(conn)
            # Ninguna calculada y alguna con error (p. ej. no se pudo leer la biblioteca): un script tiene que enterarse.
            fallo = result["errors"] and not result["items_updated"]
            print(f"{'✗' if fallo else '✓'} Readiness recalculado: {result['items_updated']} peticiones  |  "
                  f"errores: {result['errors']}")
            return 1 if fallo else 0
        if args.requests_command == "readiness":
            from ..services.request_readiness import list_request_readiness, get_request_readiness
            req_id = getattr(args, "id", None)
            if req_id:
                data = get_request_readiness(req_id, conn)
                if not data:
                    print(f"Sin readiness para petición {req_id}. Ejecuta: python3 emuwarez_uploader.py requests readiness-refresh")
                    return 1
                print(f"Petición: {data.get('title')} (ID {req_id})")
                print(f"  Estado readiness : {data['status']}")
                print(f"  Acción           : {data.get('recommended_action') or '—'}")
                print(f"  Compat. score    : {data.get('compatibility_score')}")
                print(f"  Readiness score  : {data.get('upload_readiness_score')}")
                print(f"  Candidato local  : #{data.get('best_library_item_id') or '—'}")
                if data.get("blockers"):
                    print("  Bloqueadores:")
                    for b in data["blockers"]:
                        print(f"    - {b}")
                return 0
            limit = getattr(args, "limit", 50)
            rows = list_request_readiness(conn, limit=limit)
            if not rows:
                print("Sin readiness calculado. Ejecuta: python3 emuwarez_uploader.py requests readiness-refresh")
                return 0
            _print_table(
                ["ID", "Título", "Estado", "Acción", "Candidato"],
                [
                    [
                        r["request_item_id"],
                        (r.get("title") or "")[:40],
                        r["status"],
                        r.get("recommended_action") or "—",
                        f"#{r.get('best_library_item_id')}" if r.get("best_library_item_id") else "—",
                    ]
                    for r in rows
                ],
            )
            return 0
        if args.requests_command == "candidates":
            from ..services.request_readiness import get_candidates_for_request
            items = get_candidates_for_request(args.id, conn)
            if not items:
                print(f"Sin candidatos para petición {args.id}. Ejecuta: python3 emuwarez_uploader.py requests readiness-refresh")
                return 0
            _print_table(
                ["Rank", "Lib ID", "Título", "Compat.", "Readiness", "Acción"],
                [
                    [
                        c["candidate_rank"],
                        c["library_item_id"],
                        (c.get("lib_title") or "")[:35],
                        f"{c.get('compatibility_score', 0):.0f}",
                        c.get("readiness_status") or "—",
                        c.get("recommended_action") or "—",
                    ]
                    for c in items
                ],
            )
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
        if args.missing_command == "diagnostics":
            from ..models import LocalStatus
            limit = getattr(args, "limit", 50)
            missing_statuses = list(LocalStatus.not_available())
            placeholders = ",".join("?" * len(missing_statuses))
            rows = conn.execute(
                f"""
                SELECT id, title, local_status, arr_queue_status, arr_queue_progress,
                       arr_queue_error, arr_history_error, diagnostic_status, recommended_action
                FROM library_items WHERE local_status IN ({placeholders})
                ORDER BY updated_at DESC LIMIT ?
                """,
                missing_statuses + [limit],
            ).fetchall()
            if not rows:
                print("Sin faltantes en biblioteca. Ejecuta: python3 emuwarez_uploader.py sync")
                return 0
            _print_table(
                ["ID", "Estado local", "Queue", "Diagnóstico", "Acción recomendada", "Título"],
                [
                    [
                        r["id"],
                        r["local_status"],
                        r["arr_queue_status"] or "–",
                        r["diagnostic_status"] or "–",
                        r["recommended_action"] or "–",
                        r["title"],
                    ]
                    for r in rows
                ],
            )
            return 0
    return 1


def cmd_arr(args) -> int:
    with _open_conn(args) as conn:
        instances = instance_service.list_instances(conn, enabled_only=True)
        if not instances:
            print("⚠ Sin instancias Radarr/Sonarr habilitadas. Añade una con:")
            print("  python3 emuwarez_uploader.py instances add radarr --name ... --url ... --api-key ...")
            return 0

        if args.arr_command == "health":
            from ..services.arr_health import collect_arr_health
            result = collect_arr_health(conn)
            summary = result.get("summary", {})
            print("\n── Salud Radarr/Sonarr ──────────────────────────────────")
            print(f"  Radarr: {summary.get('radarr', 0)} instancias  |  Sonarr: {summary.get('sonarr', 0)} instancias")
            print(f"  OK: {summary.get('ok', 0)}  |  Warning: {summary.get('warning', 0)}  |  Error: {summary.get('error', 0)}")
            print()
            for inst in result.get("instances", []):
                mark = "✓" if inst.get("ok") else "✗"
                version = inst.get("version") or ""
                err = inst.get("error") or ""
                print(f"  {mark} [{inst.get('instance_type', '?')}] {inst.get('instance_name', '?')}  {version}  {err}")
            return 0

        if args.arr_command == "refresh-health":
            from ..services.arr_health import collect_arr_health, refresh_arr_queue_diagnostics, refresh_arr_history_diagnostics
            include_queue = not getattr(args, "no_queue", False)
            include_history = not getattr(args, "no_history", False)
            history_size = getattr(args, "history_size", 100)
            print("Comprobando salud ARR...")
            health = collect_arr_health(conn)
            s = health.get("summary", {})
            print(f"  OK: {s.get('ok', 0)}  Warning: {s.get('warning', 0)}  Error: {s.get('error', 0)}")
            if include_queue:
                print("Actualizando diagnósticos de queue...")
                qr = refresh_arr_queue_diagnostics(conn)
                print(f"  Items actualizados: {qr.get('library_items_updated', 0)}  (queue encontrada: {qr.get('queue_items_found', 0)})")
                if qr.get("errors"):
                    for e in qr["errors"]:
                        print(f"  ✗ {e.get('instance')}: {e.get('error')}")
            if include_history:
                print("Actualizando diagnósticos de historial...")
                hr = refresh_arr_history_diagnostics(conn, page_size=history_size)
                print(f"  Items actualizados: {hr.get('library_items_updated', 0)}  (historial leído: {hr.get('history_items_found', 0)})")
                if hr.get("errors"):
                    for e in hr["errors"]:
                        print(f"  ✗ {e.get('instance')}: {e.get('error')}")
            print("✓ Salud ARR actualizada")
            return 0
    return 1
