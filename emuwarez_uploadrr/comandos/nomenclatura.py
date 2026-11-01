"""Comandos de nomenclatura y de título MKV."""
from __future__ import annotations

from .comunes import _open_conn, _print_table


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
    from ..services.nomenclature import (
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
            from ..services.nomenclature import apply_nomenclature_proposal
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

        # Phase 10A subcommands
        if args.nomenclature_command == "sources":
            from ..services.source_assistant import list_emu_sources
            sources = list_emu_sources()
            _print_table(["Código", "Label"], [[s["code"], s["label"]] for s in sources])
            return 0

        if args.nomenclature_command == "providers":
            from ..services.source_assistant import list_emu_providers
            providers = list_emu_providers()
            _print_table(["Código", "Nombre"], [[p["code"], p["name"]] for p in providers])
            return 0

        if args.nomenclature_command == "fields":
            from ..services.source_assistant import build_editable_nomenclature_fields
            result = build_editable_nomenclature_fields(args.id, conn=conn)
            if "error" in result:
                print(f"✗ {result['error']}")
                return 1
            fields = result.get("fields", {})
            print(f"Título:           {fields.get('title')}")
            print(f"Año:              {fields.get('year')}")
            print(f"Resolución:       {fields.get('resolution')}")
            print(f"Source:           {fields.get('source')}")
            print(f"Provider:         {fields.get('provider')}")
            print(f"Códec:            {fields.get('video_codec')}")
            print(f"Audio:            {fields.get('audio_summary')}")
            print(f"Subs:             {fields.get('subs')}")
            print(f"Tag:              {fields.get('tag')}")
            print(f"Torrent name:     {result.get('torrent_name')}")
            print(f"MKV title:        {result.get('internal_mkv_title')}")
            tmdb_avail = result.get("tmdb_available_providers", [])
            if tmdb_avail:
                print(f"Providers TMDb:   {', '.join(tmdb_avail)}")
            return 0

        if args.nomenclature_command == "preview-fields":
            from ..services.source_assistant import update_nomenclature_fields_preview
            import json as _json
            fields_json = getattr(args, "fields_json", None) or "{}"
            try:
                fields = _json.loads(fields_json)
            except Exception:
                print("✗ JSON de campos inválido")
                return 1
            result = update_nomenclature_fields_preview(args.id, fields, conn=conn)
            print(f"Torrent name:  {result.get('torrent_name')}")
            print(f"MKV title:     {result.get('internal_mkv_title')}")
            return 0

    return 1


def cmd_mkv_title(args) -> int:
    from ..services.mkv_title import (
        preview_internal_title_update,
        apply_internal_title_update,
    )
    with _open_conn(args) as conn:
        if args.mkv_command == "preview":
            result = preview_internal_title_update(args.id, conn=conn)
            print(f"Status:         {result.get('status')}")
            print(f"Prepared path:  {result.get('prepared_path')}")
            print(f"Torrent name:   {result.get('torrent_name')}")
            print(f"Internal title: {result.get('internal_mkv_title')}")
            print(f"mkvpropedit:    {'disponible' if result.get('mkvpropedit_available') else 'no instalado'}")
            if result.get("command_preview"):
                print(f"Comando:        {result['command_preview']}")
            for e in result.get("errors", []):
                print(f"  ✗ {e}")
            for w in result.get("warnings", []):
                print(f"  ⚠ {w}")
            return 0 if result.get("status") != "blocked" else 1

        if args.mkv_command == "apply":
            do_apply = getattr(args, "mkv_apply", False)
            dry_run = not do_apply
            confirm = getattr(args, "mkv_confirm", None)
            result = apply_internal_title_update(
                args.id,
                dry_run=dry_run,
                apply=do_apply,
                confirmation=confirm,
                conn=conn,
            )
            print(f"Status: {result.get('status')}")
            if result.get("status") == "applied":
                print(f"  ✓ Título MKV aplicado: {result.get('internal_mkv_title')}")
            elif dry_run:
                print(f"  [dry-run] Se aplicaría: {result.get('internal_mkv_title')}")
                print(f"  Comando: {result.get('command_preview')}")
            for e in result.get("errors", []):
                print(f"  ✗ {e}")
            if not do_apply:
                print("  ✓ mkvpropedit no se ha ejecutado (dry-run).")
            return 0 if result.get("status") not in ("blocked", "error") else 1
    return 1
