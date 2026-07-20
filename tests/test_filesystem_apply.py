"""Tests for filesystem_apply service."""
from emuwarez_uploadrr.services.filesystem_apply import ensure_path_under_base


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
