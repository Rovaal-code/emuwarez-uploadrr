"""Library synchronization and querying."""
from __future__ import annotations

import sqlite3
from typing import Optional

from ..integrations import radarr, sonarr
from ..models import InstanceConfig, LibraryItem, LocalStatus, NomenclatureStatus
from .instances import list_instances
from .tasks import start_task, finish_task


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def upsert_library_item(conn: sqlite3.Connection, item: LibraryItem) -> int:
    data = item.to_dict()
    columns = [
        "item_type", "title", "year", "original_title", "instance_id", "instance_type",
        "instance_name", "external_id", "tmdb_id", "imdb_id", "tvdb_id", "path",
        "quality", "resolution", "source", "size_bytes", "local_status",
        "request_status", "nomenclature_status", "request_id", "added_at", "raw_json",
        "poster_url",
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
            poster_url = excluded.poster_url,
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


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def sync_instance(
    conn: sqlite3.Connection,
    instance: InstanceConfig,
    *,
    include_episodes: bool = False,
) -> tuple[int, int]:
    imported = 0
    missing = 0
    if instance.type == "radarr":
        queue_records = radarr.get_queue(instance.url, instance.api_key)
        queue_map = radarr.build_queue_map(queue_records)
        for movie in radarr.get_movies(instance.url, instance.api_key):
            item = radarr.movie_to_library_item(
                movie,
                instance_id=int(instance.id),
                instance_name=instance.name,
                queue_map=queue_map,
            )
            upsert_library_item(conn, item)
            imported += 1
            if item.local_status != LocalStatus.AVAILABLE.value:
                missing += 1

    elif instance.type == "sonarr":
        queue_records = sonarr.get_queue(instance.url, instance.api_key)
        series_queue = sonarr.build_series_queue_map(queue_records)
        ep_queue = sonarr.build_episode_queue_map(queue_records)
        for series in sonarr.get_series(instance.url, instance.api_key):
            series_item = sonarr.series_to_library_item(
                series,
                instance_id=int(instance.id),
                instance_name=instance.name,
                series_queue_map=series_queue,
            )
            upsert_library_item(conn, series_item)
            imported += 1
            if series_item.local_status != LocalStatus.AVAILABLE.value:
                missing += 1
            if include_episodes and series.get("id"):
                files = sonarr.get_episode_files(instance.url, instance.api_key, int(series["id"]))
                files_by_id = {f.get("id"): f for f in files if f.get("id") is not None}
                for episode in sonarr.get_episodes(instance.url, instance.api_key, int(series["id"])):
                    ep_file = (
                        files_by_id.get(episode.get("episodeFileId"))
                        if episode.get("episodeFileId")
                        else None
                    )
                    ep_item = sonarr.episode_to_library_item(
                        episode,
                        ep_file,
                        series,
                        instance_id=int(instance.id),
                        instance_name=instance.name,
                        ep_queue_map=ep_queue,
                    )
                    upsert_library_item(conn, ep_item)
                    imported += 1
                    if ep_item.local_status != LocalStatus.AVAILABLE.value:
                        missing += 1
    return imported, missing


def sync_all(conn: sqlite3.Connection, *, include_episodes: bool = False) -> dict:
    task_id = start_task(conn, "sync-library", "Sincronizando Radarr/Sonarr")
    total = 0
    missing = 0
    details: list[str] = []
    errors: list[str] = []
    try:
        for instance in list_instances(conn, enabled_only=True):
            try:
                imported, miss = sync_instance(conn, instance, include_episodes=include_episodes)
                total += imported
                missing += miss
                details.append(f"{instance.type}:{instance.name}: {imported} importados, {miss} faltantes")
            except Exception as exc:
                err = f"{instance.type}:{instance.name}: {exc}"
                errors.append(err)
                details.append(f"ERROR — {err}")
        summary = f"{total} elementos sincronizados; {missing} no disponibles"
        finish_task(conn, task_id, "completed", summary, "\n".join(details))
        return {"imported": total, "missing": missing, "instances": len(list_instances(conn)), "errors": errors}
    except Exception as exc:
        finish_task(conn, task_id, "failed", str(exc), "\n".join(details))
        raise


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

_MISSING_STATUSES = LocalStatus.not_available()


def list_library(
    conn: sqlite3.Connection,
    *,
    status: Optional[str] = None,
    request: Optional[str] = None,
    nomenclature: Optional[str] = None,
    item_type: Optional[str] = None,
    origin: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
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
    if origin:
        where.append("instance_type = ?")
        params.append(origin)
    if search:
        where.append("title LIKE ?")
        params.append(f"%{search}%")
    sql = "SELECT * FROM library_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC, title COLLATE NOCASE LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def count_library(
    conn: sqlite3.Connection,
    *,
    status: Optional[str] = None,
    item_type: Optional[str] = None,
    search: Optional[str] = None,
) -> int:
    where = []
    params: list = []
    if status:
        where.append("local_status = ?")
        params.append(status)
    if item_type:
        where.append("item_type = ?")
        params.append(item_type)
    if search:
        where.append("title LIKE ?")
        params.append(f"%{search}%")
    sql = "SELECT COUNT(*) FROM library_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def get_library_item(conn: sqlite3.Connection, item_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def list_missing(conn: sqlite3.Connection, *, limit: int = 50, offset: int = 0) -> list[dict]:
    placeholders = ", ".join(["?"] * len(_MISSING_STATUSES))
    sql = (
        f"SELECT * FROM library_items WHERE local_status IN ({placeholders})"
        " ORDER BY updated_at DESC, title COLLATE NOCASE LIMIT ? OFFSET ?"
    )
    rows = conn.execute(sql, [*_MISSING_STATUSES, limit, offset]).fetchall()
    return [dict(row) for row in rows]


def get_dashboard_summary(conn: sqlite3.Connection) -> dict:
    """Return aggregated counts from library_items."""
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN local_status = ? THEN 1 ELSE 0 END) AS available,
            SUM(CASE WHEN local_status IN ({missing_ph}) THEN 1 ELSE 0 END) AS missing_count,
            SUM(CASE WHEN local_status = ? THEN 1 ELSE 0 END) AS uploading,
            SUM(CASE WHEN local_status = ? THEN 1 ELSE 0 END) AS uploaded,
            SUM(CASE WHEN instance_type = 'radarr' THEN 1 ELSE 0 END) AS radarr_items,
            SUM(CASE WHEN instance_type = 'sonarr' THEN 1 ELSE 0 END) AS sonarr_items
        FROM library_items
        """.format(missing_ph=", ".join(["?"] * len(_MISSING_STATUSES))),
        [
            LocalStatus.AVAILABLE.value,
            *_MISSING_STATUSES,
            LocalStatus.UPLOADING.value,
            LocalStatus.UPLOADED.value,
        ],
    ).fetchone()

    last_sync = conn.execute(
        "SELECT started_at FROM task_runs WHERE name = 'sync-library' AND status = 'completed' ORDER BY id DESC LIMIT 1"
    ).fetchone()

    return {
        "library_total": int(row["total"] or 0),
        "available": int(row["available"] or 0),
        "missing": int(row["missing_count"] or 0),
        "uploading": int(row["uploading"] or 0),
        "completed": int(row["uploaded"] or 0),
        "radarr_items": int(row["radarr_items"] or 0),
        "sonarr_items": int(row["sonarr_items"] or 0),
        "last_sync_at": last_sync["started_at"] if last_sync else None,
    }


def get_dashboard_diagnostics(conn: sqlite3.Connection) -> dict:
    """Return Phase 8A diagnostic counts for the dashboard."""
    try:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN file_exists = 1 THEN 1 ELSE 0 END) AS files_verified,
                SUM(CASE WHEN local_status = 'Disponible' AND file_exists = 0 AND file_verified_at IS NOT NULL THEN 1 ELSE 0 END) AS files_missing_on_disk,
                SUM(CASE WHEN recommended_action = 'adapt_nomenclature' THEN 1 ELSE 0 END) AS items_ready_for_nomenclature,
                SUM(CASE WHEN recommended_action IN ('upload', 'run_preflight') THEN 1 ELSE 0 END) AS items_ready_for_upload,
                SUM(CASE WHEN arr_queue_status IN ('downloading', 'queued') THEN 1 ELSE 0 END) AS items_waiting_download,
                SUM(CASE WHEN recommended_action = 'review_arr' THEN 1 ELSE 0 END) AS items_need_arr_review
            FROM library_items
            """
        ).fetchone()
        if row:
            return {
                "files_verified": int(row["files_verified"] or 0),
                "files_missing_on_disk": int(row["files_missing_on_disk"] or 0),
                "items_ready_for_nomenclature": int(row["items_ready_for_nomenclature"] or 0),
                "items_ready_for_upload": int(row["items_ready_for_upload"] or 0),
                "items_waiting_download": int(row["items_waiting_download"] or 0),
                "items_need_arr_review": int(row["items_need_arr_review"] or 0),
            }
    except Exception:
        pass
    return {
        "files_verified": 0,
        "files_missing_on_disk": 0,
        "items_ready_for_nomenclature": 0,
        "items_ready_for_upload": 0,
        "items_waiting_download": 0,
        "items_need_arr_review": 0,
    }


def get_recent_activity(conn: sqlite3.Connection, *, limit: int = 20) -> list[dict]:
    """Return recent task_runs as activity feed."""
    rows = conn.execute(
        "SELECT * FROM task_runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(row) for row in rows]


def update_request_status(
    conn: sqlite3.Connection,
    library_item_id: int,
    request_status: str,
    request_id: Optional[int] = None,
) -> None:
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
