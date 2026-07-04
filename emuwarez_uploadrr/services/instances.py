"""Instance management for Radarr/Sonarr."""
from __future__ import annotations

import sqlite3
from typing import Optional

from ..integrations import radarr, sonarr
from ..integrations.arr_base import ArrClientError, safe_api_key
from ..integrations.base import IntegrationError, normalize_base_url
from ..models import InstanceConfig, InstanceType

_VALID_INSTANCE_TYPES = (InstanceType.RADARR.value, InstanceType.SONARR.value)


def add_instance(
    conn: sqlite3.Connection,
    instance_type: str,
    name: str,
    url: str,
    api_key: str,
    enabled: bool = True,
) -> int:
    instance_type = instance_type.lower().strip()
    if instance_type not in _VALID_INSTANCE_TYPES:
        raise ValueError("Tipo de instancia inválido. Usa radarr o sonarr.")
    url = normalize_base_url(url)
    cur = conn.execute(
        """
        INSERT INTO instances(type, name, url, api_key, enabled)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(type, name) DO UPDATE SET
            url = excluded.url,
            api_key = excluded.api_key,
            enabled = excluded.enabled,
            updated_at = CURRENT_TIMESTAMP
        """,
        (instance_type, name.strip(), url, api_key.strip(), 1 if enabled else 0),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM instances WHERE type = ? AND name = ?",
        (instance_type, name.strip()),
    ).fetchone()
    return int(row["id"] if row else cur.lastrowid)


def update_instance(
    conn: sqlite3.Connection,
    instance_id: int,
    *,
    url: Optional[str] = None,
    api_key: Optional[str] = None,
    name: Optional[str] = None,
    enabled: Optional[bool] = None,
    is_4k: Optional[bool] = None,
    is_anime: Optional[bool] = None,
) -> bool:
    sets = []
    params = []
    if url is not None:
        sets.append("url = ?")
        params.append(normalize_base_url(url))
    if api_key is not None:
        sets.append("api_key = ?")
        params.append(api_key.strip())
    if name is not None:
        sets.append("name = ?")
        params.append(name.strip())
    if enabled is not None:
        sets.append("enabled = ?")
        params.append(1 if enabled else 0)
    if is_4k is not None:
        sets.append("is_4k = ?")
        params.append(1 if is_4k else 0)
    if is_anime is not None:
        sets.append("is_anime = ?")
        params.append(1 if is_anime else 0)
    if not sets:
        return False
    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(instance_id)
    cur = conn.execute(
        f"UPDATE instances SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    conn.commit()
    return cur.rowcount > 0


def remove_instance(conn: sqlite3.Connection, instance_id: int) -> bool:
    cur = conn.execute("DELETE FROM instances WHERE id = ?", (instance_id,))
    conn.commit()
    return cur.rowcount > 0


def get_instance(conn: sqlite3.Connection, instance_id: int) -> Optional[InstanceConfig]:
    row = conn.execute("SELECT * FROM instances WHERE id = ?", (instance_id,)).fetchone()
    return row_to_instance(row) if row else None


def list_instances(conn: sqlite3.Connection, enabled_only: bool = False) -> list[InstanceConfig]:
    sql = "SELECT * FROM instances"
    params: tuple = ()
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY type, name"
    rows = conn.execute(sql, params).fetchall()
    return [row_to_instance(row) for row in rows]


def row_to_instance(row) -> InstanceConfig:
    return InstanceConfig(
        id=int(row["id"]),
        type=row["type"],
        name=row["name"],
        url=row["url"],
        api_key=row["api_key"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def instance_to_dict_safe(instance: InstanceConfig) -> dict:
    """Return instance as dict with API key masked (safe for API responses)."""
    return {
        "id": instance.id,
        "type": instance.type,
        "name": instance.name,
        "url": instance.url,
        "api_key_masked": safe_api_key(instance.api_key),
        "enabled": instance.enabled,
        "created_at": instance.created_at,
        "updated_at": instance.updated_at,
    }


def test_instance(instance: InstanceConfig) -> dict:
    if instance.type == InstanceType.RADARR.value:
        return radarr.test_connection(instance.url, instance.api_key)
    if instance.type == InstanceType.SONARR.value:
        return sonarr.test_connection(instance.url, instance.api_key)
    raise IntegrationError(f"Tipo de instancia no soportado: {instance.type}")


def test_instance_safe(instance: InstanceConfig) -> dict:
    """Run connection test, return structured result (no raw api_key in output)."""
    inst_dict = {"url": instance.url, "api_key": instance.api_key, "name": instance.name}
    try:
        if instance.type == InstanceType.RADARR.value:
            result = radarr.radarr_test_connection(inst_dict)
        elif instance.type == InstanceType.SONARR.value:
            result = sonarr.sonarr_test_connection(inst_dict)
        else:
            result = {"ok": False, "error": f"Tipo desconocido: {instance.type}"}
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    return {**result, "instance_id": instance.id, "instance_name": instance.name}


def mark_instance_test_result(conn: sqlite3.Connection, instance_id: int, ok: bool, error: Optional[str] = None) -> None:
    """Update last_test_status and last_test_at in instances table."""
    status = "ok" if ok else f"error: {error or 'unknown'}"[:100]
    conn.execute(
        """
        UPDATE instances
        SET last_test_status = ?, last_test_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, instance_id),
    )
    conn.commit()
