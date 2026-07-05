"""Tests for Phase 11C onboarding wizard additions:
new step order (admin -> emu -> instances -> tmdb -> complete), and the
nomenclature/hardlink-strategy step. No dedicated Uploadrr step (removed —
configurable later from Settings, service ships with sensible defaults).
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# next_step() reordering
# ---------------------------------------------------------------------------

def test_next_step_order_after_admin(client, auth_headers):
    resp = client.get("/api/setup/status")
    assert resp.json()["next_step"] == "emu"


def test_complete_succeeds_with_nothing_else_configured(client, auth_headers):
    """Every step besides creating the admin is skippable — completing
    setup right after admin creation, with eMuwarez/instances/TMDb/Uploadrr
    all left unconfigured, must succeed rather than block with 'Pasos
    pendientes'."""
    resp = client.post("/api/setup/complete", headers=auth_headers)
    assert resp.status_code == 200

    status_resp = client.get("/api/setup/status")
    data = status_resp.json()
    assert data["initialized"] is True
    assert data["next_step"] is None


def test_next_step_order_after_emu(client, auth_headers):
    client.post("/api/setup/emu", json={"api_key": "emukey"}, headers=auth_headers)
    resp = client.get("/api/setup/status")
    assert resp.json()["next_step"] == "instances"


def test_next_step_order_after_instances(client, auth_headers):
    client.post("/api/setup/emu", json={"api_key": "emukey"}, headers=auth_headers)
    client.post(
        "/api/setup/instances",
        json={"type": "radarr", "name": "R1", "url": "http://r:7878", "api_key": "k"},
        headers=auth_headers,
    )
    resp = client.get("/api/setup/status")
    assert resp.json()["next_step"] == "tmdb"


def test_next_step_order_after_tmdb(client, auth_headers):
    client.post("/api/setup/emu", json={"api_key": "emukey"}, headers=auth_headers)
    client.post(
        "/api/setup/instances",
        json={"type": "radarr", "name": "R1", "url": "http://r:7878", "api_key": "k"},
        headers=auth_headers,
    )
    client.post("/api/setup/tmdb", json={"api_key": "tmdbkey"}, headers=auth_headers)
    resp = client.get("/api/setup/status")
    assert resp.json()["next_step"] == "complete"



# ---------------------------------------------------------------------------
# POST /api/setup/nomenclature
# ---------------------------------------------------------------------------

def test_setup_nomenclature_requires_auth(client):
    resp = client.post("/api/setup/nomenclature", json={})
    assert resp.status_code == 401


def test_setup_nomenclature_default_uses_hardlinks_no_confirmation_needed(client, auth_headers):
    resp = client.post(
        "/api/setup/nomenclature",
        json={"default_release_tag": "MYTAG", "hardlink_base": "/data/uploads/emu"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


def test_setup_nomenclature_disable_hardlinks_without_confirmation_returns_400(client, auth_headers):
    resp = client.post(
        "/api/setup/nomenclature",
        json={"default_release_tag": "TAG", "use_hardlinks": False},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "DESACTIVAR_HARDLINKS" in resp.json()["detail"]


def test_setup_nomenclature_disable_hardlinks_wrong_confirmation_returns_400(client, auth_headers):
    resp = client.post(
        "/api/setup/nomenclature",
        json={"default_release_tag": "TAG", "use_hardlinks": False, "confirmation": "WRONG"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_setup_nomenclature_disable_hardlinks_with_correct_confirmation_persists(client, auth_headers):
    resp = client.post(
        "/api/setup/nomenclature",
        json={"default_release_tag": "TAG", "use_hardlinks": False, "confirmation": "DESACTIVAR_HARDLINKS"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    settings_resp = client.get("/api/settings", headers=auth_headers)
    assert settings_resp.json()["default_release_tag"] == "TAG"


def test_setup_nomenclature_persists_hardlink_base_setting(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    client.post(
        "/api/setup/nomenclature",
        json={"default_release_tag": "TAG", "hardlink_base": "/data/uploads/emu"},
        headers=auth_headers,
    )
    conn = connect(db_path())
    init_db(conn)
    row = conn.execute("SELECT value FROM settings WHERE key = 'hardlink_base'").fetchone()
    assert row["value"] == "/data/uploads/emu"
    row2 = conn.execute("SELECT value FROM settings WHERE key = 'nomenclature.use_hardlinks'").fetchone()
    assert row2["value"] == "true"
    conn.close()


def test_setup_nomenclature_persists_provider_priority_order(client, auth_headers):
    import json as _json
    from emuwarez_uploadrr.database import connect, db_path, init_db
    resp = client.post(
        "/api/setup/nomenclature",
        json={"default_release_tag": "TAG", "provider_priority_order": ["NF", "AMZN", "DSNP"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    conn = connect(db_path())
    init_db(conn)
    row = conn.execute("SELECT value FROM settings WHERE key = 'provider_priority_order'").fetchone()
    assert _json.loads(row["value"]) == ["NF", "AMZN", "DSNP"]
    conn.close()

    settings_resp = client.get("/api/settings", headers=auth_headers)
    assert settings_resp.json()["provider_priority_order"] == ["NF", "AMZN", "DSNP"]


def test_setup_nomenclature_rejects_invalid_provider_code(client, auth_headers):
    resp = client.post(
        "/api/setup/nomenclature",
        json={"default_release_tag": "TAG", "provider_priority_order": ["NOT_A_CODE"]},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "NOT_A_CODE" in resp.json()["detail"]


def test_setup_nomenclature_rejects_duplicate_provider_codes(client, auth_headers):
    resp = client.post(
        "/api/setup/nomenclature",
        json={"default_release_tag": "TAG", "provider_priority_order": ["AMZN", "AMZN"]},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "duplicados" in resp.json()["detail"]


def test_setup_nomenclature_without_provider_priority_leaves_setting_untouched(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    resp = client.post(
        "/api/setup/nomenclature",
        json={"default_release_tag": "TAG"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    conn = connect(db_path())
    init_db(conn)
    row = conn.execute("SELECT value FROM settings WHERE key = 'provider_priority_order'").fetchone()
    conn.close()
    # Untouched means either absent, or (if a prior test in this session set
    # it) not overwritten by this call — either way this call must not have
    # written an empty/garbage value.
    if row is not None:
        assert row["value"]


# ---------------------------------------------------------------------------
# Full flow — new step order end to end, including optional steps
# ---------------------------------------------------------------------------

def test_full_setup_flow_new_order_with_nomenclature(client, auth_headers):
    client.post("/api/setup/emu", json={"api_key": "emu_key_e2e"}, headers=auth_headers)
    client.post(
        "/api/setup/instances",
        json={"type": "radarr", "name": "Radarr E2E", "url": "http://radarr:7878", "api_key": "r"},
        headers=auth_headers,
    )
    client.post("/api/setup/tmdb", json={"api_key": "tmdb_key_e2e"}, headers=auth_headers)
    client.post(
        "/api/setup/nomenclature",
        json={"default_release_tag": "EMUWAREZ", "hardlink_base": "/data/uploads/emu"},
        headers=auth_headers,
    )

    complete_resp = client.post("/api/setup/complete", headers=auth_headers)
    assert complete_resp.status_code == 200

    status_resp = client.get("/api/setup/status")
    data = status_resp.json()
    assert data["initialized"] is True
    assert data["next_step"] is None
