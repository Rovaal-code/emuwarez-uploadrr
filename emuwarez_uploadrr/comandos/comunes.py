"""Ayudas compartidas por los comandos: tabla, traducción de filtros y conexión."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..database import connect, init_db
from ..models import LocalStatus, NomenclatureStatus, RequestStatus
from ..services import library as library_service


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
        "partial": LocalStatus.PARTIAL.value,
        "parcial": LocalStatus.PARTIAL.value,
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
