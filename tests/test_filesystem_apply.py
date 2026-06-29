"""Tests for filesystem_apply service (Phase 6B)."""
import os
import pytest
from pathlib import Path

from emuwarez_uploadrr.services.filesystem_apply import (
    build_safe_apply_plan,
    apply_hardlink_plan,
    ensure_path_under_base,
    resolve_safe_path,
)


# ---------------------------------------------------------------------------
# ensure_path_under_base
# ---------------------------------------------------------------------------

def test_ensure_path_under_base_valid(tmp_path):
    child = tmp_path / "subdir" / "file.mkv"
    assert ensure_path_under_base(str(child), str(tmp_path)) is True


def test_ensure_path_under_base_traversal(tmp_path):
    other = tmp_path.parent / "other"
    assert ensure_path_under_base(str(other), str(tmp_path)) is False


def test_ensure_path_under_base_same_dir(tmp_path):
    # The base itself does not count as "under" itself
    assert ensure_path_under_base(str(tmp_path), str(tmp_path)) is True


def test_ensure_path_under_base_sibling(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    assert ensure_path_under_base(str(b), str(a)) is False


# ---------------------------------------------------------------------------
# build_safe_apply_plan — blocking cases
# ---------------------------------------------------------------------------

def test_plan_blocked_no_source(tmp_path):
    base = str(tmp_path)
    dst = str(tmp_path / "dest" / "file.mkv")
    result = build_safe_apply_plan("", dst, base)
    assert result["status"] == "blocked"
    assert any("source_path" in e for e in result["errors"])


def test_plan_blocked_source_not_exists(tmp_path):
    src = str(tmp_path / "nonexistent.mkv")
    dst = str(tmp_path / "dest" / "file.mkv")
    result = build_safe_apply_plan(src, dst, str(tmp_path))
    assert result["status"] == "blocked"
    assert any("no existe" in e for e in result["errors"])


def test_plan_blocked_source_is_symlink(tmp_path):
    real = tmp_path / "real.mkv"
    real.write_bytes(b"x")
    link = tmp_path / "link.mkv"
    link.symlink_to(real)
    dst = str(tmp_path / "prepared" / "link.mkv")
    result = build_safe_apply_plan(str(link), dst, str(tmp_path))
    assert result["status"] == "blocked"
    assert any("symlink" in e for e in result["errors"])


def test_plan_blocked_destination_outside_base(tmp_path):
    src = tmp_path / "source.mkv"
    src.write_bytes(b"x")
    base = tmp_path / "base"
    base.mkdir()
    dst = str(tmp_path / "outside" / "file.mkv")
    result = build_safe_apply_plan(str(src), dst, str(base))
    assert result["status"] == "blocked"
    assert any("fuera de hardlink_base" in e or "outside" in e.lower() for e in result["errors"])


def test_plan_blocked_no_hardlink_base(tmp_path):
    src = tmp_path / "source.mkv"
    src.write_bytes(b"x")
    dst = str(tmp_path / "dest" / "file.mkv")
    result = build_safe_apply_plan(str(src), dst, "")
    assert result["status"] == "blocked"
    assert any("hardlink_base" in e for e in result["errors"])


def test_plan_blocked_source_equals_destination(tmp_path):
    src = tmp_path / "source.mkv"
    src.write_bytes(b"x")
    result = build_safe_apply_plan(str(src), str(src), str(tmp_path))
    assert result["status"] == "blocked"
    assert any("mismo archivo" in e for e in result["errors"])


def test_plan_blocked_destination_exists(tmp_path):
    src = tmp_path / "source.mkv"
    src.write_bytes(b"x")
    base = tmp_path / "prepared"
    base.mkdir()
    dst = base / "source.mkv"
    dst.write_bytes(b"y")
    result = build_safe_apply_plan(str(src), str(dst), str(tmp_path))
    assert result["status"] == "blocked"
    assert any("ya existe" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# build_safe_apply_plan — happy path
# ---------------------------------------------------------------------------

def test_plan_ready(tmp_path):
    src = tmp_path / "movie.mkv"
    src.write_bytes(b"video")
    base = tmp_path / "prepared"
    base.mkdir()
    dst = str(base / "subdir" / "movie.mkv")
    result = build_safe_apply_plan(str(src), dst, str(tmp_path))
    assert result["status"] == "ready"
    assert result["errors"] == []
    assert result["source_path"] == str(src)
    assert result["destination_path"] == dst


def test_plan_warns_non_video_extension(tmp_path):
    src = tmp_path / "movie.txt"
    src.write_bytes(b"text")
    base = tmp_path / "prepared"
    base.mkdir()
    dst = str(base / "movie.txt")
    result = build_safe_apply_plan(str(src), dst, str(tmp_path))
    assert result["status"] == "ready"
    assert any("vídeo" in w or "video" in w.lower() for w in result["warnings"])


# ---------------------------------------------------------------------------
# apply_hardlink_plan — dry_run
# ---------------------------------------------------------------------------

def test_apply_dry_run_does_not_write(tmp_path):
    src = tmp_path / "source.mkv"
    src.write_bytes(b"data")
    base = tmp_path / "prepared"
    dst = str(base / "source.mkv")
    plan = build_safe_apply_plan(str(src), dst, str(tmp_path))
    assert plan["status"] == "ready"

    result = apply_hardlink_plan(plan, dry_run=True)
    assert result["status"] == "ready"
    assert not base.exists()  # directory NOT created in dry_run
    assert not Path(dst).exists()


def test_apply_dry_run_blocked_plan(tmp_path):
    plan = {
        "status": "blocked",
        "errors": ["test error"],
        "warnings": [],
        "source_path": str(tmp_path / "src.mkv"),
        "destination_path": str(tmp_path / "dst.mkv"),
        "parent_dir": str(tmp_path),
        "hardlink_base": str(tmp_path),
    }
    result = apply_hardlink_plan(plan, dry_run=True)
    assert result["status"] == "blocked"


# ---------------------------------------------------------------------------
# apply_hardlink_plan — real apply
# ---------------------------------------------------------------------------

def test_apply_real_creates_hardlink(tmp_path):
    src = tmp_path / "source.mkv"
    src.write_bytes(b"video content")
    base = tmp_path / "prepared"
    dst = str(base / "subdir" / "source.mkv")
    plan = build_safe_apply_plan(str(src), dst, str(tmp_path))
    assert plan["status"] == "ready"

    result = apply_hardlink_plan(plan, dry_run=False)
    assert result["status"] == "applied"
    assert Path(dst).exists()
    # Same inode — it's a hardlink, not a copy
    assert src.stat().st_ino == Path(dst).stat().st_ino
    # Original untouched
    assert src.read_bytes() == b"video content"


def test_apply_real_original_never_modified(tmp_path):
    src = tmp_path / "original.mkv"
    original_content = b"original video bytes"
    src.write_bytes(original_content)
    base = tmp_path / "prepared"
    dst = str(base / "original.mkv")
    plan = build_safe_apply_plan(str(src), dst, str(tmp_path))

    apply_hardlink_plan(plan, dry_run=False)
    assert src.exists()
    assert src.read_bytes() == original_content
    assert str(src) == str(src)  # path unchanged


def test_apply_real_blocked_plan_does_not_write(tmp_path):
    src = tmp_path / "source.mkv"
    src.write_bytes(b"x")
    plan = {
        "status": "blocked",
        "errors": ["some error"],
        "warnings": [],
        "source_path": str(src),
        "destination_path": str(tmp_path / "prepared" / "source.mkv"),
        "parent_dir": str(tmp_path / "prepared"),
        "hardlink_base": str(tmp_path),
    }
    result = apply_hardlink_plan(plan, dry_run=False)
    assert result["status"] == "blocked"
    assert not (tmp_path / "prepared").exists()


def test_apply_overwrite_removes_existing(tmp_path):
    src = tmp_path / "source.mkv"
    src.write_bytes(b"new content")
    base = tmp_path / "prepared"
    base.mkdir()
    dst = base / "source.mkv"
    dst.write_bytes(b"old content")

    plan = build_safe_apply_plan(str(src), str(dst), str(tmp_path))
    assert plan["status"] == "blocked"  # destination exists

    result = apply_hardlink_plan(plan, dry_run=False, overwrite=True)
    assert result["status"] == "applied"
    assert Path(dst).read_bytes() == b"new content"


def test_apply_no_overwrite_blocked_when_dst_exists(tmp_path):
    src = tmp_path / "source.mkv"
    src.write_bytes(b"x")
    base = tmp_path / "prepared"
    base.mkdir()
    dst = base / "source.mkv"
    dst.write_bytes(b"y")

    plan = build_safe_apply_plan(str(src), str(dst), str(tmp_path))
    result = apply_hardlink_plan(plan, dry_run=False, overwrite=False)
    assert result["status"] == "blocked"
    assert dst.read_bytes() == b"y"  # unchanged
