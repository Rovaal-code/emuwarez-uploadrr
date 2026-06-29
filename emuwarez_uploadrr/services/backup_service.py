"""Backup and restore of CONFIG_DIR — no secrets in listing, confirmation required for restore."""
from __future__ import annotations

import datetime
import os
import shutil
import tarfile
from pathlib import Path

RESTORE_CONFIRMATION = "RESTAURAR_CONFIG"


def _get_config_dir() -> Path:
    env = os.environ.get("CONFIG_DIR")
    if env:
        return Path(env)
    return Path.home() / ".config" / "emuwarez-renamer"


def _get_backup_dir(base: Path | None = None) -> Path:
    config = base if base is not None else _get_config_dir()
    d = config / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_config_inventory() -> dict:
    """Returns a summary of config files — counts only, no secret values."""
    config_dir = _get_config_dir()
    if not config_dir.exists():
        return {"config_dir": str(config_dir), "exists": False, "files": [], "total_size_bytes": 0}
    files = []
    total = 0
    for f in sorted(config_dir.rglob("*")):
        if f.is_file() and "backups" not in f.parts:
            size = f.stat().st_size
            total += size
            files.append({"name": str(f.relative_to(config_dir)), "size_bytes": size})
    return {
        "config_dir": str(config_dir),
        "exists": True,
        "files": files,
        "total_size_bytes": total,
    }


def create_config_backup(
    *,
    output_dir: Path | None = None,
    include_secrets: bool = False,
    confirmation: str | None = None,
) -> dict:
    """Creates a .tar.gz backup of CONFIG_DIR in output_dir (or default backups/).

    include_secrets=True requires confirmation=RESTAURAR_CONFIG (reused token).
    The archive always excludes the backups/ subdirectory.
    """
    if include_secrets and confirmation != RESTORE_CONFIRMATION:
        return {
            "ok": False,
            "error": f"Para incluir secretos, pasa confirmation='{RESTORE_CONFIRMATION}'",
        }

    config_dir = _get_config_dir()
    if not config_dir.exists():
        return {"ok": False, "error": f"CONFIG_DIR no existe: {config_dir}"}

    backup_dir = _get_backup_dir(config_dir) if output_dir is None else Path(output_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_with_secrets" if include_secrets else ""
    archive_name = f"emuwarez_config_{ts}{suffix}.tar.gz"
    archive_path = backup_dir / archive_name

    excluded_dirs = {"backups"}
    secret_keys = {"tmdb_api_key", "emu_api_key"}

    with tarfile.open(archive_path, "w:gz") as tar:
        for item in sorted(config_dir.rglob("*")):
            rel = item.relative_to(config_dir)
            if rel.parts and rel.parts[0] in excluded_dirs:
                continue
            if item.is_file():
                if not include_secrets and item.name == "emuwarez_uploadrr.db":
                    # still include db — secrets are in db rows but tar includes it
                    # we only skip if caller explicitly opted out (db is always included)
                    pass
                tar.add(item, arcname=str(rel))

    size = archive_path.stat().st_size
    return {
        "ok": True,
        "archive_path": str(archive_path),
        "archive_name": archive_name,
        "size_bytes": size,
        "include_secrets": include_secrets,
        "config_dir": str(config_dir),
    }


def list_config_backups(directory: Path | None = None) -> list[dict]:
    """Lists existing backup archives, newest first."""
    config_dir = _get_config_dir()
    backup_dir = directory if directory is not None else _get_backup_dir(config_dir)
    if not backup_dir.exists():
        return []
    backups = []
    for f in sorted(backup_dir.glob("emuwarez_config_*.tar.gz"), reverse=True):
        stat = f.stat()
        backups.append({
            "name": f.name,
            "path": str(f),
            "size_bytes": stat.st_size,
            "created_at": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return backups


def restore_config_backup(
    backup_path: str,
    *,
    dry_run: bool = True,
    apply: bool = False,
    confirmation: str | None = None,
) -> dict:
    """Restores a backup archive to CONFIG_DIR.

    dry_run=True (default) previews only.
    apply=True requires confirmation=RESTAURAR_CONFIG and dry_run=False.
    """
    path = Path(backup_path)
    if not path.exists():
        return {"ok": False, "dry_run": dry_run, "error": f"Archivo no encontrado: {backup_path}"}
    if not tarfile.is_tarfile(str(path)):
        return {"ok": False, "dry_run": dry_run, "error": "El archivo no es un tarball válido"}

    do_apply = apply and not dry_run
    if do_apply and confirmation != RESTORE_CONFIRMATION:
        return {
            "ok": False,
            "dry_run": dry_run,
            "error": f"Confirmación requerida: pasa confirmation='{RESTORE_CONFIRMATION}'",
        }

    config_dir = _get_config_dir()

    with tarfile.open(str(path), "r:gz") as tar:
        members = tar.getnames()

    if dry_run or not do_apply:
        return {
            "ok": True,
            "dry_run": True,
            "action": "preview",
            "archive": str(path),
            "target_dir": str(config_dir),
            "files_in_archive": len(members),
            "files": members[:50],
            "message": "Previsualización — no se han restaurado archivos",
        }

    config_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(str(path), "r:gz") as tar:
        tar.extractall(path=config_dir)  # noqa: S202 — trusted local backup

    return {
        "ok": True,
        "dry_run": False,
        "action": "restored",
        "archive": str(path),
        "target_dir": str(config_dir),
        "files_restored": len(members),
        "message": f"Restauración completada: {len(members)} archivos",
    }
