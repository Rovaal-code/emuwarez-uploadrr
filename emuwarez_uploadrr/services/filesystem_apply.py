"""Filesystem apply service for nomenclature preparation.

Renames the original file IN PLACE to the Emuwarez nomenclature (same
directory → same filesystem, so it works across SSHFS/NFS mounts). This is
the only sanctioned path that moves/renames a source file.

SAFETY CONTRACT:
- Only allowed filesystem write: os.rename (when dry_run=False).
- Destination must stay in the same directory as the source.
- No path traversal (/../).
- No symlinks as source.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov", ".ts", ".m2ts",
    ".wmv", ".flv", ".webm", ".iso", ".m4v",
}


def resolve_safe_path(path: str) -> str:
    """Resolve path without following symlinks for display."""
    return str(Path(path).resolve())


def ensure_path_under_base(path: str, base: str) -> bool:
    """Return True if path is strictly inside base (no traversal)."""
    try:
        resolved_path = Path(path).resolve()
        resolved_base = Path(base).resolve()
        resolved_path.relative_to(resolved_base)
        return True
    except ValueError:
        return False


def build_safe_rename_plan(source_path: str, destination_path: str) -> dict[str, Any]:
    """Validate an in-place rename of the original file (same directory).
    Never touches the filesystem."""
    errors: list[str] = []
    warnings: list[str] = []

    src = Path(source_path) if source_path else None
    if not source_path:
        errors.append("source_path no proporcionado.")
    elif not src.exists():
        errors.append(f"El archivo origen no existe: {source_path}")
    elif src.is_symlink():
        errors.append("El archivo origen es un symlink. No se permite renombrar symlinks.")
    elif not src.is_file():
        errors.append(f"El origen no es un archivo regular: {source_path}")
    elif src.suffix.lower() not in VIDEO_EXTENSIONS:
        warnings.append(f"El archivo origen no parece un vídeo ({src.suffix}). Continuando con precaución.")

    if not destination_path:
        errors.append("destination_path no proporcionado.")
    elif src is not None and src.exists():
        dst = Path(destination_path)
        # Stay in the same directory as the source: a rename in place is on the
        # same filesystem (no EXDEV), and we never move files between folders.
        if dst.parent.resolve() != src.parent.resolve():
            errors.append("El destino debe estar en la misma carpeta que el origen.")
        if dst.resolve() == src.resolve():
            warnings.append("El archivo ya tiene la nomenclatura correcta; no hay nada que renombrar.")
        elif dst.exists():
            errors.append(f"El destino ya existe: {destination_path}.")
        if not os.access(str(src.parent), os.W_OK):
            errors.append(f"La carpeta del origen no es escribible: {src.parent}")

    status = "blocked" if errors else "ready"
    return {
        "status": status,
        "operation_type": "nomenclature_rename",
        "source_path": source_path,
        "destination_path": destination_path,
        "parent_dir": str(Path(destination_path).parent) if destination_path else None,
        "errors": errors,
        "warnings": warnings,
    }


def apply_rename_plan(plan: dict[str, Any], *, dry_run: bool = True) -> dict[str, Any]:
    """Execute or simulate the in-place rename. Only os.rename is allowed."""
    result = dict(plan)
    now = datetime.now(timezone.utc).isoformat()
    result["dry_run"] = dry_run
    result["applied_at"] = None

    src = plan.get("source_path")
    dst = plan.get("destination_path")

    # Nothing to do when the file already matches (a warning, not an error).
    if src and dst and Path(src).exists() and Path(dst).exists() and Path(src).resolve() == Path(dst).resolve():
        result["status"] = "applied"
        result["applied_at"] = now
        result["message"] = "El archivo ya tiene la nomenclatura correcta."
        return result

    if plan["status"] == "blocked":
        result["message"] = "Plan bloqueado. Ver errors para más detalles."
        return result

    if dry_run:
        result["status"] = "ready"
        result["message"] = f"Dry-run: se renombraría '{src}' → '{dst}'. No se ha escrito nada."
        return result

    try:
        if Path(dst).exists():
            result["status"] = "blocked"
            result["errors"] = list(plan.get("errors", [])) + [f"El destino ya existe: {dst}."]
            result["message"] = "Renombrado bloqueado: el destino ya existe."
            return result
        os.rename(src, dst)
        result["status"] = "applied"
        result["applied_at"] = now
        result["message"] = f"Archivo renombrado correctamente: '{dst}'."
    except OSError as exc:
        result["status"] = "failed"
        result["errors"] = list(plan.get("errors", [])) + [f"Error de sistema: {exc}"]
        result["message"] = f"Falló el renombrado: {exc}"

    return result
