"""Registro de una subida: logs (con aviso push) y artefactos."""
from __future__ import annotations

import json

from ...database import rows_to_dicts
from ..eventos import EVENTO_SUBIDA_LOG, publicar_agrupado
from ..upload_result_parser import extract_torrent_url, torrent_id_from_url
from .comun import QBIT_AÑADIDO, _get_db_conn, _now


def _avisar_de_log(job_id: int) -> None:
    """Avisa de que hay líneas nuevas, como mucho una vez por segundo.

    El aviso NO lleva las líneas. El proceso escupe cientos por segundo y
    mandarlas por el canal lo convertiría en una tubería de logs; además solo
    le importan a quien tenga abierta esa pantalla concreta. Así que solo se
    dice que las hay, y quien mire las pide.

    Agrupar aquí es seguro porque el aviso no lleva estado: el que sí sale trae
    consigo todo lo que se perdieron los que no salieron.
    """
    publicar_agrupado(f"log-{job_id}", EVENTO_SUBIDA_LOG, {"job_id": job_id}, cada=1.0)


def _ficha_del_torrent(stdout_text: str) -> dict:
    """Lo que guarda una subida que falla después de subir el torrent: su ficha, su id y la marca del enlace."""
    url = extract_torrent_url(stdout_text)
    if not url:
        return {}
    return {"result_url": url, "result_torrent_id": torrent_id_from_url(url), "torrent_subido": 1}


def _marca_torrent_subido(message: str) -> bool:
    """Si la línea dice que el torrent ya está en eMuwarez o en qBittorrent."""
    return message == QBIT_AÑADIDO or extract_torrent_url(message) is not None


def append_upload_log(
    job_id: int,
    level: str,
    message: str,
    stream: str = "system",
    raw: dict | None = None,
    conn=None,
) -> None:
    _avisar_de_log(job_id)
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        # La secuencia se calcula en el INSERT: dos hilos no cogen la misma, y el MAX lo resuelve el índice.
        conn.execute(
            """INSERT INTO upload_job_logs
               (upload_job_id, level, message, stream, created_at, raw_json, sequence, is_secret_redacted)
               VALUES (?, ?, ?, ?, ?, ?,
                       (SELECT COALESCE(MAX(sequence), 0) + 1 FROM upload_job_logs WHERE upload_job_id = ?), 1)""",
            (
                job_id,
                level,
                message[:8000],
                stream,
                _now(),
                json.dumps(raw, ensure_ascii=False) if raw else None,
                job_id,
            ),
        )
        if _marca_torrent_subido(message):
            # Al leer la línea, no al terminar: si el proceso muere después, el enlace sigue siendo de lo que se siembra.
            conn.execute("UPDATE upload_jobs SET torrent_subido = 1 WHERE id = ?", (job_id,))
        conn.commit()
    finally:
        if own:
            conn.close()


def get_upload_job_logs(
    job_id: int,
    limit: int = 500,
    offset: int = 0,
    *,
    tail: bool = False,
    after_sequence: int | None = None,
    conn=None,
) -> dict:
    """tail=True overrides `offset` to fetch the LAST `limit` lines instead
    of the first — a noisy job (many retries across several image hosts,
    each logging multiple lines) can easily produce more lines than a fixed
    small `limit`, and a caller that always passes offset=0 would otherwise
    be frozen on the SAME oldest window forever, never seeing anything
    logged after it — exactly what made "Ver Logs" look stuck/stale during
    a real per-host upload failure storm.

    after_sequence: solo las líneas posteriores a esa, de la más antigua a la más nueva (seguir una subida en vivo)."""
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        total_row = conn.execute(
            "SELECT COUNT(*) FROM upload_job_logs WHERE upload_job_id = ?", (job_id,)
        ).fetchone()
        total = total_row[0] if total_row else 0
        if after_sequence is not None:
            rows = conn.execute(
                "SELECT * FROM upload_job_logs WHERE upload_job_id = ? AND sequence > ? "
                "ORDER BY sequence ASC, id ASC LIMIT ?",
                (job_id, after_sequence, limit),
            ).fetchall()
        elif tail:
            # Del final hacia atrás por el índice y se da la vuelta: sin OFFSET, que recorre todo lo anterior.
            rows = conn.execute(
                "SELECT * FROM upload_job_logs WHERE upload_job_id = ? ORDER BY sequence DESC, id DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()[::-1]
            offset = max(0, total - limit)
        else:
            rows = conn.execute(
                "SELECT * FROM upload_job_logs WHERE upload_job_id = ? ORDER BY sequence ASC, id ASC LIMIT ? OFFSET ?",
                (job_id, limit, offset),
            ).fetchall()
        return {
            "job_id": job_id,
            "logs": rows_to_dicts(rows),
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        if own:
            conn.close()


def create_upload_artifact(
    job_id: int,
    artifact_type: str,
    *,
    name: str | None = None,
    path: str | None = None,
    url: str | None = None,
    value: str | None = None,
    raw: dict | None = None,
    conn=None,
) -> dict:
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        now = _now()
        cur = conn.execute(
            """INSERT INTO upload_artifacts
               (upload_job_id, artifact_type, name, path, url, value, created_at, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                artifact_type,
                name,
                path,
                url,
                value,
                now,
                json.dumps(raw, ensure_ascii=False) if raw else None,
            ),
        )
        conn.commit()
        return {
            "id": cur.lastrowid,
            "upload_job_id": job_id,
            "artifact_type": artifact_type,
            "name": name,
            "path": path,
            "url": url,
            "value": value,
            "created_at": now,
        }
    finally:
        if own:
            conn.close()


def get_upload_job_artifacts(job_id: int, conn=None) -> list[dict]:
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM upload_artifacts WHERE upload_job_id = ? ORDER BY id ASC",
            (job_id,),
        ).fetchall()
        return rows_to_dicts(rows)
    finally:
        if own:
            conn.close()
