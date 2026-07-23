"""Tests for the onboarding wizard's step order (admin -> emu -> instances ->
tmdb -> complete). No dedicated Uploadrr step — service ships with sensible
defaults, configurable later from Settings. No dedicated nomenclature step
either — the upload tag lives on the eMuwarez step and provider priority on
its own step now, both frontend-only via PUT /settings (see SetupWizard.tsx).
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


def test_setup_instances_rejects_invalid_url(client, auth_headers):
    """The onboarding wizard's Instancias step used to only check the URL
    wasn't blank — a real http(s) URL is required, same as the Instancias
    tab in Configuración already enforces."""
    resp = client.post(
        "/api/setup/instances",
        json={"type": "radarr", "name": "R1", "url": "solo un texto cualquiera", "api_key": "k"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


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
# Full flow — new step order end to end, including optional steps
# ---------------------------------------------------------------------------

def test_full_setup_flow_new_order(client, auth_headers):
    client.post("/api/setup/emu", json={"api_key": "emu_key_e2e"}, headers=auth_headers)
    client.post(
        "/api/setup/instances",
        json={"type": "radarr", "name": "Radarr E2E", "url": "http://radarr:7878", "api_key": "r"},
        headers=auth_headers,
    )
    client.post("/api/setup/tmdb", json={"api_key": "tmdb_key_e2e"}, headers=auth_headers)

    complete_resp = client.post("/api/setup/complete", headers=auth_headers)
    assert complete_resp.status_code == 200

    status_resp = client.get("/api/setup/status")
    data = status_resp.json()
    assert data["initialized"] is True
    assert data["next_step"] is None
