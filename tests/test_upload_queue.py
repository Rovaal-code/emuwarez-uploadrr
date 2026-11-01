"""Tests for services/upload_queue.py — the queued-upload orchestration
("Subir a eMuwarez" -> queued job -> grace period -> server-side
integrity/nomenclature/remux/start)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from emuwarez_uploadrr.services import upload_queue as uq


@pytest.fixture(autouse=True)
def _biblioteca_en_tmp(tmp_path, monkeypatch):
    """Las bibliotecas de estos tests viven en tmp_path, no en /data."""
    from emuwarez_uploadrr.services import uploadrr_contract
    monkeypatch.setattr(uploadrr_contract, "DEFAULT_ALLOWED_ROOTS", [str(tmp_path)])


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


def _insert_proposal(conn, item_id, title="Movie.2024.1080p", status="valid", huella=True, fields_json=None):
    """Una propuesta guardada. Con `huella` lleva la del elemento actual (sigue
    vigente); sin ella es de reglas viejas y build_nomenclature_proposal la rehace."""
    from datetime import datetime, timezone
    from emuwarez_uploadrr.services import nomenclature as nom
    now = datetime.now(timezone.utc).isoformat()
    raw = None
    if huella:
        item = nom.get_library_item_for_nomenclature(item_id, conn=conn)
        raw = json.dumps({"huella": nom._huella(item)})
    cur = conn.execute(
        """INSERT INTO nomenclature_proposals
           (library_item_id, status, proposed_filename, proposed_title, raw_json, fields_json,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (item_id, status, title, title, raw, fields_json, now, now),
    )
    conn.commit()
    return cur.lastrowid


def test_queue_rehace_la_propuesta_automatica_de_reglas_viejas(db_conn, tmp_path):
    """Una automática bloqueada con reglas viejas no se fija: se rehace."""
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    vieja = _insert_proposal(db_conn, iid, status="blocked", huella=False)

    result = uq.queue_upload_for_item(iid, conn=db_conn)
    job_id = result["job"]["id"]
    try:
        row = db_conn.execute("SELECT nomenclature_proposal_id FROM upload_jobs WHERE id=?",
                              (job_id,)).fetchone()
        assert row["nomenclature_proposal_id"] not in (None, vieja)
        estado = db_conn.execute("SELECT status FROM nomenclature_proposals WHERE id=?", (vieja,)).fetchone()
        assert estado["status"] == "expired"
    finally:
        uq.cancel_queued_timer(job_id)


def test_queue_conserva_la_propuesta_editada_a_mano(db_conn, tmp_path):
    """La editada a mano se respeta aunque no lleve huella."""
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    manual = _insert_proposal(db_conn, iid, huella=False, fields_json=json.dumps({"title": "X"}))

    result = uq.queue_upload_for_item(iid, conn=db_conn)
    job_id = result["job"]["id"]
    try:
        row = db_conn.execute("SELECT nomenclature_proposal_id FROM upload_jobs WHERE id=?",
                              (job_id,)).fetchone()
        assert row["nomenclature_proposal_id"] == manual
    finally:
        uq.cancel_queued_timer(job_id)


def test_comprobacion_previa_no_falla_por_una_propuesta_bloqueada_de_reglas_viejas(db_conn, tmp_path, monkeypatch):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    _insert_proposal(db_conn, iid, status="blocked", huella=False)
    monkeypatch.setattr(uq, "_season_upload_preconditions", lambda conn: [])
    fallos = []
    monkeypatch.setattr(uq, "_fail", lambda job_id, msg: fallos.append(msg))
    nueva = {"id": 999, "status": "valid"}
    with patch("emuwarez_uploadrr.services.nomenclature.build_nomenclature_proposal",
               return_value=nueva) as build:
        assert uq._check_generic_upload_preconditions(1, iid, False, db_conn) is True
    build.assert_called_once()
    assert fallos == []


def test_comprobacion_previa_falla_si_la_vigente_esta_bloqueada(db_conn, tmp_path, monkeypatch):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    _insert_proposal(db_conn, iid, status="blocked")
    monkeypatch.setattr(uq, "_season_upload_preconditions", lambda conn: [])
    fallos = []
    monkeypatch.setattr(uq, "_fail", lambda job_id, msg: fallos.append(msg))
    assert uq._check_generic_upload_preconditions(1, iid, False, db_conn) is False
    assert fallos == ["Hay errores en la propuesta de nomenclatura que bloquean la subida."]


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


def test_run_queued_job_fails_when_file_outside_allowed_roots(db_conn, tmp_path, monkeypatch):
    from emuwarez_uploadrr.services import uploadrr_contract
    (tmp_path / "medios").mkdir()
    monkeypatch.setattr(uploadrr_contract, "DEFAULT_ALLOWED_ROOTS", [str(tmp_path / "medios")])
    fuera = tmp_path / "fuera" / "Peli.2024.mkv"
    fuera.parent.mkdir()
    fuera.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(fuera))
    job_id = _queued_job_row(db_conn, iid, path=str(fuera))

    uq._run_queued_job(job_id)

    from emuwarez_uploadrr.services.upload_execution import get_upload_job
    job = get_upload_job(job_id, conn=db_conn)
    assert job["status"] == "failed"
    assert "fuera de los allowed_roots" in (job["error_message"] or "")
    # Ni renombrado ni enlazado: el fichero sigue como estaba.
    assert [p.name for p in fuera.parent.iterdir()] == ["Peli.2024.mkv"]


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


@pytest.mark.usefixtures("ficheros_de_mentira")
def test_run_queued_job_stage_is_nomenclature_before_nomenclature_starts(db_conn, tmp_path):
    """Regression: `upload_jobs.stage` (a separate, older display pipeline
    from progress_json — see upload_execution.compute_progress_phase(), read
    by every "current activity" label as a fallback whenever progress_json
    has no phase in "running" state yet) used to be set to
    "verificacion_presubida" the instant a queued job left the queue, before
    nomenclature had even started — so the UI flashed "Iniciando Uploadrr"
    first instead of "Aplicando nomenclatura" (reported 2026-07-28, right
    after the progress_json phase-order fix shipped for the same underlying
    bug in the Fases table)."""
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    job_id = _queued_job_row(db_conn, iid, path=str(f))

    from emuwarez_uploadrr.services.upload_execution import get_upload_job
    real_check = uq._check_generic_upload_preconditions
    captured = {}

    def spy_check(*args, **kwargs):
        captured["stage"] = get_upload_job(job_id, conn=db_conn)["stage"]
        return real_check(*args, **kwargs)

    with patch.object(uq, "_check_generic_upload_preconditions", side_effect=spy_check):
        uq._run_queued_job(job_id)

    assert captured["stage"] == "nomenclature"


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


def test_queue_retry_fija_la_vigente_si_la_del_original_era_de_reglas_viejas(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    vieja = _insert_proposal(db_conn, iid, status="blocked", huella=False)
    original_id = _failed_job_row(db_conn, iid, status="failed")
    db_conn.execute("UPDATE upload_jobs SET nomenclature_proposal_id = ? WHERE id = ?", (vieja, original_id))
    db_conn.commit()

    result = uq.queue_retry_for_job(original_id, conn=db_conn)
    try:
        row = db_conn.execute(
            "SELECT nomenclature_proposal_id, nomenclature_snapshot_json FROM upload_jobs WHERE id=?",
            (result["job"]["id"],),
        ).fetchone()
        assert row["nomenclature_proposal_id"] not in (None, vieja)
        assert json.loads(row["nomenclature_snapshot_json"])["id"] == row["nomenclature_proposal_id"]
    finally:
        uq.cancel_queued_timer(result["job"]["id"])


def test_queue_retry_conserva_la_propuesta_editada_a_mano_aunque_haya_otra_posterior(db_conn, tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    manual = _insert_proposal(db_conn, iid, fields_json=json.dumps({"title": "Mio"}))
    original_id = _failed_job_row(db_conn, iid, status="failed")
    db_conn.execute("UPDATE upload_jobs SET nomenclature_proposal_id = ? WHERE id = ?", (manual, original_id))
    _insert_proposal(db_conn, iid, title="Otra")  # posterior y vigente
    db_conn.commit()

    result = uq.queue_retry_for_job(original_id, conn=db_conn)
    try:
        row = db_conn.execute("SELECT nomenclature_proposal_id FROM upload_jobs WHERE id=?",
                              (result["job"]["id"],)).fetchone()
        assert row["nomenclature_proposal_id"] == manual
    finally:
        uq.cancel_queued_timer(result["job"]["id"])


def test_comprobacion_previa_fija_la_propuesta_rehecha_en_el_trabajo(db_conn, tmp_path, monkeypatch):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    vieja = _insert_proposal(db_conn, iid, huella=False)
    job_id = _failed_job_row(db_conn, iid, status="queued")
    db_conn.execute("UPDATE upload_jobs SET nomenclature_proposal_id = ? WHERE id = ?", (vieja, job_id))
    db_conn.commit()
    monkeypatch.setattr(uq, "_season_upload_preconditions", lambda conn: [])
    nueva = {"id": vieja + 100, "status": "valid", "proposed_filename": "Nuevo"}
    with patch("emuwarez_uploadrr.services.nomenclature.build_nomenclature_proposal", return_value=nueva):
        assert uq._check_generic_upload_preconditions(job_id, iid, False, db_conn) is True
    row = db_conn.execute("SELECT nomenclature_proposal_id, nomenclature_snapshot_json FROM upload_jobs WHERE id=?",
                          (job_id,)).fetchone()
    assert row["nomenclature_proposal_id"] == vieja + 100
    assert json.loads(row["nomenclature_snapshot_json"])["proposed_filename"] == "Nuevo"


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
# _write_snapshot — persisted nomenclature/remux data for
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
            "source": "BluRay", "provider": None, "tag": "MYTAG", "title": None,
        }
    finally:
        uq.cancel_queued_timer(job_id)


def test_season_overrides_column_survives_schema_version_short_circuit(db_conn):
    """Regression: init_db() skips its ENTIRE migration cascade once
    app_state.schema_version already matches the current SCHEMA_VERSION
    (a deliberate perf guard — see init_db's own docstring). Adding
    _migrate_upload_jobs_season_overrides without also bumping
    SCHEMA_VERSION meant any server already on the current version never
    ran it at all — confirmed in production: "table upload_jobs has no
    column named season_overrides_json" on every upload (movie, episode,
    AND season, since the column is in that INSERT unconditionally).
    Forcing the cascade to run again (by clearing schema_version, same
    simulation the analogous missing_since regression test uses) must
    still add the column."""
    from emuwarez_uploadrr.database import init_db

    db_conn.execute("DELETE FROM app_state WHERE key = 'schema_version'")
    db_conn.commit()

    init_db(db_conn)

    cols = {row["name"] for row in db_conn.execute("PRAGMA table_info(upload_jobs)").fetchall()}
    assert "season_overrides_json" in cols

    # And queuing a plain movie (not just a season) must not blow up on the
    # column being missing — the real production symptom.
    iid = _movie_with_path(db_conn, "/x/movie.mkv")
    result = uq.queue_upload_for_item(iid, conn=db_conn)
    assert result["status"] == "queued"
    uq.cancel_queued_timer(result["job"]["id"])


def test_run_queued_job_season_forwards_stored_overrides_to_the_plan(db_conn, tmp_path, monkeypatch):
    """Regression: the pack used to be recomputed with no override at all, so
    the files never reflected the user's choice."""
    season_id, episode_ids = _seed_season_with_episodes(db_conn, n=1)
    f = tmp_path / "S01E01.mkv"
    f.write_bytes(b"x" * 100)
    db_conn.execute("UPDATE library_items SET path = ? WHERE id = ?", (str(f), episode_ids[0]))
    db_conn.commit()

    job_id = _queued_job_row(db_conn, season_id, path="")
    db_conn.execute(
        "UPDATE upload_jobs SET season_overrides_json = ? WHERE id = ?",
        (json.dumps({"source": "BluRay", "provider": None, "tag": "MYTAG",
                     "title": "The Tudors"}), job_id),
    )
    db_conn.commit()

    monkeypatch.setattr(uq, "_check_season_integrity", lambda *a, **k: True)
    monkeypatch.setattr(uq, "_check_generic_upload_preconditions", lambda *a, **k: True)

    captured = {}
    import emuwarez_uploadrr.services.season_pack as season_pack_mod

    def fake_plan(season_id_arg, conn=None, *,
                  source_override=None, provider_override=None, tag_override=None,
                  title_override=None):
        captured["source_override"] = source_override
        captured["provider_override"] = provider_override
        captured["tag_override"] = tag_override
        captured["title_override"] = title_override
        return {"status": "blocked", "errors": ["stop here on purpose"], "episodes": []}

    monkeypatch.setattr(season_pack_mod, "build_season_pack_plan", fake_plan)

    uq._run_queued_job(job_id)

    assert captured == {
        "source_override": "BluRay", "provider_override": None, "tag_override": "MYTAG",
        # The Título dropdown's pick has to survive the round trip through
        # season_overrides_json too — a season has no proposal row to hold it.
        "title_override": "The Tudors",
    }


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


def test_reintentar_dos_veces_no_crea_dos_subidas(db_conn, tmp_path):
    """Doble clic en "Reintentar": el original sigue fallido, así que el
    segundo reintento también lo aceptaba y el contenido se subía dos veces."""
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    original_id = _failed_job_row(db_conn, iid, status="failed")

    primero = uq.queue_retry_for_job(original_id, conn=db_conn)
    try:
        segundo = uq.queue_retry_for_job(original_id, conn=db_conn)
        assert primero["status"] == "queued"
        assert segundo["status"] == "blocked"
        assert segundo["job"]["id"] == primero["job"]["id"]
        activos = db_conn.execute(
            "SELECT COUNT(*) FROM upload_jobs WHERE library_item_id = ? AND status = 'queued'", (iid,)
        ).fetchone()[0]
        assert activos == 1
    finally:
        uq.cancel_queued_timer(primero["job"]["id"])


def test_dos_peticiones_a_la_vez_dejan_una_sola_subida(db_conn, tmp_path, monkeypatch):
    """Dos peticiones simultáneas (dos pestañas) leían las dos "no hay nada en
    curso" antes de que ninguna insertara."""
    import threading

    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    monkeypatch.setattr(uq, "_arm_queue_timer", lambda job_id: None)

    barrera = threading.Barrier(2)
    original = uq._find_latest_job_for_item

    def leer_y_esperar(conn, item_id):
        fila = original(conn, item_id)
        barrera.wait(timeout=5)
        return fila

    monkeypatch.setattr(uq, "_find_latest_job_for_item", leer_y_esperar)
    resultados = []
    hilos = [threading.Thread(target=lambda: resultados.append(uq.queue_upload_for_item(iid)["status"]))
             for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert sorted(resultados) == ["blocked", "queued"]
    activos = db_conn.execute(
        "SELECT COUNT(*) FROM upload_jobs WHERE library_item_id = ? AND status = 'queued'", (iid,)
    ).fetchone()[0]
    assert activos == 1


# ---------------------------------------------------------------------------
# staging ("Automático") — the job appears immediately as 'staging', gets
# its nomenclature/remux/checks previews computed in the background, then is
# promoted into the normal 'queued' 60s countdown.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Cancelar mientras se preparan ficheros
# ---------------------------------------------------------------------------

def test_cancelling_while_preparing_marks_the_job_and_stops_it(db_conn, tmp_path):
    """Antes 'preparing' no se podía cancelar: ni el botón ni la API lo
    aceptaban. Si la aplicación se paraba en esa fase, el job se quedaba ahí
    para siempre y no había forma de tocarlo desde la interfaz."""
    from emuwarez_uploadrr.services import upload_queue as uq
    from emuwarez_uploadrr.services.upload_execution import cancel_upload_job

    f = tmp_path / "peli.mkv"
    f.write_bytes(b"x")
    cur = db_conn.execute(
        "INSERT INTO library_items(item_type,title,local_status,path) VALUES ('movie','Peli','Disponible',?)",
        (str(f),))
    item_id = cur.lastrowid
    cur = db_conn.execute(
        """INSERT INTO upload_jobs(library_item_id, title, path, status, stage)
           VALUES (?, 'Peli', ?, 'preparing', 'remux')""", (item_id, str(f)))
    job_id = cur.lastrowid
    db_conn.commit()

    result = cancel_upload_job(job_id, conn=db_conn)
    assert result["ok"] is True
    assert db_conn.execute("SELECT status FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()["status"] == "cancelled"

    # Y el trabajo que siguiera vivo NO puede resucitarlo al pasar de fase:
    # sin este guardia el job volvía a parecer en marcha después de cancelarlo.
    assert uq._mark(job_id, stage="verificacion_presubida") is False
    assert db_conn.execute("SELECT status FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()["status"] == "cancelled"
    assert uq.job_was_cancelled(job_id, conn=db_conn) is True


def test_un_job_cancelado_cuenta_como_activo_hasta_que_su_hilo_termina(db_conn, tmp_path):
    """Cancelar en 'preparing' solo marca la fila: el hilo sigue renombrando o
    remuxeando hasta el siguiente punto limpio. Un Reintentar en ese momento
    lanzaba una segunda preparación sobre el mismo fichero."""
    import threading
    from unittest.mock import patch

    f = tmp_path / "peli.mkv"
    f.write_bytes(b"x")
    iid = _movie_with_path(db_conn, str(f))
    job_id = _failed_job_row(db_conn, iid, status="cancelled")

    en_el_paso = threading.Event()
    seguir = threading.Event()

    def preparando(_job_id):
        en_el_paso.set()
        seguir.wait(timeout=5)

    with patch.object(uq, "_run_queued_job", preparando):
        hilo = threading.Thread(target=uq._correr_trabajo, args=(job_id,))
        hilo.start()
        assert en_el_paso.wait(timeout=5)

        assert uq.trabajo_activo(db_conn, iid)["id"] == job_id
        reintento = uq.queue_retry_for_job(job_id, conn=db_conn)
        assert reintento["status"] == "blocked"
        assert "terminando" in reintento["errors"][0]

        seguir.set()
        hilo.join(timeout=5)

    assert uq.trabajo_activo(db_conn, iid) is None


# ---------------------------------------------------------------------------
# Jobs que se quedaron a medias al pararse la aplicación
# ---------------------------------------------------------------------------

def _seed_job(conn, status, stage="remux"):
    cur = conn.execute(
        "INSERT INTO library_items(item_type,title,local_status,path) "
        "VALUES ('movie','Peli','Disponible','/data/peli.mkv')")
    cur = conn.execute(
        """INSERT INTO upload_jobs(library_item_id, title, path, status, stage)
           VALUES (?, 'Peli', '/data/peli.mkv', ?, ?)""", (cur.lastrowid, status, stage))
    conn.commit()
    return cur.lastrowid


def test_interrupted_jobs_are_marked_failed_on_boot(db_conn):
    """Un job en estado activo depende de un hilo o un subproceso de ESTE
    proceso. Si la aplicación acaba de arrancar, ninguno existe: murieron con
    el proceso anterior, pero la fila sobrevivió. Sin esto, un
    `docker compose down` a media subida lo dejaba congelado para siempre."""
    from emuwarez_uploadrr.services.upload_queue import reconcile_interrupted_jobs, ACTIVE_JOB_STATUSES
    ids = {estado: _seed_job(db_conn, estado) for estado in sorted(ACTIVE_JOB_STATUSES)}

    assert reconcile_interrupted_jobs(conn=db_conn) == len(ids)

    for estado, job_id in ids.items():
        row = db_conn.execute("SELECT status, error_message FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
        assert row["status"] == "failed", f"{estado} no se reconcilió"
        # 'failed' y no 'cancelled' porque nadie los canceló: se interrumpieron.
        # Y failed es lo que enciende el botón Reintentar.
        assert "Interrumpido" in (row["error_message"] or "")


def test_reconciling_leaves_finished_jobs_alone(db_conn):
    """Lo que ya terminó no se toca: reconciliar no puede reescribir el
    historial de subidas que salieron bien."""
    from emuwarez_uploadrr.services.upload_queue import reconcile_interrupted_jobs
    ids = {estado: _seed_job(db_conn, estado) for estado in ("completed", "failed", "cancelled")}

    assert reconcile_interrupted_jobs(conn=db_conn) == 0

    for estado, job_id in ids.items():
        row = db_conn.execute("SELECT status FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
        assert row["status"] == estado


def test_reconciling_an_empty_queue_is_a_no_op(db_conn):
    from emuwarez_uploadrr.services.upload_queue import reconcile_interrupted_jobs
    assert reconcile_interrupted_jobs(conn=db_conn) == 0


def test_the_reconciliation_actually_runs_when_the_app_boots(db_conn, isolated_db):
    """Lo de arriba prueba la función; esto prueba que está enchufada. Un
    arreglo que no se ejecuta no arregla nada."""
    import os
    from fastapi.testclient import TestClient
    from emuwarez_uploadrr.web.app import app
    os.environ["CONFIG_DIR"] = str(isolated_db)
    job_id = _seed_job(db_conn, "preparing")

    # El lifespan (y con él la reconciliación) solo corre al entrar en el
    # contexto del cliente.
    with TestClient(app):
        pass

    row = db_conn.execute("SELECT status FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
    assert row["status"] == "failed"


# ---------------------------------------------------------------------------
# Lo que recibe Uploadrr: el enlace de la carpeta de subidas
# ---------------------------------------------------------------------------

def _correr_cola_hasta_el_inicio(db_conn, tmp_path, monkeypatch, *, enlace_duro=True, origen=None):
    """Pasa un trabajo por toda la cola (con los pasos pesados simulados) y
    devuelve lo que hay en la fila justo cuando se arranca Uploadrr."""
    import errno
    import os

    from emuwarez_uploadrr.services import carpeta_subida as cs
    from emuwarez_uploadrr.services.settings import set_setting

    lib = tmp_path / "lib"
    lib.mkdir()
    f = lib / "Movie.2024.mkv"
    f.write_bytes(b"x" * 100)
    monkeypatch.setattr(cs, "RAIZ_SUBIDAS", str(tmp_path / "uploads"))
    if not enlace_duro:
        def sin_enlace_duro(*a, **k):
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        monkeypatch.setattr(cs.os, "link", sin_enlace_duro)

    iid = _movie_with_path(db_conn, str(f))
    db_conn.execute("UPDATE library_items SET prepared_path = ?, tmdb_id = '1' WHERE id = ?", (str(f), iid))
    jid = _queued_job_row(db_conn, iid, str(f))
    (tmp_path / "U").mkdir()
    (tmp_path / "U" / "upload.py").write_text("")
    for k, v in (("emu.api_key", "a"), ("tmdb.api_key", "b"), ("uploadrr.path", str(tmp_path / "U"))):
        set_setting(db_conn, k, v)
    db_conn.commit()

    visto = {}
    plan = {"status": "ready", "source_path": str(origen or f), "nombre": "Movie.2024.1080p.mkv",
            "proposal": None}

    def arrancar(job_id, **kw):
        from emuwarez_uploadrr.services.upload_execution import validate_upload_job_start
        fila = db_conn.execute("SELECT prepared_path, status FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
        visto.update(dict(fila))
        visto["errores"] = validate_upload_job_start(job_id, conn=db_conn)["errors"]
        return {"error": None}

    with patch("emuwarez_uploadrr.services.upload_execution.start_upload_job", arrancar), \
         patch("emuwarez_uploadrr.services.nomenclature.build_nomenclature_apply_plan", lambda *a, **k: plan), \
         patch("emuwarez_uploadrr.services.mkv_remux.modo_pistas", lambda c: "ninguno"):
        uq._run_queued_job(jid)
    # La cola cede su plaza al hilo de Uploadrr, que aquí no existe.
    from emuwarez_uploadrr.services.upload_execution import _upload_concurrency_gate
    _upload_concurrency_gate.release()
    visto["uploads"] = str(tmp_path / "uploads")
    visto["biblioteca"] = str(f)
    assert os.path.exists(str(f))
    return visto


@pytest.mark.usefixtures("ficheros_de_mentira")
def test_uploadrr_recibe_el_enlace_de_la_carpeta_de_subidas(db_conn, tmp_path, monkeypatch):
    """_populate_ready escribía en prepared_path la ruta de la biblioteca justo
    después de que el paso anterior dejara ahí el enlace. El enlace lleva el
    nombre de eMuwarez y el original conserva el suyo."""
    visto = _correr_cola_hasta_el_inicio(db_conn, tmp_path, monkeypatch)
    assert visto["status"] == "ready"
    assert visto["prepared_path"] == str(Path(visto["uploads"]) / "Movie.2024.1080p.mkv")
    assert visto["errores"] == []
    assert [p.name for p in Path(visto["biblioteca"]).parent.iterdir()] == ["Movie.2024.mkv"]


@pytest.mark.usefixtures("ficheros_de_mentira")
def test_no_se_enlaza_un_fichero_fuera_de_allowed_roots(db_conn, tmp_path, monkeypatch):
    """La ruta que se enlaza se vuelve a comprobar: no tiene por qué ser la
    misma que pasó la comprobación de integridad."""
    from emuwarez_uploadrr.services import uploadrr_contract
    monkeypatch.setattr(uploadrr_contract, "DEFAULT_ALLOWED_ROOTS", [str(tmp_path / "lib")])
    fuera = tmp_path / "fuera.mkv"
    fuera.write_bytes(b"x" * 100)

    visto = _correr_cola_hasta_el_inicio(db_conn, tmp_path, monkeypatch, origen=fuera)
    assert "status" not in visto  # Uploadrr no llega a arrancar
    job = db_conn.execute("SELECT status, error_message FROM upload_jobs").fetchone()
    assert job["status"] == "failed" and "allowed_roots" in job["error_message"]
    assert not (tmp_path / "uploads").exists() or not any((tmp_path / "uploads").iterdir())


@pytest.mark.usefixtures("ficheros_de_mentira")
def test_un_enlace_simbolico_en_la_carpeta_de_subidas_vale_para_subir(db_conn, tmp_path, monkeypatch):
    """Con /config y /data en montajes distintos no cabe un enlace duro."""
    import os

    visto = _correr_cola_hasta_el_inicio(db_conn, tmp_path, monkeypatch, enlace_duro=False)
    assert os.path.islink(visto["prepared_path"])
    assert Path(visto["prepared_path"]).is_relative_to(visto["uploads"])
    assert visto["errores"] == []


# ---------------------------------------------------------------------------
# La fase de nomenclatura falla con el motivo, sin tocar nada
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("ficheros_de_mentira")
@pytest.mark.parametrize("respuesta, esperado", [
    (RuntimeError("boom"), "Error aplicando la nomenclatura: boom"),
    ({"status": "blocked", "errors": ["propuesta bloqueada"]}, "No se pudo aplicar la nomenclatura: propuesta bloqueada"),
])
def test_un_fallo_al_calcular_el_nombre_para_la_subida(db_conn, tmp_path, monkeypatch, respuesta, esperado):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 100)
    iid = _movie_with_path(db_conn, str(f))
    job_id = _queued_job_row(db_conn, iid, path=str(f))
    monkeypatch.setattr(uq, "_check_generic_upload_preconditions", lambda *a, **k: True)

    def plan(*a, **k):
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta
    monkeypatch.setattr("emuwarez_uploadrr.services.nomenclature.build_nomenclature_apply_plan", plan)

    uq._run_queued_job(job_id)

    job = db_conn.execute("SELECT status, error_message FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
    assert job["status"] == "failed" and esperado in job["error_message"]
    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".mkv"] == ["movie.mkv"]


def test_un_fallo_al_calcular_el_pack(db_conn, monkeypatch):
    season_id, _ids = _seed_season_with_episodes(db_conn, n=1)
    job_id = _queued_job_row(db_conn, season_id, path="")
    monkeypatch.setattr(uq, "_check_season_integrity", lambda *a, **k: True)
    monkeypatch.setattr(uq, "_check_generic_upload_preconditions", lambda *a, **k: True)

    def plan(*a, **k):
        raise RuntimeError("boom")
    import emuwarez_uploadrr.services.season_pack as season_pack_mod
    monkeypatch.setattr(season_pack_mod, "build_season_pack_plan", plan)

    uq._run_queued_job(job_id)

    job = db_conn.execute("SELECT status, error_message FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()
    assert job["status"] == "failed"
    assert "Error aplicando la nomenclatura del pack de temporada: boom" in job["error_message"]


def test_preparar_el_fichero_cuenta_el_idioma_elegido(tmp_path, monkeypatch):
    """Si lo único que cambia es el idioma de una pista sin idioma, el plan que
    decide si se editan las pistas tiene que verlo; si no, no se escribe."""
    from emuwarez_uploadrr.services import mkv_remux

    class _Visto(Exception):
        pass

    def _plan(*a, **kw):
        raise _Visto(kw)
    monkeypatch.setattr(mkv_remux, "build_remux_plan", _plan)
    origen = tmp_path / "peli.mkv"
    origen.write_bytes(b"x")
    with pytest.raises(_Visto) as visto:
        uq._preparar_fichero(1, 1, str(origen), str(tmp_path / "subida.mkv"), "solo_renombrar", None,
                             overrides={"5": {"language": "spa"}})
    assert visto.value.args[0]["idiomas"] == {5: "spa"}
