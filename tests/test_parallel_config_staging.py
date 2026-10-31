"""Reference-counted config staging so uploads can run in parallel safely.

The staged config.yaml (TMDb/EMU keys) is shared: the first concurrent upload
stages it, the last one to finish restores it. In between, overlapping jobs
must NOT re-stage or restore it out from under each other.
"""
from __future__ import annotations

import emuwarez_uploadrr.services.upload_execution as ue


def _patch(monkeypatch):
    calls = {"stage": 0, "restore": 0}

    def fake_stage(job_id, cwd):
        calls["stage"] += 1
        return ue.default_uploadrr_config_path(cwd)

    def fake_restore(job_id, config_path):
        calls["restore"] += 1

    monkeypatch.setattr(ue, "_stage_uploadrr_config", fake_stage)
    monkeypatch.setattr(ue, "_restore_uploadrr_config", fake_restore)
    monkeypatch.setattr(ue, "append_upload_log", lambda *a, **k: None)
    # start from a clean refcount table
    ue._config_stage_refcount.clear()
    return calls


def test_two_overlapping_uploads_restore_once(monkeypatch):
    calls = _patch(monkeypatch)
    cwd = "/tmp/fake-uploadrr"

    a = ue._acquire_staged_config(1, cwd)   # first: stages
    b = ue._acquire_staged_config(2, cwd)   # second overlapping: recalcula (solo escribe si cambió), no restaura
    assert calls["stage"] == 2
    assert a is not None and b is not None

    ue._release_staged_config(1, a)         # first finishes: NOT restored yet
    assert calls["restore"] == 0
    ue._release_staged_config(2, b)         # last finishes: restored now
    assert calls["restore"] == 1


def test_sequential_uploads_stage_and_restore_each(monkeypatch):
    calls = _patch(monkeypatch)
    cwd = "/tmp/fake-uploadrr"

    a = ue._acquire_staged_config(1, cwd)
    ue._release_staged_config(1, a)
    b = ue._acquire_staged_config(2, cwd)
    ue._release_staged_config(2, b)
    assert calls["stage"] == 2
    assert calls["restore"] == 2


def test_nothing_to_stage_is_not_refcounted(monkeypatch):
    calls = _patch(monkeypatch)
    monkeypatch.setattr(ue, "_stage_uploadrr_config", lambda job_id, cwd: None)
    a = ue._acquire_staged_config(1, "/tmp/fake-uploadrr")
    assert a is None
    ue._release_staged_config(1, a)         # no-op
    assert calls["restore"] == 0
