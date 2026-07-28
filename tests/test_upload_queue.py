"""Tests for services/upload_queue.py — the queued-upload orchestration
("Subir a eMuwarez" -> queued job -> grace period -> server-side
integrity/nomenclature/remux/start)."""
from __future__ import annotations

import json

import pytest

from emuwarez_uploadrr.services import upload_queue as uq


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _movie_with_path(conn, path: str, title: str = "X") -> int:
    conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status, path, size_bytes, updated_at)
           VALUES ('movie', ?, 'Disponible', 'Sin petición', 'N/A', ?, 100, CURRENT_TIMESTAMP)""",
        (title, path),
    )
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _queued_job_row(conn, item_id: int, path: str = "") -> int:
    """Insert a 'queued' job row directly, bypassing the real timer — lets
    tests drive _run_queued_job() deterministically instead of racing a
    real threading.Timer."""
    cur = conn.execute(
        """INSERT INTO upload_jobs (library_item_id, status, stage, title, path, source_path,
                                     queued_until, created_at, updated_at)
           VALUES (?, 'queued', 'queued', 'X', ?, ?, '2099-01-01T00:00:00+00:00',
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (item_id, path, path),
    )
    conn.commit()
    return cur.lastrowid


def test_queue_creates_queued_job_and_registers_timer(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))

    result = uq.queue_upload_for_item(iid, conn=db_conn)
    assert result["status"] == "queued"
    job = result["job"]
    assert job["status"] == "queued"
    assert job["queued_until"]

    job_id = job["id"]
    assert job_id in uq._QUEUE_TIMERS
    try:
        assert uq.cancel_queued_timer(job_id) is True
        assert job_id not in uq._QUEUE_TIMERS
    finally:
        uq.cancel_queued_timer(job_id)  # no-op safety net if the assert above failed


def test_get_queue_positions_orders_by_id(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 10)
    iid = _movie_with_path(db_conn, str(f))
    j1 = _queued_job_row(db_conn, iid)
    j2 = _queued_job_row(db_conn, iid)
    j3 = _queued_job_row(db_conn, iid)

    positions = uq.get_queue_positions(db_conn)
    assert positions[j1] == (1, 3)
    assert positions[j2] == (2, 3)
    assert positions[j3] == (3, 3)


def test_get_queue_positions_ignores_non_queued_jobs(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 10)
    iid = _movie_with_path(db_conn, str(f))
    j1 = _queued_job_row(db_conn, iid)
    j2 = _queued_job_row(db_conn, iid)
    db_conn.execute("UPDATE upload_jobs SET status = 'running' WHERE id = ?", (j1,))
    db_conn.commit()

    positions = uq.get_queue_positions(db_conn)
    assert j1 not in positions
    assert positions[j2] == (1, 1)


def test_queue_persists_checks_snapshot(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    checks = {
        "checks": [
            {"id": "renameable", "label": "Se puede renombrar", "status": "ok", "message": "/x"},
            {"id": "emuwarez", "label": "eMuwarez disponible", "status": "ok", "message": ""},
        ],
        "ready": True,
    }

    result = uq.queue_upload_for_item(iid, checks=checks, conn=db_conn)
    job_id = result["job"]["id"]
    try:
        row = db_conn.execute("SELECT checks_snapshot_json FROM upload_jobs WHERE id=?", (job_id,)).fetchone()
        stored = json.loads(row["checks_snapshot_json"])
        assert stored == checks
    finally:
        uq.cancel_queued_timer(job_id)


def _insert_proposal(conn, item_id, title="Movie.2024.1080p"):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO nomenclature_proposals
           (library_item_id, status, proposed_filename, proposed_title, created_at, updated_at)
           VALUES (?,?,?,?,?,?)""",
        (item_id, "valid", title, title, now, now),
    )
    conn.commit()
    return cur.lastrowid


def test_queue_pins_and_persists_latest_nomenclature_proposal(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    proposal_id = _insert_proposal(db_conn, iid)

    result = uq.queue_upload_for_item(iid, conn=db_conn)
    job_id = result["job"]["id"]
    try:
        row = db_conn.execute(
            "SELECT nomenclature_proposal_id, nomenclature_snapshot_json FROM upload_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        assert row["nomenclature_proposal_id"] == proposal_id
        assert json.loads(row["nomenclature_snapshot_json"])["id"] == proposal_id
    finally:
        uq.cancel_queued_timer(job_id)


def test_queue_persists_remux_overrides_and_snapshot(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    overrides = {5: {"new_name": "Custom.Track.Name", "default_after": True}}
    snapshot = {"ordered_tracks": [{"id": 5, "new_name": "Custom.Track.Name"}]}

    result = uq.queue_upload_for_item(iid, remux_overrides=overrides, remux_snapshot=snapshot, conn=db_conn)
    job_id = result["job"]["id"]
    try:
        row = db_conn.execute(
            "SELECT remux_overrides_json, remux_snapshot_json FROM upload_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        assert json.loads(row["remux_overrides_json"]) == {"5": {"new_name": "Custom.Track.Name", "default_after": True}}
        assert json.loads(row["remux_snapshot_json"]) == snapshot
    finally:
        uq.cancel_queued_timer(job_id)


def test_queue_blocked_when_item_missing(db_conn):
    result = uq.queue_upload_for_item(999999, conn=db_conn)
    assert result["status"] == "blocked"
    assert result["job"] is None


def test_cancel_upload_job_stops_queued_timer(db_conn, tmp_path):
    from emuwarez_uploadrr.services.upload_execution import cancel_upload_job, get_upload_job

    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    result = uq.queue_upload_for_item(iid, conn=db_conn)
    job_id = result["job"]["id"]

    try:
        r = cancel_upload_job(job_id, conn=db_conn)
        assert r["ok"] is True
        job = get_upload_job(job_id, conn=db_conn)
        assert job["status"] == "cancelled"
        assert job_id not in uq._QUEUE_TIMERS
    finally:
        uq.cancel_queued_timer(job_id)


def test_run_queued_job_fails_fast_when_file_inaccessible(db_conn):
    iid = _movie_with_path(db_conn, "/nope/does/not/exist.mkv")
    job_id = _queued_job_row(db_conn, iid, path="/nope/does/not/exist.mkv")

    uq._run_queued_job(job_id)

    from emuwarez_uploadrr.services.upload_execution import get_upload_job
    job = get_upload_job(job_id, conn=db_conn)
    assert job["status"] == "failed"
    assert job["stage"] == "failed"
    assert "no es accesible" in (job["error_message"] or "")


def test_run_queued_job_releases_concurrency_slot_on_early_failure(db_conn):
    """"Subidas en paralelo" full serialization: _run_queued_job now takes its
    concurrency slot before any preprocessing (not just around the real
    Uploadrr-EMU subprocess like before) — a job that fails during that very
    first integrity check (well before ever reaching start_upload_job) must
    still release it, or every failed queued job would permanently eat one
    slot and eventually deadlock the whole queue."""
    from emuwarez_uploadrr.services.upload_execution import _upload_concurrency_gate
    assert _upload_concurrency_gate._active == 0

    iid = _movie_with_path(db_conn, "/nope/does/not/exist.mkv")
    job_id = _queued_job_row(db_conn, iid, path="/nope/does/not/exist.mkv")

    uq._run_queued_job(job_id)

    assert _upload_concurrency_gate._active == 0


# ---------------------------------------------------------------------------
# Internal MKV title (mkvpropedit) — previously never wired into the real
# pipeline at all (only reachable from Biblioteca's separate "Adaptar
# nomenclatura" modal), so no real upload ever actually changed the file's
# own embedded title. Confirmed in production: Chappie, 2026-07-30, still
# showed "Chappie [www.newpct1.com]" (the source release's own title) after
# a real upload.
# ---------------------------------------------------------------------------

def test_apply_mkv_title_best_effort_logs_success(db_conn, monkeypatch):
    iid = _movie_with_path(db_conn, "/x/movie.mkv")
    job_id = _queued_job_row(db_conn, iid, path="/x/movie.mkv")

    import emuwarez_uploadrr.services.mkv_title as mkv_title_mod
    monkeypatch.setattr(
        mkv_title_mod, "apply_internal_title_update",
        lambda *a, **k: {"status": "applied", "internal_mkv_title": "Movie.2024-TAG"},
    )

    uq._apply_mkv_title_best_effort(job_id, iid, conn=db_conn)

    from emuwarez_uploadrr.services.upload_execution import get_upload_job_logs
    logs = get_upload_job_logs(job_id, conn=db_conn)
    assert any("Título interno del MKV actualizado" in log["message"] for log in logs["logs"])


def test_apply_mkv_title_best_effort_skips_silently_when_blocked(db_conn, monkeypatch):
    """A non-.mkv file or a missing prepared_path ("blocked") is expected/
    skippable, not something worth alarming the user about in the log."""
    iid = _movie_with_path(db_conn, "/x/movie.mkv")
    job_id = _queued_job_row(db_conn, iid, path="/x/movie.mkv")

    import emuwarez_uploadrr.services.mkv_title as mkv_title_mod
    monkeypatch.setattr(
        mkv_title_mod, "apply_internal_title_update",
        lambda *a, **k: {"status": "blocked", "errors": ["no es .mkv"]},
    )

    uq._apply_mkv_title_best_effort(job_id, iid, conn=db_conn)

    from emuwarez_uploadrr.services.upload_execution import get_upload_job_logs
    logs = get_upload_job_logs(job_id, conn=db_conn)
    assert not any("MKV" in log["message"] for log in logs["logs"])


def test_apply_mkv_title_best_effort_logs_warning_on_real_failure(db_conn, monkeypatch):
    """A genuine mkvpropedit failure must be visible (unlike "blocked" above)
    but must NOT fail the job — the video itself is fine either way."""
    iid = _movie_with_path(db_conn, "/x/movie.mkv")
    job_id = _queued_job_row(db_conn, iid, path="/x/movie.mkv")

    import emuwarez_uploadrr.services.mkv_title as mkv_title_mod
    monkeypatch.setattr(
        mkv_title_mod, "apply_internal_title_update",
        lambda *a, **k: {"status": "error", "errors": ["mkvpropedit exit 1"]},
    )

    uq._apply_mkv_title_best_effort(job_id, iid, conn=db_conn)

    from emuwarez_uploadrr.services.upload_execution import get_upload_job, get_upload_job_logs
    logs = get_upload_job_logs(job_id, conn=db_conn)
    assert any("No se pudo actualizar el título interno del MKV" in log["message"] for log in logs["logs"])
    # Confirms this really is best-effort: no status column touched.
    assert get_upload_job(job_id, conn=db_conn)["status"] == "queued"


def test_apply_mkv_title_best_effort_survives_exception(db_conn, monkeypatch):
    iid = _movie_with_path(db_conn, "/x/movie.mkv")
    job_id = _queued_job_row(db_conn, iid, path="/x/movie.mkv")

    import emuwarez_uploadrr.services.mkv_title as mkv_title_mod

    def _raise(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(mkv_title_mod, "apply_internal_title_update", _raise)

    uq._apply_mkv_title_best_effort(job_id, iid, conn=db_conn)  # must not raise

    from emuwarez_uploadrr.services.upload_execution import get_upload_job_logs
    logs = get_upload_job_logs(job_id, conn=db_conn)
    assert any("Error actualizando el título interno del MKV" in log["message"] for log in logs["logs"])


def test_run_queued_job_season_applies_mkv_title_per_episode(db_conn, tmp_path, monkeypatch):
    """The user's explicit requirement: for a season, the internal title
    must be applied to EVERY episode individually, not just once for the
    season as a whole (each episode is its own separate MKV file)."""
    season_id, episode_ids = _seed_season_with_episodes(db_conn, n=3)
    job_id = _queued_job_row(db_conn, season_id, path="")

    monkeypatch.setattr(uq, "_check_season_integrity", lambda *a, **k: True)
    monkeypatch.setattr(uq, "_check_generic_upload_preconditions", lambda *a, **k: True)

    import emuwarez_uploadrr.services.season_pack as season_pack_mod
    monkeypatch.setattr(
        season_pack_mod, "apply_season_pack",
        lambda *a, **k: {"status": "applied", "episodes": [], "season_pack_title": "Serie X S01"},
    )
    monkeypatch.setattr(uq, "_run_season_remux", lambda job_id, season_id, conn: (True, []))

    calls = []
    import emuwarez_uploadrr.services.mkv_title as mkv_title_mod
    monkeypatch.setattr(
        mkv_title_mod, "apply_internal_title_update",
        lambda library_item_id, **k: calls.append(library_item_id) or {"status": "blocked"},
    )

    uq._run_queued_job(job_id)

    assert sorted(calls) == sorted(episode_ids)


def test_run_queued_job_skipped_when_job_not_queued_anymore(db_conn, tmp_path, monkeypatch):
    """Simulates the cancel-race: if the job's status isn't 'queued' anymore
    by the time the timer fires (e.g. cancelled a moment earlier), the
    orchestrator must not touch the filesystem at all."""
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    job_id = _queued_job_row(db_conn, iid, path=str(f))
    db_conn.execute("UPDATE upload_jobs SET status = 'cancelled' WHERE id = ?", (job_id,))
    db_conn.commit()

    called = []
    monkeypatch.setattr(uq, "_mark", lambda *a, **k: called.append((a, k)))

    uq._run_queued_job(job_id)

    assert called == []  # never even reached the integrity stage
    from emuwarez_uploadrr.services.upload_execution import get_upload_job
    job = get_upload_job(job_id, conn=db_conn)
    assert job["status"] == "cancelled"  # left untouched


def _failed_job_row(conn, item_id: int, *, status: str = "failed", retry_count: int = 0) -> int:
    cur = conn.execute(
        """INSERT INTO upload_jobs (library_item_id, status, stage, title, path, source_path,
                                     retry_count, created_at, updated_at)
           VALUES (?, ?, ?, 'X', '', '', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (item_id, status, status, retry_count),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# queue_retry_for_job — no-confirmation retry straight into 'queued'
# ---------------------------------------------------------------------------

def test_queue_retry_for_job_creates_new_queued_row(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    original_id = _failed_job_row(db_conn, iid, status="failed", retry_count=1)

    result = uq.queue_retry_for_job(original_id, conn=db_conn)
    try:
        assert result["status"] == "queued"
        new_job = result["job"]
        assert new_job["id"] != original_id
        assert new_job["status"] == "queued"
        assert new_job["queued_until"]
        assert new_job["retry_of_job_id"] == original_id
        assert new_job["retry_count"] == 2

        # Original job untouched.
        original = db_conn.execute("SELECT status FROM upload_jobs WHERE id=?", (original_id,)).fetchone()
        assert original["status"] == "failed"
    finally:
        uq.cancel_queued_timer(result["job"]["id"])


def test_queue_retry_carries_forward_manual_nomenclature_and_remux(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    proposal_id = _insert_proposal(db_conn, iid)
    original_id = _failed_job_row(db_conn, iid, status="failed")
    db_conn.execute(
        "UPDATE upload_jobs SET nomenclature_proposal_id = ?, remux_overrides_json = ? WHERE id = ?",
        (proposal_id, json.dumps({"5": {"new_name": "Custom", "default_after": True}}), original_id),
    )
    db_conn.commit()

    result = uq.queue_retry_for_job(original_id, conn=db_conn)
    try:
        row = db_conn.execute(
            "SELECT nomenclature_proposal_id, remux_overrides_json FROM upload_jobs WHERE id=?",
            (result["job"]["id"],),
        ).fetchone()
        assert row["nomenclature_proposal_id"] == proposal_id
        assert json.loads(row["remux_overrides_json"]) == {"5": {"new_name": "Custom", "default_after": True}}
    finally:
        uq.cancel_queued_timer(result["job"]["id"])


def test_queue_retry_does_not_backfill_nomenclature_for_automatic_job(db_conn, tmp_path):
    """An automatic (staging-pipeline) job never sets nomenclature_proposal_id
    — its absence is the signal a retry uses to keep auto-detecting from
    scratch instead of pinning a specific proposal."""
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    _insert_proposal(db_conn, iid)  # a proposal exists, but was never pinned to the job
    original_id = _failed_job_row(db_conn, iid, status="failed")

    result = uq.queue_retry_for_job(original_id, conn=db_conn)
    try:
        row = db_conn.execute(
            "SELECT nomenclature_proposal_id FROM upload_jobs WHERE id=?", (result["job"]["id"],),
        ).fetchone()
        assert row["nomenclature_proposal_id"] is None
    finally:
        uq.cancel_queued_timer(result["job"]["id"])


def test_queue_retry_for_job_blocked_when_not_failed_or_cancelled(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    original_id = _failed_job_row(db_conn, iid, status="completed")

    result = uq.queue_retry_for_job(original_id, conn=db_conn)
    assert result["status"] == "blocked"
    assert result["job"] is None


def test_queue_retry_for_job_not_found(db_conn):
    result = uq.queue_retry_for_job(999999, conn=db_conn)
    assert result["status"] == "blocked"


# ---------------------------------------------------------------------------
# _write_snapshot / _run_season_remux — persisted nomenclature/remux data for
# the job detail page (previously discarded once nomenclature.py/mkv_remux.py
# returned).
# ---------------------------------------------------------------------------

def test_write_snapshot_persists_json(db_conn):
    iid = _movie_with_path(db_conn, "/x/movie.mkv")
    job_id = _queued_job_row(db_conn, iid, path="/x/movie.mkv")

    uq._write_snapshot(job_id, "nomenclature_snapshot_json", {"proposed_filename": "Movie.2024-TAG"}, conn=db_conn)

    row = db_conn.execute("SELECT nomenclature_snapshot_json FROM upload_jobs WHERE id=?", (job_id,)).fetchone()
    assert json.loads(row["nomenclature_snapshot_json"]) == {"proposed_filename": "Movie.2024-TAG"}


# ---------------------------------------------------------------------------
# Season Source/Proveedor/Tag overrides (manual wizard's now-editable season
# fields, no longer read-only) — get_queue_positions comes first alphabetically
# but these fit better next to the other season-only tests below.
# ---------------------------------------------------------------------------

def test_queue_upload_for_item_persists_season_overrides(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 10)
    iid = _movie_with_path(db_conn, str(f))
    result = uq.queue_upload_for_item(iid, source_override="BluRay", conn=db_conn)
    job_id = result["job"]["id"]
    try:
        row = db_conn.execute("SELECT season_overrides_json FROM upload_jobs WHERE id=?", (job_id,)).fetchone()
        # Not a season — the override is simply ignored (a movie/episode's
        # edits already flow through nomenclature_proposals instead).
        assert row["season_overrides_json"] is None
    finally:
        uq.cancel_queued_timer(job_id)


def test_queue_upload_for_item_persists_season_overrides_for_season(db_conn):
    season_id, _episode_ids = _seed_season_with_episodes(db_conn, n=1)
    result = uq.queue_upload_for_item(
        season_id, source_override="BluRay", tag_override="MYTAG", conn=db_conn,
    )
    job_id = result["job"]["id"]
    try:
        row = db_conn.execute("SELECT season_overrides_json FROM upload_jobs WHERE id=?", (job_id,)).fetchone()
        assert json.loads(row["season_overrides_json"]) == {
            "source": "BluRay", "provider": None, "tag": "MYTAG",
        }
    finally:
        uq.cancel_queued_timer(job_id)


def test_run_queued_job_season_forwards_stored_overrides_to_apply(db_conn, tmp_path, monkeypatch):
    """Regression: apply_season_pack() previously ignored any override —
    even one the Automático source-disparity gate had already resolved by
    hand — recomputing the pack from scratch with no override at all, so the
    real renamed files never reflected the user's choice."""
    season_id, episode_ids = _seed_season_with_episodes(db_conn, n=1)
    f = tmp_path / "S01E01.mkv"
    f.write_bytes(b"x" * 100)
    db_conn.execute("UPDATE library_items SET path = ? WHERE id = ?", (str(f), episode_ids[0]))
    db_conn.commit()

    job_id = _queued_job_row(db_conn, season_id, path="")
    db_conn.execute(
        "UPDATE upload_jobs SET season_overrides_json = ? WHERE id = ?",
        (json.dumps({"source": "BluRay", "provider": None, "tag": "MYTAG"}), job_id),
    )
    db_conn.commit()

    monkeypatch.setattr(uq, "_check_season_integrity", lambda *a, **k: True)
    monkeypatch.setattr(uq, "_check_generic_upload_preconditions", lambda *a, **k: True)

    captured = {}
    import emuwarez_uploadrr.services.season_pack as season_pack_mod

    def fake_apply_season_pack(season_id_arg, conn, *, job_id=None,
                                source_override=None, provider_override=None, tag_override=None):
        captured["source_override"] = source_override
        captured["provider_override"] = provider_override
        captured["tag_override"] = tag_override
        return {"status": "blocked", "errors": ["stop here on purpose"], "episodes": []}

    monkeypatch.setattr(season_pack_mod, "apply_season_pack", fake_apply_season_pack)

    uq._run_queued_job(job_id)

    assert captured == {"source_override": "BluRay", "provider_override": None, "tag_override": "MYTAG"}


def _seed_season_with_episodes(conn, n=2):
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status, updated_at)
           VALUES ('series', 'Serie X', 2020, 'Parcial', 'Sin petición', 'N/A', CURRENT_TIMESTAMP)"""
    )
    series_id = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO library_items
           (item_type, title, year, local_status, request_status, nomenclature_status, parent_id, season_number, updated_at)
           VALUES ('season', 'Serie X - Temporada 1', 2020, 'Parcial', 'Sin petición', 'N/A', ?, 1, CURRENT_TIMESTAMP)""",
        (series_id,),
    )
    season_id = cur.lastrowid
    episode_ids = []
    for i in range(1, n + 1):
        cur = conn.execute(
            """INSERT INTO library_items
               (item_type, title, year, local_status, request_status, nomenclature_status,
                parent_id, season_number, episode_number, path, updated_at)
               VALUES ('episode', ?, 2020, 'Disponible', 'Sin petición', 'No adaptada', ?, 1, ?, ?, CURRENT_TIMESTAMP)""",
            (f"Episodio {i}", season_id, i, f"/x/S01E0{i}.mkv"),
        )
        episode_ids.append(cur.lastrowid)
    conn.commit()
    return season_id, episode_ids


def test_run_season_remux_accumulates_per_episode_snapshot(db_conn, monkeypatch):
    season_id, episode_ids = _seed_season_with_episodes(db_conn, n=2)
    job_id = _queued_job_row(db_conn, episode_ids[0], path="")

    fake_tracks = [{"id": 0, "type": "audio", "new_name": "Español", "default_after": True}]

    def fake_build_remux_plan(item_id, conn=None):
        return {"status": "ready", "ordered_tracks": fake_tracks}

    def fake_apply_remux(item_id, *, apply, dry_run, confirmation, overrides, conn, on_progress=None):
        if on_progress:
            on_progress(50)
            on_progress(100)
        return {"status": "applied", "ordered_tracks": fake_tracks}

    import emuwarez_uploadrr.services.mkv_remux as mkv_remux_mod
    monkeypatch.setattr(mkv_remux_mod, "build_remux_plan", fake_build_remux_plan)
    monkeypatch.setattr(mkv_remux_mod, "apply_remux", fake_apply_remux)

    ok, snapshot = uq._run_season_remux(job_id, season_id, conn=db_conn)

    assert ok is True
    assert len(snapshot) == 2
    assert all(ep["ordered_tracks"] == fake_tracks for ep in snapshot)

    row = db_conn.execute("SELECT progress_json FROM upload_jobs WHERE id=?", (job_id,)).fetchone()
    state = json.loads(row["progress_json"])
    by_key = {p["key"]: p for p in state["phases"]}
    assert by_key["remux"]["pct"] == 100


# ---------------------------------------------------------------------------
# _find_latest_job_for_item / duplicate-chaining — a fresh "Subir" (or
# Automático) on an item that already has a job (any status, including
# Completado) chains onto it via retry_of_job_id instead of creating an
# unrelated row.
# ---------------------------------------------------------------------------

def test_find_latest_job_for_item_no_jobs(db_conn):
    iid = _movie_with_path(db_conn, "/x/movie.mkv")
    assert uq._find_latest_job_for_item(db_conn, iid) is None


def test_find_latest_job_for_item_returns_tip_of_chain(db_conn):
    iid = _movie_with_path(db_conn, "/x/movie.mkv")
    j1 = _failed_job_row(db_conn, iid, status="completed")
    j2 = _failed_job_row(db_conn, iid, status="failed", retry_count=1)
    db_conn.execute("UPDATE upload_jobs SET retry_of_job_id = ? WHERE id = ?", (j1, j2))
    j3 = _failed_job_row(db_conn, iid, status="cancelled", retry_count=2)
    db_conn.execute("UPDATE upload_jobs SET retry_of_job_id = ? WHERE id = ?", (j2, j3))
    db_conn.commit()

    latest = uq._find_latest_job_for_item(db_conn, iid)
    assert latest["id"] == j3


def test_queue_upload_chains_onto_terminal_job_including_completed(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    original_id = _failed_job_row(db_conn, iid, status="completed", retry_count=0)

    result = uq.queue_upload_for_item(iid, conn=db_conn)
    try:
        assert result["status"] == "queued"
        job = result["job"]
        assert job["retry_of_job_id"] == original_id
        assert job["retry_count"] == 1

        original = db_conn.execute("SELECT status FROM upload_jobs WHERE id=?", (original_id,)).fetchone()
        assert original["status"] == "completed"  # untouched
    finally:
        uq.cancel_queued_timer(result["job"]["id"])


def test_queue_upload_blocked_when_latest_job_is_active(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    _queued_job_row(db_conn, iid, path=str(f))

    result = uq.queue_upload_for_item(iid, conn=db_conn)
    assert result["status"] == "blocked"
    assert "en curso" in result["errors"][0]


# ---------------------------------------------------------------------------
# staging ("Automático") — the job appears immediately as 'staging', gets
# its nomenclature/remux/checks previews computed in the background, then is
# promoted into the normal 'queued' 60s countdown.
# ---------------------------------------------------------------------------

def test_queue_auto_upload_inserts_staging_job(db_conn, tmp_path, monkeypatch):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    monkeypatch.setattr(uq, "_run_staging_job", lambda job_id, **kwargs: None)

    result = uq.queue_auto_upload_for_item(iid, conn=db_conn)
    assert result["status"] == "staging"
    job = result["job"]
    assert job["status"] == "staging"
    assert job["queued_until"] is None


def test_queue_auto_upload_blocked_when_latest_job_is_active(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    _queued_job_row(db_conn, iid, path=str(f))

    result = uq.queue_auto_upload_for_item(iid, conn=db_conn)
    assert result["status"] == "blocked"


def test_run_staging_job_promotes_to_queued_with_snapshots(db_conn, tmp_path, monkeypatch):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    job_id = uq._insert_staging_job(db_conn, {"id": iid, "title": "X", "path": str(f)})

    import emuwarez_uploadrr.services.nomenclature as nomenclature_mod
    import emuwarez_uploadrr.services.mkv_remux as mkv_remux_mod
    import emuwarez_uploadrr.services.upload_checks as upload_checks_mod

    monkeypatch.setattr(
        nomenclature_mod, "apply_nomenclature_proposal",
        lambda item_id, conn=None, **kwargs: {"status": "applied", "proposal": {"proposed_filename": "Movie.2024-TAG"}},
    )
    monkeypatch.setattr(
        mkv_remux_mod, "build_remux_plan",
        lambda item_id, conn=None: {"status": "ready", "ordered_tracks": [{"id": 0, "type": "video"}]},
    )
    monkeypatch.setattr(
        upload_checks_mod, "run_upload_checks",
        lambda conn, item_id: {"checks": [{"id": "renameable", "label": "x", "status": "ok", "message": ""}], "ready": True},
    )

    try:
        uq._run_staging_job(job_id)

        from emuwarez_uploadrr.services.upload_execution import get_upload_job
        job = get_upload_job(job_id, conn=db_conn)
        assert job["status"] == "queued"
        assert job["queued_until"]
        assert json.loads(job["nomenclature_snapshot_json"]) == {"proposed_filename": "Movie.2024-TAG"}
        assert json.loads(job["remux_snapshot_json"]) == {"ordered_tracks": [{"id": 0, "type": "video"}]}
        assert json.loads(job["checks_snapshot_json"])["ready"] is True
    finally:
        uq.cancel_queued_timer(job_id)


def test_run_staging_job_fails_when_checks_are_not_ready(db_conn, tmp_path, monkeypatch):
    """Regression: a staging job used to be promoted to 'queued' regardless
    of run_upload_checks()'s own `ready` flag — the checks snapshot could
    say "failed" while the job itself sat in Subidas looking fine. The job
    must land in 'failed' with the check's own error message instead."""
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    job_id = uq._insert_staging_job(db_conn, {"id": iid, "title": "X", "path": str(f)})

    import emuwarez_uploadrr.services.nomenclature as nomenclature_mod
    import emuwarez_uploadrr.services.mkv_remux as mkv_remux_mod
    import emuwarez_uploadrr.services.upload_checks as upload_checks_mod

    monkeypatch.setattr(
        nomenclature_mod, "apply_nomenclature_proposal",
        lambda item_id, conn=None, **kwargs: {"status": "applied", "proposal": {"proposed_filename": "Movie.2024-TAG"}},
    )
    monkeypatch.setattr(
        mkv_remux_mod, "build_remux_plan",
        lambda item_id, conn=None: {"status": "ready", "ordered_tracks": []},
    )
    monkeypatch.setattr(
        upload_checks_mod, "run_upload_checks",
        lambda conn, item_id: {
            "checks": [{"id": "output", "label": "Directorio de salida no escribible", "status": "fail",
                        "message": "uploadrr.path no configurado"}],
            "ready": False,
        },
    )

    uq._run_staging_job(job_id)

    from emuwarez_uploadrr.services.upload_execution import get_upload_job
    job = get_upload_job(job_id, conn=db_conn)
    assert job["status"] == "failed"
    assert "uploadrr.path" in (job["error_message"] or "")
    # The checks snapshot itself must still be saved (so the job/detail page
    # can show exactly which check failed), even though the job failed.
    assert json.loads(job["checks_snapshot_json"])["ready"] is False


def test_run_staging_job_advances_stage_incrementally(db_conn, tmp_path, monkeypatch):
    """Each staging sub-step's snapshot must be written, and `stage` advanced,
    BEFORE the next one starts — the job detail page's per-section spinner
    relies on (status, stage) reflecting real progress, not a single
    end-of-staging batch write."""
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    job_id = uq._insert_staging_job(db_conn, {"id": iid, "title": "X", "path": str(f)})

    import emuwarez_uploadrr.services.nomenclature as nomenclature_mod
    import emuwarez_uploadrr.services.mkv_remux as mkv_remux_mod
    import emuwarez_uploadrr.services.upload_checks as upload_checks_mod
    from emuwarez_uploadrr.services.upload_execution import get_upload_job

    assert get_upload_job(job_id, conn=db_conn)["stage"] == "nomenclature"

    stage_when_remux_starts = {}
    stage_when_checks_start = {}

    def fake_apply_nomenclature(item_id, conn=None, **kwargs):
        # Nomenclature snapshot isn't written yet at this point.
        assert get_upload_job(job_id, conn=db_conn)["nomenclature_snapshot_json"] is None
        return {"status": "applied", "proposal": {"proposed_filename": "Movie.2024-TAG"}}

    def fake_build_remux_plan(item_id, conn=None, **kwargs):
        job = get_upload_job(job_id, conn=db_conn)
        stage_when_remux_starts["stage"] = job["stage"]
        stage_when_remux_starts["nomenclature_snapshot"] = job["nomenclature_snapshot_json"]
        return {"status": "ready", "ordered_tracks": [{"id": 0, "type": "video"}]}

    def fake_run_upload_checks(conn, item_id):
        job = get_upload_job(job_id, conn=db_conn)
        stage_when_checks_start["stage"] = job["stage"]
        stage_when_checks_start["remux_snapshot"] = job["remux_snapshot_json"]
        return {"checks": [{"id": "renameable", "label": "x", "status": "ok", "message": ""}], "ready": True}

    monkeypatch.setattr(nomenclature_mod, "apply_nomenclature_proposal", fake_apply_nomenclature)
    monkeypatch.setattr(mkv_remux_mod, "build_remux_plan", fake_build_remux_plan)
    monkeypatch.setattr(upload_checks_mod, "run_upload_checks", fake_run_upload_checks)

    try:
        uq._run_staging_job(job_id)
        assert stage_when_remux_starts["stage"] == "remux"
        assert stage_when_remux_starts["nomenclature_snapshot"] is not None
        assert stage_when_checks_start["stage"] == "checks"
        assert stage_when_checks_start["remux_snapshot"] is not None
        assert get_upload_job(job_id, conn=db_conn)["status"] == "queued"
    finally:
        uq.cancel_queued_timer(job_id)


def test_run_staging_job_skipped_when_cancelled_before_promotion(db_conn, tmp_path, monkeypatch):
    """If the user cancels while the background preview computation is still
    running, _run_staging_job() must not overwrite the 'cancelled' status
    with 'queued' once it finishes."""
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    job_id = uq._insert_staging_job(db_conn, {"id": iid, "title": "X", "path": str(f)})

    import emuwarez_uploadrr.services.nomenclature as nomenclature_mod
    import emuwarez_uploadrr.services.mkv_remux as mkv_remux_mod
    import emuwarez_uploadrr.services.upload_checks as upload_checks_mod

    def fake_apply_nomenclature(item_id, conn=None, **kwargs):
        # Simulate the cancel happening mid-computation.
        db_conn.execute("UPDATE upload_jobs SET status = 'cancelled' WHERE id = ?", (job_id,))
        db_conn.commit()
        return {"status": "applied", "proposal": {"proposed_filename": "Movie.2024-TAG"}}

    monkeypatch.setattr(nomenclature_mod, "apply_nomenclature_proposal", fake_apply_nomenclature)
    monkeypatch.setattr(mkv_remux_mod, "build_remux_plan", lambda item_id, conn=None: {"status": "ready", "ordered_tracks": []})
    monkeypatch.setattr(upload_checks_mod, "run_upload_checks", lambda conn, item_id: {"checks": [], "ready": True})

    uq._run_staging_job(job_id)

    from emuwarez_uploadrr.services.upload_execution import get_upload_job
    job = get_upload_job(job_id, conn=db_conn)
    assert job["status"] == "cancelled"
    assert job["nomenclature_snapshot_json"] is None
    assert job_id not in uq._QUEUE_TIMERS
