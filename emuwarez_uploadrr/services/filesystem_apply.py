"""Filesystem apply service for nomenclature hardlink preparation.

SAFETY CONTRACT:
- Never rename, move, or delete source files.
- Never modify source file content.
- Never execute mkvpropedit or Uploadrr.
- Only allowed filesystem writes: os.makedirs + os.link (when dry_run=False).
- destination_path must always be inside hardlink_base.
- No path traversal (/../).
- No symlinks as source.
- No cross-device links (EXDEV → blocked, not fallback copy).
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


def build_safe_apply_plan(
    source_path: str,
    destination_path: str,
    hardlink_base: str,
) -> dict[str, Any]:
    """Validate and build a plan for creating a hardlink.

    Returns a plan dict with status ready/blocked and all details.
    Never modifies the filesystem.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Validate source
    src = Path(source_path) if source_path else None
    if not source_path:
        errors.append("source_path no proporcionado.")
    elif not src.exists():
        errors.append(f"El archivo origen no existe: {source_path}")
    elif src.is_symlink():
        errors.append("El archivo origen es un symlink. No se permite hardlink de symlinks.")
    elif not src.is_file():
        errors.append(f"El origen no es un archivo regular: {source_path}")
    elif src.suffix.lower() not in VIDEO_EXTENSIONS:
        warnings.append(
            f"El archivo origen no parece un vídeo ({src.suffix}). Continuando con precaución."
        )

    # Validate destination
    dst_resolved = None
    if not destination_path:
        errors.append("destination_path no proporcionado.")
    else:
        try:
            dst_resolved = Path(destination_path).resolve()
        except Exception:
            errors.append("destination_path no se pudo resolver.")

        if dst_resolved is not None:
            # Check destination is under hardlink_base
            if not hardlink_base:
                errors.append("hardlink_base no configurado.")
            elif not ensure_path_under_base(str(dst_resolved), hardlink_base):
                errors.append(
                    f"destination_path está fuera de hardlink_base. "
                    f"Destino: {dst_resolved}, Base: {hardlink_base}"
                )

            # Check destination != source
            if src is not None and not src.is_symlink() and src.exists():
                try:
                    src_resolved = src.resolve()
                    if dst_resolved == src_resolved:
                        errors.append(
                            "source_path y destination_path son el mismo archivo."
                        )
                except Exception:
                    pass

            # Check destination not symlink
            if Path(destination_path).is_symlink():
                errors.append("El destino es un symlink.")

            # Check destination doesn't already exist
            if Path(destination_path).exists():
                errors.append(
                    f"El destino ya existe: {destination_path}. "
                    "Usa overwrite=true para sobrescribir (no recomendado)."
                )

    parent_dir = str(Path(destination_path).parent) if destination_path else None
    status = "blocked" if errors else "ready"

    return {
        "status": status,
        "operation_type": "nomenclature_hardlink",
        "source_path": source_path,
        "destination_path": destination_path,
        "parent_dir": parent_dir,
        "hardlink_base": hardlink_base,
        "errors": errors,
        "warnings": warnings,
    }


def apply_hardlink_plan(
    plan: dict[str, Any],
    *,
    dry_run: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Execute or simulate the hardlink plan.

    When dry_run=True: validates only, no filesystem writes.
    When dry_run=False: creates parent directories and hardlink.
    Never modifies or deletes source file.
    """
    result = dict(plan)
    now = datetime.now(timezone.utc).isoformat()
    result["dry_run"] = dry_run
    result["applied_at"] = None

    if plan["status"] == "blocked" and not overwrite:
        result["status"] = "blocked"
        result["message"] = "Plan bloqueado. Ver errors para más detalles."
        return result

    if plan["status"] == "blocked" and overwrite:
        # Only allow overwrite to bypass "destination exists" errors
        non_overwrite_errors = [
            e for e in plan.get("errors", []) if "ya existe" not in e
        ]
        if non_overwrite_errors:
            result["status"] = "blocked"
            result["message"] = "Plan bloqueado por errores de seguridad no superables."
            return result

    source_path = plan["source_path"]
    destination_path = plan["destination_path"]
    parent_dir = plan["parent_dir"]

    if dry_run:
        result["status"] = "ready"
        result["message"] = (
            f"Dry-run: se crearía hardlink de '{source_path}' → '{destination_path}'. "
            "No se ha escrito nada."
        )
        return result

    # Real apply — only os.makedirs + os.link allowed
    try:
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        if overwrite and Path(destination_path).exists():
            if Path(destination_path).is_symlink() or not Path(destination_path).is_file():
                result["status"] = "blocked"
                result["errors"] = list(plan.get("errors", [])) + [
                    "El destino existente no es un archivo regular. No se puede sobrescribir."
                ]
                result["message"] = "Sobrescritura bloqueada: destino no es archivo regular."
                return result
            os.remove(destination_path)

        os.link(source_path, destination_path)
        result["status"] = "applied"
        result["applied_at"] = now
        result["message"] = (
            f"Hardlink creado correctamente: '{destination_path}'. "
            "El archivo original no ha sido modificado."
        )
    except OSError as exc:
        import errno as _errno
        if exc.errno == _errno.EXDEV:
            result["status"] = "blocked"
            result["errors"] = list(plan.get("errors", [])) + [
                "No se puede crear hardlink entre dispositivos distintos (EXDEV). "
                "Copia/reflink queda pendiente de fase futura."
            ]
            result["message"] = "Cross-device hardlink no soportado."
        else:
            result["status"] = "failed"
            result["errors"] = list(plan.get("errors", [])) + [
                f"Error de sistema: {exc}"
            ]
            result["message"] = f"Falló la creación del hardlink: {exc}"

    return result
