"""Library synchronization and querying."""
from __future__ import annotations

import sqlite3
from typing import Iterable, Optional

from ..integrations import radarr, sonarr
from ..models import InstanceConfig, LibraryItem, LocalStatus, NomenclatureStatus
from .instances import list_instances
from .tasks import start_task, finish_task


def upsert_library_item(conn: sqlite3.Connection, item: LibraryItem) -> int:
    data = item.to_dict()
    columns = [
        "item_type", "title", "year", "original_title", "instance_id", "instance_type",
        "instance_name", "external_id", "tmdb_id", "imdb_id", "tvdb_id", "path",
        "quality", "resolution", "source", "size_bytes", "local_status",
        "request_status", "nomenclature_status", "request_id", "added_at", "raw_json",
    ]
    values = [data.get(col) for col in columns]
    conn.execute(
        f"""
        INSERT INTO library_items({', '.join(columns)}, updated_at)
        VALUES ({', '.join(['?'] * len(columns))}, CURRENT_TIMESTAMP)
        ON CONFLICT(instance_id, item_type, external_id) DO UPDATE SET
            title = excluded.title,
            year = excluded.year,
            original_title = excluded.original_title,
            instance_type = excluded.instance_type,
            instance_name = excluded.instance_name,
            tmdb_id = excluded.tmdb_id,
            imdb_id = excluded.imdb_id,
            tvdb_id = excluded.tvdb_id,
            path = excluded.path,
            quality = excluded.quality,
            resolution = excluded.resolution,
            source = excluded.source,
            size_bytes = excluded.size_bytes,
            local_status = excluded.local_status,
            nomenclature_status = excluded.nomenclature_status,
            raw_json = excluded.raw_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        values,
    )
    row = conn.execute(
        "SELECT id FROM library_items WHERE instance_id = ? AND item_type = ? AND external_id = ?",
        (item.instance_id, item.item_type, item.external_id),
    ).fetchone()
    conn.commit()
    return int(row["id"])


def sync_instance(conn: sqlite3.Connection, instance: InstanceConfig, *, include_episodes: bool = False) -> tuple[int, int]:
    imported = 0
    missing = 0
    if instance.type == "radarr":
        for movie in radarr.get_movies(instance.url, instance.api_key):
            item = radarr.movie_to_library_item(movie, instance_id=int(instance.id), instance_name=instance.name)
            upsert_library_item(conn, item)
            imported += 1
            if item.local_status == LocalStatus.MISSING.value:
                missing += 1
    elif instance.type == "sonarr":
        for series in sonarr.get_series(instance.url, instance.api_key):
            series_item = sonarr.series_to_library_item(series, instance_id=int(instance.id), instance_name=instance.name)
            upsert_library_item(conn, series_item)
            imported += 1
            if series_item.local_status == LocalStatus.MISSING.value:
                missing += 1
            if include_episodes and series.get("id"):
                files = sonarr.get_episode_files(instance.url, instance.api_key, int(series["id"]))
                files_by_id = {f.get("id"): f for f in files if f.get("id") is not None}
                for episode in sonarr.get_episodes(instance.url, instance.api_key, int(series["id"])):
                    ep_file = files_by_id.get(episode.get("episodeFileId")) if episode.get("episodeFileId") else None
                    ep_item = sonarr.episode_to_library_item(
                        episode,
                        ep_file,
                        series,
                        instance_id=int(instance.id),
                        instance_name=instance.name,
                    )
                    upsert_library_item(conn, ep_item)
                    imported += 1
                    if ep_item.local_status == LocalStatus.MISSING.value:
                        missing += 1
    return imported, missing


def sync_all(conn: sqlite3.Connection, *, include_episodes: bool = False) -> dict[str, int]:
    task_id = start_task(conn, "sync-library", "Sincronizando Radarr/Sonarr")
    total = 0
    missing = 0
    details: list[str] = []
    try:
        for instance in list_instances(conn, enabled_only=True):
            imported, miss = sync_instance(conn, instance, include_episodes=include_episodes)
            total += imported
            missing += miss
            details.append(f"{instance.type}:{instance.name}: {imported} importados, {miss} faltantes")
        summary = f"{total} elementos sincronizados; {missing} faltantes"
        finish_task(conn, task_id, "completed", summary, "\n".join(details))
        return {"imported": total, "missing": missing, "instances": len(details)}
    except Exception as exc:
        finish_task(conn, task_id, "failed", str(exc), "\n".join(details))
        raise


def list_library(
    conn: sqlite3.Connection,
    *,
    status: Optional[str] = None,
    request: Optional[str] = None,
    nomenclature: Optional[str] = None,
    item_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    where = []
    params: list = []
    if status:
        where.append("local_status = ?")
        params.append(status)
    if request:
        where.append("request_status = ?")
        params.append(request)
    if nomenclature:
        where.append("nomenclature_status = ?")
        params.append(nomenclature)
    if item_type:
        where.append("item_type = ?")
        params.append(item_type)
    if search:
        where.append("title LIKE ?")
        params.append(f"%{search}%")
    sql = "SELECT * FROM library_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC, title COLLATE NOCASE LIMIT ?"
    params.append(limit)
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def get_library_item(conn: sqlite3.Connection, item_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def list_missing(conn: sqlite3.Connection, *, limit: int = 50) -> list[dict]:
    return list_library(conn, status=LocalStatus.MISSING.value, limit=limit)


def update_request_status(conn: sqlite3.Connection, library_item_id: int, request_status: str, request_id: Optional[int] = None) -> None:
    conn.execute(
        "UPDATE library_items SET request_status = ?, request_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (request_status, request_id, library_item_id),
    )
    conn.commit()


def mark_nomenclature(conn: sqlite3.Connection, library_item_id: int, status: str) -> None:
    conn.execute(
        "UPDATE library_items SET nomenclature_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, library_item_id),
    )
    conn.commit()
