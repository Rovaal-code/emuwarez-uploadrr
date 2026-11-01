"""Instance management for Radarr/Sonarr."""
from __future__ import annotations

import sqlite3
from typing import Optional

from ..database import borrar_biblioteca
from ..integrations import radarr, sonarr
from ..integrations.arr_base import safe_api_key
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
    *,
    test_connection: bool = False,
) -> int:
    """Instance names are globally unique (not just per type, see the
    _migrate_instances_unique_name migration) — a name already in use by
    *any* instance, regardless of type, is now a real rejection (400),
    not a silent upsert. The old ON CONFLICT(type, name) DO UPDATE
    behavior predates that constraint and would silently overwrite an
    unrelated instance's URL/key if two different types shared a name.

    When ``test_connection`` is set (the web create flow does), the *arr
    connection is verified *after* the cheap type/name/URL validation but
    *before* the insert — so a duplicate name still reports the name error
    (not a connection error), and a well-formed but unreachable/unauthorized
    instance is never persisted."""
    instance_type = instance_type.lower().strip()
    if instance_type not in _VALID_INSTANCE_TYPES:
        raise ValueError("Tipo de instancia inválido. Usa radarr o sonarr.")
    name = name.strip()
    existing = conn.execute("SELECT id FROM instances WHERE name = ?", (name,)).fetchone()
    if existing:
        raise ValueError(f"Ya existe una instancia con el nombre '{name}'.")
    url = normalize_base_url(url)
    if test_connection:
        result = test_connection_params(instance_type, url, api_key, name)
        if not result.get("ok"):
            raise ValueError(
                f"No se pudo conectar con la instancia {instance_type}: "
                f"{result.get('error') or 'error desconocido'}"
            )
    cur = conn.execute(
        """
        INSERT INTO instances(type, name, url, api_key, enabled)
        VALUES (?, ?, ?, ?, ?)
        """,
        (instance_type, name, url, api_key.strip(), 1 if enabled else 0),
    )
    conn.commit()
    return int(cur.lastrowid)


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
        name = name.strip()
        conflict = conn.execute(
            "SELECT id FROM instances WHERE name = ? AND id != ?", (name, instance_id)
        ).fetchone()
        if conflict:
            raise ValueError(f"Ya existe una instancia con el nombre '{name}'.")
        sets.append("name = ?")
        params.append(name)
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
    if name is not None:
        # La biblioteca guarda el nombre de la instancia en cada ficha; si no, hasta la próxima sincronización
        # (días, con la instancia apagada) la interfaz sigue enseñando el viejo.
        conn.execute("UPDATE library_items SET instance_name = ? WHERE instance_id = ?", (name, instance_id))
    conn.commit()
    return cur.rowcount > 0


AVISO_SIN_RESPUESTA = (
    "Guardado, pero la instancia no responde: no se ha podido comprobar que sea el mismo servidor. "
    "Si apunta a otro, sincronizar mezclará elementos."
)


def aviso_si_cambia_el_destino(instance: InstanceConfig, *, url: Optional[str], api_key: Optional[str]) -> Optional[str]:
    """Con otra URL o clave, prueba la nueva: si no responde devuelve el aviso (se guarda igual, hay instancias apagadas
    días). Las fichas se casan por su id de Radarr/Sonarr, así que si apunta a otro servidor la sincronización las mezcla."""
    nueva_url = normalize_base_url(url) if url is not None else instance.url
    nueva_clave = api_key.strip() if api_key is not None else instance.api_key
    if (nueva_url, nueva_clave) == (instance.url, instance.api_key):
        return None
    if test_connection_params(instance.type, nueva_url, nueva_clave, instance.name).get("ok"):
        return None
    return AVISO_SIN_RESPUESTA


def remove_instance(conn: sqlite3.Connection, instance_id: int) -> bool:
    """Borra la instancia con lo que se sincronizó de ella: ninguna sincronización lo iba a quitar después. Nunca a la
    vez que una sincronización de biblioteca (lanza SyncAlreadyRunning): la que fuera por ella volvería a escribirlo."""
    from .library import _sin_sincronizar, volver_a_cruzar_peticiones
    with _sin_sincronizar():
        _, peticiones = borrar_biblioteca(conn, "instance_id = ?", (instance_id,))
        cur = conn.execute("DELETE FROM instances WHERE id = ?", (instance_id,))
        conn.commit()
    volver_a_cruzar_peticiones(conn, peticiones)
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


def test_connection_params(instance_type: str, url: str, api_key: str, name: str = "") -> dict:
    """Test connectivity for not-yet-persisted instance params (create flow).
    Returns a structured result {ok, version?, error?} — never raises, never
    leaks the raw api_key."""
    instance_type = (instance_type or "").lower().strip()
    inst_dict = {"url": normalize_base_url(url), "api_key": (api_key or "").strip(), "name": name}
    try:
        if instance_type == InstanceType.RADARR.value:
            return radarr.radarr_test_connection(inst_dict)
        if instance_type == InstanceType.SONARR.value:
            return sonarr.sonarr_test_connection(inst_dict)
        return {"ok": False, "error": f"Tipo desconocido: {instance_type}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


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


def list_instance_rows(conn) -> list[dict]:
    """Todas las instancias, ordenadas como las enseña la interfaz."""
    return [dict(r) for r in conn.execute("SELECT * FROM instances ORDER BY type, name")]


def get_instance_row(instance_id: int, conn) -> dict | None:
    row = conn.execute("SELECT * FROM instances WHERE id = ?", (instance_id,)).fetchone()
    return dict(row) if row else None


def set_instance_flags(instance_id: int, *, is_4k: bool, is_anime: bool, conn) -> None:
    """Las dos banderas que distinguen una instancia 4K o de anime."""
    conn.execute(
        "UPDATE instances SET is_4k=?, is_anime=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (int(is_4k), int(is_anime), instance_id),
    )
    conn.commit()
