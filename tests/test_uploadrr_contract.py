"""Tests for the Uploadrr-EMU CLI contract (Phase 10E).

None of these tests execute any subprocess or touch a real Uploadrr/
installation — they only exercise pure command-building/validation
functions.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.uploadrr_contract import (
    DEFAULT_ALLOWED_ROOTS,
    build_uploadrr_emu_command,
    get_allowed_roots,
    path_within_allowed_roots,
    redact_uploadrr_command,
    render_command_preview,
    validate_uploadrr_emu_contract,
)


def _build(**overrides):
    args = dict(
        python_path="/usr/bin/python3",
        uploadrr_script_path="/opt/Uploadrr/upload.py",
        prepared_path="/data/prepared/Movie.2024.1080p.WEB-DL.mkv",
        torrent_name="Movie.2024.1080p.WEB-DL-EMUWAREZ",
        tmdb_id="12345",
        category="movie",
        resolution="1080p",
    )
    args.update(overrides)
    return build_uploadrr_emu_command(**args)


def test_command_is_a_list_of_strings():
    cmd = _build()
    assert isinstance(cmd, list)
    assert all(isinstance(part, str) for part in cmd)


def test_command_uses_tk_emu():
    cmd = _build()
    assert "-tk" in cmd
    assert cmd[cmd.index("-tk") + 1] == "EMU"


def test_command_includes_mt_torrent_name():
    cmd = _build(torrent_name="My.Custom.Title")
    assert "-mt" in cmd
    assert cmd[cmd.index("-mt") + 1] == "My.Custom.Title"


def test_command_includes_tmdb_id():
    cmd = _build(tmdb_id="999")
    assert "-tmdb" in cmd
    assert cmd[cmd.index("-tmdb") + 1] == "999"


def test_command_omits_tmdb_when_absent():
    cmd = _build(tmdb_id=None)
    assert "-tmdb" not in cmd


def test_command_includes_ua_flag():
    cmd = _build()
    assert "-ua" in cmd


def test_command_uses_c_movie():
    cmd = _build(category="movie")
    assert "-c" in cmd
    assert cmd[cmd.index("-c") + 1] == "movie"


def test_command_uses_c_tv():
    cmd = _build(category="tv")
    assert cmd[cmd.index("-c") + 1] == "tv"


def test_command_uses_res_resolution():
    cmd = _build(resolution="2160p")
    assert "-res" in cmd
    assert cmd[cmd.index("-res") + 1] == "2160p"


def _res_value(**overrides):
    cmd = _build(**overrides)
    return cmd[cmd.index("-res") + 1] if "-res" in cmd else None


def test_res_normalizes_uppercase_p_to_valid_choice():
    # Uploadrr lowercases internally, but we must never emit an out-of-choices
    # token; "1080P" -> "1080p".
    assert _res_value(resolution="1080P") == "1080p"


def test_res_unrecognized_value_collapses_to_other():
    # legacy.py::uploadrr_resolution behavior: anything not matching \d+p in the
    # choice set becomes "other" instead of crashing upload.py's argparse.
    for bad in ("1920x1080", "4K", "FHD", "1080"):
        assert _res_value(resolution=bad) == "other", bad


def test_res_omitted_when_empty():
    # Empty resolution must drop -res entirely (Uploadrr then auto-detects),
    # never emit `-res ""`.
    assert "-res" not in _build(resolution="")


def test_res_valid_choice_passthrough():
    for good in ("2160p", "1080i", "720p", "540p", "480i", "other"):
        assert _res_value(resolution=good) == good, good


def test_season_added_when_int():
    cmd = _build(season=2)
    assert "-season" in cmd
    assert cmd[cmd.index("-season") + 1] == "S02"


def test_episode_added_when_int():
    cmd = _build(episode=5)
    assert "-episode" in cmd
    assert cmd[cmd.index("-episode") + 1] == "E05"


def test_season_episode_absent_by_default():
    cmd = _build()
    assert "-season" not in cmd
    assert "-episode" not in cmd


@pytest.mark.parametrize(
    ("formato", "tipo"),
    [
        ("Full BluRay", "disc"),
        ("FDVD", "disc"),
        ("BDRemux", "remux"),
        ("BDReMux", "remux"),
        ("BluRay", "encode"),
        ("MHD", "encode"),
        ("WEB-DL", "webdl"),
        ("WEBRip", "webrip"),
        ("HDTV", "hdtv"),
    ],
)
def test_release_format_goes_as_t(formato, tipo):
    cmd = _build(release_format=formato)
    assert cmd[cmd.index("-t") + 1] == tipo


@pytest.mark.parametrize("formato", [None, "", "SD", "DVD", "bluray"])
def test_release_format_without_uploadrr_type_sends_no_t(formato):
    assert "-t" not in _build(release_format=formato)


def test_no_legacy_broken_flags_present():
    cmd = _build()
    joined = " ".join(cmd)
    assert "--tracker" not in joined
    assert "--category" not in joined
    assert "--resolution" not in joined


def test_prepared_path_is_positional_arg():
    cmd = _build(prepared_path="/data/prepared/x.mkv")
    assert "/data/prepared/x.mkv" in cmd


def test_render_command_preview_quotes_spaces():
    preview = render_command_preview(["python", "upload.py", "path with spaces"])
    assert '"path with spaces"' in preview


def test_redact_uploadrr_command_replaces_secret_values():
    cmd = ["python", "upload.py", "/x/secret123456.mkv"]
    redacted = redact_uploadrr_command(cmd, secrets=["secret123456"])
    assert "secret123456" not in " ".join(redacted)
    assert "***REDACTED***" in " ".join(redacted)


def test_redact_uploadrr_command_ignores_short_values():
    cmd = ["python", "-c", "tv"]
    redacted = redact_uploadrr_command(cmd, secrets=["tv"])
    assert redacted == cmd


# ---------------------------------------------------------------------------
# path_within_allowed_roots
# ---------------------------------------------------------------------------

def test_path_within_allowed_roots_true(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    target = root / "movie.mkv"
    target.write_bytes(b"\x00")
    assert path_within_allowed_roots(str(target), [str(root)])


def test_path_within_allowed_roots_false_outside(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    other = tmp_path / "other" / "movie.mkv"
    assert not path_within_allowed_roots(str(other), [str(root)])


def test_path_within_allowed_roots_blocks_traversal(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    (tmp_path / "secret").mkdir()
    traversal = str(root / ".." / "secret" / "movie.mkv")
    assert not path_within_allowed_roots(traversal, [str(root)])


def test_path_within_allowed_roots_empty_roots_never_grants_access():
    assert not path_within_allowed_roots("/anything", [])


# ---------------------------------------------------------------------------
# get_allowed_roots
# ---------------------------------------------------------------------------

def test_get_allowed_roots_defaults_to_data_when_never_set(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db, db_path
    conn = connect(db_path())
    init_db(conn)
    assert get_allowed_roots(conn) == DEFAULT_ALLOWED_ROOTS


def test_get_allowed_roots_respects_explicit_empty_list(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db, db_path
    from emuwarez_uploadrr.services.settings import set_setting
    conn = connect(db_path())
    init_db(conn)
    set_setting(conn, "uploadrr.allowed_roots", "[]")
    assert get_allowed_roots(conn) == []


def test_get_allowed_roots_respects_explicit_value(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db, db_path
    from emuwarez_uploadrr.services.settings import set_setting
    conn = connect(db_path())
    init_db(conn)
    set_setting(conn, "uploadrr.allowed_roots", '["/movies", "/tv"]')
    assert get_allowed_roots(conn) == ["/movies", "/tv"]


# ---------------------------------------------------------------------------
# validate_uploadrr_emu_contract
# ---------------------------------------------------------------------------

def _valid_contract_kwargs(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    prepared = root / "movie.mkv"
    prepared.write_bytes(b"\x00")
    python_bin = tmp_path / "python3"
    python_bin.write_text("#!/bin/sh\n")
    script = tmp_path / "upload.py"
    script.write_text("# fake")
    return dict(
        prepared_path=str(prepared),
        torrent_name="Movie.2024.1080p",
        tmdb_id="123",
        category="movie",
        resolution="1080p",
        allowed_roots=[str(root)],
        python_path=str(python_bin),
        uploadrr_script_path=str(script),
    )


def test_contract_valid_happy_path(tmp_path):
    result = validate_uploadrr_emu_contract(**_valid_contract_kwargs(tmp_path))
    assert result["valid"] is True
    assert result["errors"] == []


def test_contract_blocks_path_outside_allowed_roots(tmp_path):
    kwargs = _valid_contract_kwargs(tmp_path)
    outside = tmp_path / "outside.mkv"
    outside.write_bytes(b"\x00")
    kwargs["prepared_path"] = str(outside)
    result = validate_uploadrr_emu_contract(**kwargs)
    assert result["valid"] is False
    assert any("allowed_roots" in e for e in result["errors"])


def test_contract_blocks_missing_torrent_name(tmp_path):
    kwargs = _valid_contract_kwargs(tmp_path)
    kwargs["torrent_name"] = ""
    result = validate_uploadrr_emu_contract(**kwargs)
    assert result["valid"] is False
    assert any("título" in e.lower() for e in result["errors"])


def test_contract_blocks_invalid_category(tmp_path):
    kwargs = _valid_contract_kwargs(tmp_path)
    kwargs["category"] = "music"
    result = validate_uploadrr_emu_contract(**kwargs)
    assert result["valid"] is False
    assert any("category" in e.lower() for e in result["errors"])


def test_contract_reports_missing_python_path(tmp_path):
    kwargs = _valid_contract_kwargs(tmp_path)
    kwargs["python_path"] = str(tmp_path / "does-not-exist-python")
    result = validate_uploadrr_emu_contract(**kwargs)
    assert result["valid"] is False
    assert any("python_path" in e for e in result["errors"])


def test_contract_reports_missing_script(tmp_path):
    kwargs = _valid_contract_kwargs(tmp_path)
    kwargs["uploadrr_script_path"] = str(tmp_path / "does-not-exist" / "upload.py")
    result = validate_uploadrr_emu_contract(**kwargs)
    assert result["valid"] is False
    assert any("Uploadrr" in e for e in result["errors"])


def test_contract_warns_without_tmdb_id(tmp_path):
    kwargs = _valid_contract_kwargs(tmp_path)
    kwargs["tmdb_id"] = None
    result = validate_uploadrr_emu_contract(**kwargs)
    assert result["valid"] is True
    assert any("tmdb" in w.lower() for w in result["warnings"])


def test_season_zero_is_sent():
    cmd = _build(season=0, episode=1)
    assert cmd[cmd.index("-season") + 1] == "S00"
