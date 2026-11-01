"""Comandos `web`: estado, administrador, contraseña, información, diagnóstico y servidor."""
from __future__ import annotations

import os

from ..database import connect, init_db, db_path, preparar_base


def cmd_web_setup_status() -> int:
    try:
        with connect(db_path()) as conn:
            init_db(conn)
            from ..web.services.setup_service import get_setup_state, next_step
            state = get_setup_state(conn)
    except Exception as exc:
        print(f"✗ No se pudo leer el estado del setup: {exc}")
        return 1
    flags = [
        ("Admin configurado", state["admin_configured"]),
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
    from ..web.security import validate_password_strength
    err = validate_password_strength(password)
    if err:
        print(f"✗ {err}")
        return 1
    try:
        with connect(db_path()) as conn:
            init_db(conn)
            from ..web.services.auth_service import admin_exists, create_user
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


def cmd_web_reset_password(args) -> int:
    import getpass
    password = os.environ.get("EMUWAREZ_ADMIN_PASSWORD")
    if not password:
        try:
            password = getpass.getpass("Nueva contraseña: ")
            if not password:
                print("✗ La contraseña no puede estar vacía")
                return 1
            confirm = getpass.getpass("Confirmar nueva contraseña: ")
            if password != confirm:
                print("✗ Las contraseñas no coinciden")
                return 1
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            return 1
    from ..web.security import validate_password_strength
    err = validate_password_strength(password)
    if err:
        print(f"✗ {err}")
        return 1
    try:
        with connect(db_path()) as conn:
            init_db(conn)
            from ..web.services.auth_service import get_user_by_username, update_password
            user = get_user_by_username(conn, args.username)
            if not user:
                print(f"✗ No existe el usuario '{args.username}'.")
                return 1
            update_password(conn, user["id"], password)
            conn.commit()
        print(f"✓ Contraseña de '{args.username}' restablecida.")
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
        "── Endpoint de salud ───────────────────────────────\n"
        "  GET  http://localhost:9494/api/health\n"
        "\n"
        "── Setup wizard ─────────────────────────────────────\n"
        "  GET  http://localhost:9494/api/setup/status\n"
        "  POST http://localhost:9494/api/setup/admin      (primer arranque, sin auth)\n"
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
        "  python3 emuwarez_uploader.py web reset-password --username admin\n"
        "\n"
        "Instalar dependencias web:\n"
        "  pip install -e \".[web]\"\n"
        "\n"
        "── Docker ───────────────────────────────────────────\n"
        "  Build:    docker build -t emuwarez-uploadrr:local .\n"
        "  Compose:  docker compose -f docker-compose.example.yml up -d --build\n"
        "  URL:      http://localhost:9494\n"
        "  Config:   /config  (montar como volumen persistente)\n"
        "  Uploadrr: /opt/Uploadrr  (bind mount externo, no incluido en imagen)\n"
        "  Media:    monta tu biblioteca en el contenedor (p. ej. -v /mnt/storage:/data,\n"
        "            igual que Radarr/Sonarr) y configura esa misma ruta en\n"
        "            Ajustes > uploadrr_allowed_roots — sin ella, las subidas\n"
        "            reales se bloquean."
    )
    return 0


def cmd_web_doctor() -> int:
    from emuwarez_uploadrr.services.runtime_diagnostics import get_runtime_diagnostics
    result = get_runtime_diagnostics()
    icons = {"ok": "✓", "warning": "⚠", "error": "✗", "unknown": "?"}
    print("\nRuntime diagnostics\n")
    for check in result["checks"]:
        icon = icons.get(check["status"], "?")
        label = check["name"].replace("_", " ").title()
        print(f"{label}:")
        print(f"  {icon} {check['message']}")
        if check.get("details"):
            for k, v in check["details"].items():
                print(f"    {k}: {v}")
    if result["warnings"]:
        print(f"\nAdvertencias: {len(result['warnings'])}")
    if result["errors"]:
        print(f"\nErrores: {len(result['errors'])}")
    if result["ok"]:
        print("\n✓ Sistema listo")
    else:
        print("\n✗ Hay errores que resolver")
    return 0 if result["ok"] else 1


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
    # Antes de levantar el servidor: una base más nueva se rechaza con un mensaje, no con una traza.
    preparar_base()
    uvicorn.run(
        "emuwarez_uploadrr.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        # Al parar, uvicorn espera a que se cierren todas las conexiones, y
        # /api/eventos no se cierra mientras haya una pestaña abierta: sin
        # este tope, `docker stop` acaba siempre en SIGKILL (código 137) tras
        # el stop_grace_period entero. Pasado el tope corta lo que quede.
        timeout_graceful_shutdown=5,
    )
    return 0
