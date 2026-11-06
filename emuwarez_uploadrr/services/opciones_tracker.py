"""Anónimo y Personal release de una subida a eMuwarez.

En Configuración, cada grupo de subida (el tag tras el último «-» del nombre) se puede marcar como Personal release,
como anónimo o las dos cosas. Una subida con ese grupo lleva la marca sin que nadie la toque: también las de un lote o
las automáticas. En el Resumen del asistente las dos casillas salen con lo que diga el grupo y se pueden cambiar
para esa subida; lo elegido a mano se guarda en el trabajo (`upload_jobs.anonimo` / `personal_release`, NULL = lo
que diga el grupo) y gana a la regla.

Llega a Uploadrr-EMU como `-a` / `-pr` (uploadrr_contract.build_uploadrr_emu_command), que el tracker UNIT3D manda
como `anonymous` / `personal_release`.

Ajustes (JSON con la lista de grupos):
- upload.tags_personal_release
- upload.tags_anonimos
"""
from __future__ import annotations

import json
import sqlite3
from typing import Iterable, Optional

from .settings import get_setting_canonical, set_setting

CLAVE_PERSONAL_RELEASE = "upload.tags_personal_release"
CLAVE_ANONIMOS = "upload.tags_anonimos"


def _leer_lista(conn: sqlite3.Connection, clave: str) -> list[str]:
    try:
        valor = json.loads(get_setting_canonical(conn, clave) or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(valor, list):
        return []
    return limpiar_grupos(valor)


def limpiar_grupos(grupos: Iterable) -> list[str]:
    """Sin vacíos ni repetidos (sin distinguir mayúsculas), en el orden dado."""
    vistos: set[str] = set()
    salida: list[str] = []
    for g in grupos or []:
        texto = str(g or "").strip()
        if texto and texto.casefold() not in vistos:
            vistos.add(texto.casefold())
            salida.append(texto)
    return salida


def grupos_personal_release(conn: sqlite3.Connection) -> list[str]:
    return _leer_lista(conn, CLAVE_PERSONAL_RELEASE)


def grupos_anonimos(conn: sqlite3.Connection) -> list[str]:
    return _leer_lista(conn, CLAVE_ANONIMOS)


def guardar_grupos(
    conn: sqlite3.Connection, *, personal_release: Optional[Iterable] = None, anonimos: Optional[Iterable] = None,
) -> None:
    """None deja la lista como está."""
    if personal_release is not None:
        set_setting(conn, CLAVE_PERSONAL_RELEASE, json.dumps(limpiar_grupos(personal_release), ensure_ascii=False))
    if anonimos is not None:
        set_setting(conn, CLAVE_ANONIMOS, json.dumps(limpiar_grupos(anonimos), ensure_ascii=False))


def _en(grupo: Optional[str], lista: list[str]) -> bool:
    texto = (grupo or "").strip().casefold()
    return bool(texto) and any(texto == g.casefold() for g in lista)


def opciones_de_subida(
    conn: sqlite3.Connection, grupo: Optional[str], *,
    anonimo: Optional[bool] = None, personal_release: Optional[bool] = None,
) -> dict[str, bool]:
    """{"anon", "personal_release"} de una subida con el grupo `grupo`. `anonimo` / `personal_release` son lo
    elegido a mano en el asistente (None: lo que diga el grupo)."""
    return {
        "anon": bool(anonimo) if anonimo is not None else _en(grupo, grupos_anonimos(conn)),
        "personal_release": (bool(personal_release) if personal_release is not None
                             else _en(grupo, grupos_personal_release(conn))),
    }


__all__ = [
    "CLAVE_PERSONAL_RELEASE", "CLAVE_ANONIMOS", "limpiar_grupos", "grupos_personal_release", "grupos_anonimos",
    "guardar_grupos", "opciones_de_subida",
]
