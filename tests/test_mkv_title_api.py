"""API tests for Phase 10A MKV title endpoints."""
from __future__ import annotations

from unittest.mock import patch, MagicMock



def _seed_item(conn_ctx, title="Film", prepared_path=None, torrent_name=None):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.web.runtime import _db_path
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with connect(_db_path()) as conn:
        init_db(conn)
        conn.execute(
            "INSERT INTO library_items (title, item_type, local_status, prepared_path) VALUES (?,?,?,?)",
            (title, "movie", "downloaded", prepared_path),
        )
        conn.commit()
        item_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
        if torrent_name:
            conn.execute(
                """INSERT INTO nomenclature_proposals
                   (library_item_id, status, proposed_filename, proposed_title, created_at, updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (item_id, "valid", torrent_name, title, now, now),
            )
            conn.commit()
    return item_id


def test_preview_mkv_title_requires_auth(client):
    resp = client.get("/api/library/1/mkv-title/preview")
    assert resp.status_code == 401


def test_preview_mkv_title_not_found(client, auth_headers):
    resp = client.get("/api/library/9999/mkv-title/preview", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") in ("blocked", "error")


def test_preview_mkv_title_no_prepared_path(client, auth_headers, tmp_path):
    item_id = _seed_item(None, title="Film", prepared_path=None,
                         torrent_name="Film 2024 1080p BluRay - EMUWAREZ")
    resp = client.get(f"/api/library/{item_id}/mkv-title/preview", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "blocked"


def test_preview_mkv_title_with_mkv(client, auth_headers, tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv content")

    item_id = _seed_item(None, title="Film", prepared_path=str(mkv_file),
                         torrent_name="Film 2024 1080p BluRay - EMUWAREZ")

    with patch("emuwarez_uploadrr.services.mkv_title.check_mkvpropedit_available",
               return_value={"available": False, "path": None}):
        resp = client.get(f"/api/library/{item_id}/mkv-title/preview", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert "internal_mkv_title" in data
    assert data["internal_mkv_title"] == "Film.2024.1080p.BluRay.-.EMUWAREZ"


def test_apply_mkv_title_requires_auth(client):
    resp = client.post("/api/library/1/mkv-title/apply", json={"dry_run": True})
    assert resp.status_code == 401


def test_apply_mkv_title_dry_run_no_subprocess(client, auth_headers, tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv content")

    item_id = _seed_item(None, title="Film", prepared_path=str(mkv_file),
                         torrent_name="Film 2024 1080p BluRay - EMUWAREZ")

    with patch("subprocess.run") as mock_run:
        resp = client.post(
            f"/api/library/{item_id}/mkv-title/apply",
            json={"dry_run": True, "apply": False, "confirmation": None},
            headers=auth_headers,
        )
        mock_run.assert_not_called()

    assert resp.status_code == 200


def test_apply_mkv_title_wrong_token_blocked(client, auth_headers, tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")

    item_id = _seed_item(None, title="Film", prepared_path=str(mkv_file),
                         torrent_name="Film 2024 1080p BluRay - EMUWAREZ")

    with patch("subprocess.run") as mock_run:
        resp = client.post(
            f"/api/library/{item_id}/mkv-title/apply",
            json={"dry_run": False, "apply": True, "confirmation": "WRONG"},
            headers=auth_headers,
        )
        mock_run.assert_not_called()

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") in ("blocked", "error")


def test_apply_mkv_title_correct_token_calls_mkvpropedit(client, auth_headers, tmp_path):
    mkv_file = tmp_path / "Film.2024.mkv"
    mkv_file.write_bytes(b"fake mkv")

    item_id = _seed_item(None, title="Film", prepared_path=str(mkv_file),
                         torrent_name="Film 2024 1080p BluRay - EMUWAREZ")

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run, \
         patch("emuwarez_uploadrr.services.mkv_title.check_mkvpropedit_available",
               return_value={"available": True, "path": "/usr/bin/mkvpropedit"}):
        resp = client.post(
            f"/api/library/{item_id}/mkv-title/apply",
            json={"dry_run": False, "apply": True, "confirmation": "APLICAR_TITULO_MKV"},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    resp.json()
    if mock_run.called:
        _, kwargs = mock_run.call_args
        assert not kwargs.get("shell", False)
