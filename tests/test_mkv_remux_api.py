"""API tests for Phase 12A track reorder/rename (mkv_remux) endpoints."""
from __future__ import annotations

from unittest.mock import patch, MagicMock


_SAMPLE_MKV_JSON = {
    "tracks": [
        {"id": 0, "type": "video", "codec": "AVC/H.264/MPEG-4p10",
         "properties": {"pixel_dimensions": "1920x1080"}},
        {"id": 1, "type": "audio", "codec": "AC-3",
         "properties": {"language": "eng", "audio_channels": 2}},
        {"id": 2, "type": "audio", "codec": "AC-3",
         "properties": {"language": "spa", "audio_channels": 6}},
    ]
}


def _seed_item(prepared_path=None):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.web.runtime import _db_path
    with connect(_db_path()) as conn:
        init_db(conn)
        conn.execute(
            "INSERT INTO library_items (title, item_type, local_status, prepared_path) VALUES (?,?,?,?)",
            ("Film", "movie", "downloaded", prepared_path),
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]


def test_preview_track_remux_requires_auth(client):
    resp = client.get("/api/library/1/track-remux/preview")
    assert resp.status_code == 401


def test_preview_track_remux_not_found(client, auth_headers):
    resp = client.get("/api/library/9999/track-remux/preview", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json().get("status") == "blocked"


def test_preview_track_remux_no_mkvmerge(client, auth_headers, tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")
    item_id = _seed_item(prepared_path=str(mkv_file))

    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available",
               return_value={"available": False, "path": None}):
        resp = client.get(f"/api/library/{item_id}/track-remux/preview", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "blocked"
    assert any("mkvmerge" in e.lower() for e in data["errors"])


def test_preview_track_remux_ready(client, auth_headers, tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")
    item_id = _seed_item(prepared_path=str(mkv_file))

    with patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available",
               return_value={"available": True, "path": "/usr/bin/mkvmerge"}), \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json",
               return_value={"ok": True, "data": _SAMPLE_MKV_JSON}):
        resp = client.get(f"/api/library/{item_id}/track-remux/preview", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    audio_names = [t["new_name"] for t in data["ordered_tracks"] if t["type"] == "audio"]
    assert audio_names == ["Español (Castellano) - DD 5.1", "Inglés - DD 2.0"]


def test_apply_track_remux_requires_auth(client):
    resp = client.post("/api/library/1/track-remux/apply", json={"dry_run": True})
    assert resp.status_code == 401


def test_apply_track_remux_dry_run_no_subprocess(client, auth_headers, tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")
    item_id = _seed_item(prepared_path=str(mkv_file))

    with patch("emuwarez_uploadrr.services.mkv_remux.subprocess.run") as mock_run, \
         patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available",
               return_value={"available": True, "path": "/usr/bin/mkvmerge"}), \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json",
               return_value={"ok": True, "data": _SAMPLE_MKV_JSON}):
        resp = client.post(
            f"/api/library/{item_id}/track-remux/apply",
            json={"dry_run": True, "apply": False, "confirmation": None},
            headers=auth_headers,
        )
        mock_run.assert_not_called()

    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_apply_track_remux_wrong_token_blocked(client, auth_headers, tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")
    item_id = _seed_item(prepared_path=str(mkv_file))

    with patch("emuwarez_uploadrr.services.mkv_remux.subprocess.run") as mock_run, \
         patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available",
               return_value={"available": True, "path": "/usr/bin/mkvmerge"}), \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json",
               return_value={"ok": True, "data": _SAMPLE_MKV_JSON}):
        resp = client.post(
            f"/api/library/{item_id}/track-remux/apply",
            json={"dry_run": False, "apply": True, "confirmation": "WRONG"},
            headers=auth_headers,
        )
        mock_run.assert_not_called()

    assert resp.status_code == 200
    assert resp.json()["status"] == "blocked"


def test_apply_track_remux_correct_token_calls_mkvmerge(client, auth_headers, tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv original")
    item_id = _seed_item(prepared_path=str(mkv_file))

    def _fake_run(args, **kwargs):
        out_idx = args.index("-o") + 1
        with open(args[out_idx], "wb") as fh:
            fh.write(b"fake mkv remuxed")
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        m.stderr = ""
        return m

    with patch("emuwarez_uploadrr.services.mkv_remux.subprocess.run", side_effect=_fake_run) as mock_run, \
         patch("emuwarez_uploadrr.services.mkv_remux.check_mkvmerge_available",
               return_value={"available": True, "path": "/usr/bin/mkvmerge"}), \
         patch("emuwarez_uploadrr.services.mkv_remux.read_tracks_json",
               return_value={"ok": True, "data": _SAMPLE_MKV_JSON}):
        resp = client.post(
            f"/api/library/{item_id}/track-remux/apply",
            json={"dry_run": False, "apply": True, "confirmation": "REORDENAR_PISTAS"},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "applied"
    assert mkv_file.read_bytes() == b"fake mkv remuxed"
    _, kwargs = mock_run.call_args
    assert not kwargs.get("shell", False)
