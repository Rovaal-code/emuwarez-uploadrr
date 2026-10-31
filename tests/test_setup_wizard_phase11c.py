"""Tests for the onboarding wizard's step order (admin -> emu -> instances ->
tmdb -> complete). No dedicated Uploadrr step — service ships with sensible
defaults, configurable later from Settings. No dedicated nomenclature step
either — the upload tag lives on the eMuwarez step and provider priority on
its own step now, both frontend-only via PUT /settings (see SetupWizard.tsx).
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _mock_integration_tests(monkeypatch):
    """eMuwarez/TMDb keys are now live-tested before being saved. That
    validation isn't what this file is about (step ordering), so make the
    probe always succeed. setup_service.py imports these lazily, so patching
    the integration_tests module is enough for the POST /setup/* endpoints
    exercised here."""
    ok = lambda *a, **k: {"ok": True, "service": "x", "status": "connected", "message": "ok"}
    monkeypatch.setattr("emuwarez_uploadrr.services.integration_tests.test_tmdb_connection", ok)
    monkeypatch.setattr("emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection", ok)


# ---------------------------------------------------------------------------
# next_step() reordering
# ---------------------------------------------------------------------------

def test_next_step_order_after_admin(client, auth_headers):
    resp = client.get("/api/setup/status")
    assert resp.json()["next_step"] == "emu"


def test_complete_fails_with_nothing_else_configured(client, auth_headers):
    """eMuwarez and TMDb are mandatory — completing setup right after admin
    creation, with them left unconfigured, must be blocked with 'Pasos
    pendientes', not succeed. Instances/Uploadrr stay optional."""
    resp = client.post("/api/setup/complete", headers=auth_headers)
    assert resp.status_code == 400
    assert "emu" in resp.json()["detail"]
    assert "tmdb" in resp.json()["detail"]

    status_resp = client.get("/api/setup/status")
    data = status_resp.json()
    assert data["initialized"] is False


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
    assert resp.json()["next_step"] == "qbit"


def _hasta_tmdb(client, auth_headers):
    client.post("/api/setup/emu", json={"api_key": "emukey"}, headers=auth_headers)
    client.post(
        "/api/setup/instances",
        json={"type": "radarr", "name": "R1", "url": "http://r:7878", "api_key": "k"},
        headers=auth_headers,
    )
    client.post("/api/setup/tmdb", json={"api_key": "tmdbkey"}, headers=auth_headers)


def test_recargar_tras_tmdb_retoma_los_pasos_opcionales(client, auth_headers):
    """Tras TMDb la interfaz sigue con qBittorrent, proveedores e imágenes: una
    recarga no puede saltar a "completar" y dejar de ofrecerlos."""
    _hasta_tmdb(client, auth_headers)
    assert client.get("/api/setup/status").json()["next_step"] == "qbit"

    # Saltarse qBittorrent (sin URL) también cuenta como paso hecho.
    resp = client.post("/api/setup/qbit", json={"url": ""}, headers=auth_headers)
    assert resp.status_code == 200
    assert client.get("/api/setup/status").json()["next_step"] == "providers"

    resp = client.post("/api/setup/imghosts", json={"enabled": [], "keys": {}}, headers=auth_headers)
    assert resp.status_code == 200
    assert client.get("/api/setup/status").json()["next_step"] == "complete"


def test_recargar_sin_instancias_tampoco_vuelve_al_paso_de_instancias(client, auth_headers):
    """Las instancias se pueden saltar: tras TMDb la recarga retoma el paso
    apuntado, no el de instancias."""
    client.post("/api/setup/emu", json={"api_key": "emukey"}, headers=auth_headers)
    client.post("/api/setup/tmdb", json={"api_key": "tmdbkey"}, headers=auth_headers)
    assert client.get("/api/setup/status").json()["next_step"] == "qbit"

    client.post("/api/setup/qbit", json={"url": ""}, headers=auth_headers)
    assert client.get("/api/setup/status").json()["next_step"] == "providers"

    client.post("/api/setup/imghosts", json={"enabled": [], "keys": {}}, headers=auth_headers)
    assert client.get("/api/setup/status").json()["next_step"] == "complete"


def test_un_paso_opcional_apuntado_no_salta_a_tmdb(client, auth_headers):
    """TMDb es obligatorio: aunque se llame antes a un paso opcional, hasta que
    esté configurado el siguiente sigue siendo TMDb."""
    client.post("/api/setup/emu", json={"api_key": "emukey"}, headers=auth_headers)
    client.post("/api/setup/qbit", json={"url": ""}, headers=auth_headers)
    assert client.get("/api/setup/status").json()["next_step"] == "tmdb"


def test_repetir_un_paso_no_hace_retroceder_el_asistente(client, auth_headers):
    _hasta_tmdb(client, auth_headers)
    client.post("/api/setup/qbit", json={"url": ""}, headers=auth_headers)
    client.post("/api/setup/tmdb", json={"api_key": "otra"}, headers=auth_headers)
    assert client.get("/api/setup/status").json()["next_step"] == "providers"


def test_completar_cierra_el_asistente_aunque_queden_pasos_opcionales(client, auth_headers):
    _hasta_tmdb(client, auth_headers)
    assert client.post("/api/setup/complete", headers=auth_headers).status_code == 200
    assert client.get("/api/setup/status").json()["next_step"] is None


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
