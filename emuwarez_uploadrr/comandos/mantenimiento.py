"""Comandos de mantenimiento y de datos demo."""
from __future__ import annotations

from .comunes import _open_conn, _print_table


def cmd_maintenance(args) -> int:
    from emuwarez_uploadrr.services import backup_service, maintenance_service

    cmd = args.maintenance_command

    if cmd == "status":
        inv = backup_service.get_config_inventory()
        db_st = maintenance_service.get_database_maintenance_status()
        bkps = backup_service.list_config_backups()
        print(f"CONFIG_DIR:   {inv.get('config_dir')}")
        print(f"Archivos:     {len(inv.get('files', []))}")
        print(f"Tamaño total: {inv.get('total_size_bytes', 0):,} bytes")
        if db_st.get("ok"):
            print(f"\nBD: {db_st.get('size_bytes', 0):,} bytes  |  freelist: {db_st.get('freelist_count', 0)}")
        else:
            print(f"\nBD: {db_st.get('error')}")
        print(f"\nBackups:      {len(bkps)}")
        if bkps:
            print(f"Último:       {bkps[0]['name']}  ({bkps[0]['size_bytes']:,} bytes)")
        return 0

    if cmd == "backup":
        result = backup_service.create_config_backup(
            include_secrets=getattr(args, "include_secrets", False),
            confirmation=getattr(args, "confirm", None),
        )
        if result.get("ok"):
            print(f"✓ Backup creado: {result['archive_path']}  ({result['size_bytes']:,} bytes)")
        else:
            print(f"✗ {result.get('error')}")
        return 0 if result.get("ok") else 1

    if cmd == "list-backups":
        bkps = backup_service.list_config_backups()
        if not bkps:
            print("No hay backups.")
            return 0
        _print_table(
            ["Nombre", "Tamaño", "Fecha"],
            [[b["name"], f"{b['size_bytes']:,}", b["created_at"]] for b in bkps],
        )
        return 0

    if cmd == "restore":
        result = backup_service.restore_config_backup(
            args.backup_path,
            dry_run=not getattr(args, "maint_apply", False),
            apply=getattr(args, "maint_apply", False),
            confirmation=getattr(args, "confirm", None),
        )
        if result.get("ok"):
            print(f"✓ {result.get('message') or result.get('action')}")
            if result.get("dry_run"):
                print(f"  Archivos en el backup: {result.get('files_in_archive', 0)}")
        else:
            print(f"✗ {result.get('error')}")
        return 0 if result.get("ok") else 1

    if cmd == "db-integrity":
        result = maintenance_service.run_database_integrity_check()
        icon = "✓" if result.get("ok") else "✗"
        print(f"{icon} {result.get('message') or result.get('error')}")
        return 0 if result.get("ok") else 1

    if cmd == "db-vacuum":
        result = maintenance_service.run_database_vacuum(
            dry_run=not getattr(args, "maint_apply", False),
            apply=getattr(args, "maint_apply", False),
            confirmation=getattr(args, "confirm", None),
        )
        if result.get("ok"):
            print(f"✓ {result.get('message')}")
            if not result.get("dry_run"):
                print(f"  Antes: {result.get('size_bytes_before', 0):,} bytes  →  Después: {result.get('size_bytes_after', 0):,} bytes")
        else:
            print(f"✗ {result.get('error')}")
        return 0 if result.get("ok") else 1

    return 1


def cmd_demo(args) -> int:
    from ..services.demo_seed import seed_demo_data, reset_demo_data
    with _open_conn(args) as conn:
        if args.demo_command == "seed":
            try:
                result = seed_demo_data(
                    conn,
                    media_root=args.media_root,
                    prepared_root=args.prepared_root,
                    confirm_token=args.confirm_token,
                )
            except ValueError as exc:
                print(f"✗ {exc}")
                return 1
            print("✓ Datos demo sembrados")
            print(f"  library_item_id : {result['library_item_id']}")
            print(f"  request_item_id : {result['request_item_id']}")
            print(f"  archivo simulado: {result['media_file']}")
            return 0
        if args.demo_command == "reset":
            try:
                reset_demo_data(conn, confirm_token=args.confirm_token)
            except ValueError as exc:
                print(f"✗ {exc}")
                return 1
            print("✓ Datos demo eliminados de la BD")
            return 0
    return 1
