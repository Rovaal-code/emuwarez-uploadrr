"""MediaInfo-based nomenclature check: pure comparison + DB rollup/pending.

The MediaInfo read itself needs real files + the `mediainfo` binary, so it is
not exercised here; we cover the deterministic pieces: token comparison,
group/provider handling, pending counting and the season/series rollup.
"""
from __future__ import annotations

import emuwarez_uploadrr.services.nomenclature_check as nc


# --- pure comparison --------------------------------------------------------

_EXP = "Dune.Parte.Dos.2024.2160p.WEB-DL.HEVC.DUAL.DDP.5.1"


def test_compare_exact_with_group():
    assert nc.compare("Dune.Parte.Dos.2024.2160p.WEB-DL.HEVC.DUAL.DDP.5.1-XYZ.mkv", _EXP) == (True, [])


def test_compare_optional_provider_still_matches():
    ok, diff = nc.compare("Dune.Parte.Dos.2024.2160p.AMZN.WEB-DL.HEVC.DUAL.DDP.5.1-GRP.mkv", _EXP)
    assert ok and diff == []


def test_compare_without_group_matches():
    # Group is optional; the name must still validate.
    assert nc.compare("Dune.Parte.Dos.2024.2160p.WEB-DL.HEVC.DUAL.DDP.5.1.mkv", _EXP)[0]


def test_compare_wrong_resolution_flags_diff():
    ok, diff = nc.compare("Dune.Parte.Dos.2024.1080p.WEB-DL.HEVC.DUAL.DDP.5.1-X.mkv", _EXP)
    assert not ok and any("2160p" in d for d in diff)


def test_strip_group_keeps_web_dl_and_dts_hd():
    assert nc._strip_group("A.B.2024.2160p.WEB-DL.HEVC.5.1-EMUWAREZ") == "A.B.2024.2160p.WEB-DL.HEVC.5.1"
    assert nc._strip_group("A.B.2024.1080p.BluRay.AVC.DTS-HD.MA.5.1-GRP") == "A.B.2024.1080p.BluRay.AVC.DTS-HD.MA.5.1"


# --- DB rollup / pending ----------------------------------------------------

def _conn():
    from emuwarez_uploadrr.database import connect
    c = connect(":memory:")
    from emuwarez_uploadrr.database import init_db
    init_db(c)
    return c


def _add(conn, **kw):
    kw.setdefault("item_type", "episode")
    kw.setdefault("local_status", "Disponible")
    cols = ", ".join(kw)
    ph = ", ".join("?" for _ in kw)
    cur = conn.execute(f"INSERT INTO library_items ({cols}) VALUES ({ph})", tuple(kw.values()))
    return cur.lastrowid


def test_count_pending_only_available_unchecked():
    conn = _conn()
    season = _add(conn, item_type="season", title="S1", local_status="Disponible", path=None)
    _add(conn, parent_id=season, title="E1", path="/x/e1.mkv", nomenclature_status="No comprobada")
    _add(conn, parent_id=season, title="E2", path="/x/e2.mkv", nomenclature_status="Correcta")
    _add(conn, parent_id=season, title="E3", path=None, local_status="Ausente", nomenclature_status="N/A")
    pending, available, seasons = nc.count_pending(conn, season, "season")
    assert (pending, available) == (1, 2)  # E3 missing → not available


def test_rollup_unchecked_when_any_pending():
    from emuwarez_uploadrr.web.api.library import _nomenclature_rollup
    conn = _conn()
    season = _add(conn, item_type="season", title="S1", path=None)
    _add(conn, parent_id=season, title="E1", path="/x/e1.mkv", nomenclature_status="Correcta")
    _add(conn, parent_id=season, title="E2", path="/x/e2.mkv", nomenclature_status="No comprobada")
    assert _nomenclature_rollup(conn, season, "season") == "No comprobada"


def test_rollup_correcta_when_all_checked_correct():
    from emuwarez_uploadrr.web.api.library import _nomenclature_rollup
    conn = _conn()
    season = _add(conn, item_type="season", title="S1", path=None)
    _add(conn, parent_id=season, title="E1", path="/x/e1.mkv", nomenclature_status="Correcta")
    _add(conn, parent_id=season, title="E2", path="/x/e2.mkv", nomenclature_status="Correcta")
    _add(conn, parent_id=season, title="E3", path=None, local_status="Ausente", nomenclature_status="N/A")
    assert _nomenclature_rollup(conn, season, "season") == "Correcta"


def test_rollup_parcial_mix_correct_and_not_adapted():
    from emuwarez_uploadrr.web.api.library import _nomenclature_rollup
    conn = _conn()
    season = _add(conn, item_type="season", title="S1", path=None)
    _add(conn, parent_id=season, title="E1", path="/x/e1.mkv", nomenclature_status="Correcta")
    _add(conn, parent_id=season, title="E2", path="/x/e2.mkv", nomenclature_status="No adaptada")
    assert _nomenclature_rollup(conn, season, "season") == "Parcial"


def test_rollup_na_when_no_available_files():
    from emuwarez_uploadrr.web.api.library import _nomenclature_rollup
    conn = _conn()
    season = _add(conn, item_type="season", title="S1", path=None)
    _add(conn, parent_id=season, title="E1", path=None, local_status="Ausente", nomenclature_status="N/A")
    assert _nomenclature_rollup(conn, season, "season") == "N/A"


def test_check_item_skips_unavailable():
    # No available files → nothing checked, no MediaInfo invoked.
    conn = _conn()
    season = _add(conn, item_type="season", title="S1", path=None)
    _add(conn, parent_id=season, title="E1", path=None, local_status="Ausente", nomenclature_status="N/A")
    summary = nc.check_item(conn, season)
    assert summary["checked"] == 0
