"""Instance management for Radarr/Sonarr."""
from __future__ import annotations

import sqlite3
from typing import Optional

from ..integrations import radarr, sonarr
from ..integrations.base import IntegrationError, normalize_base_url
from ..models import InstanceConfig, InstanceType


def add_instance(conn: sqlite3.Connection, instance_type: str, name: str, url: str, api_key: str, enabled: bool = True) -> int:
    instance_type = instance_type.lower().strip()
    if instance_type not in (InstanceType.RADARR.value, InstanceType.SONARR.value):
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
    row = conn.execute("SELECT id FROM instances WHERE type = ? AND name = ?", (instance_type, name.strip())).fetchone()
    return int(row["id"] if row else cur.lastrowid)


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


def test_instance(instance: InstanceConfig) -> dict:
    if instance.type == InstanceType.RADARR.value:
        return radarr.test_connection(instance.url, instance.api_key)
    if instance.type == InstanceType.SONARR.value:
        return sonarr.test_connection(instance.url, instance.api_key)
    raise IntegrationError(f"Tipo de instancia no soportado: {instance.type}")
