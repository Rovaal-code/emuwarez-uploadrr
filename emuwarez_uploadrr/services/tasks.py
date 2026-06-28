"""Task run persistence helpers."""
from __future__ import annotations

import sqlite3
from typing import Optional


def start_task(conn: sqlite3.Connection, name: str, summary: Optional[str] = None) -> int:
    cur = conn.execute(
        "INSERT INTO task_runs(name, status, summary) VALUES (?, 'running', ?)",
        (name, summary),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_task(conn: sqlite3.Connection, task_id: int, status: str, summary: Optional[str] = None, details: Optional[str] = None) -> None:
    conn.execute(
        """
        UPDATE task_runs
        SET status = ?, summary = COALESCE(?, summary), details = ?, finished_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, summary, details, task_id),
    )
    conn.commit()


def list_tasks(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM task_runs ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
