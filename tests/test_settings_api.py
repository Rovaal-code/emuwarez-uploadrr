"""API tests for GET /api/settings and PUT /api/settings (Phase 10B)."""
from __future__ import annotations

import json
import pytest


def _mock_tmdb_ok(monkeypatch):
    """TMDb/eMuwarez keys are mandatory and live-tested before being saved
    (both in the setup wizard and in PUT /settings) — tests that seed or
    change a key must mock that live probe instead of hitting the network.

    setup_service.py imports test_tmdb_connection lazily (inside the
    function), so patching the integration_tests module is enough there.
    web/api/settings.py imports it at module load time, so PUT /settings
    needs the name patched where it was bound: web.api.settings."""
    ok = lambda *a, **k: {"ok": True, "service": "tmdb", "status": "connected", "message": "Conexión correcta"}
    monkeypatch.setattr("emuwarez_uploadrr.services.integration_tests.test_tmdb_connection", ok)
    monkeypatch.setattr("emuwarez_uploadrr.web.api.settings.test_tmdb_connection", ok)


def _seed_tmdb_key(client, auth_headers, monkeypatch, key="testkey12345"):
    """Store a TMDb API key via the setup endpoint (mocks the live TMDb probe)."""
    _mock_tmdb_ok(monkeypatch)
    resp = client.post("/api/setup/tmdb", json={"api_key": key}, headers=auth_headers)
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def test_get_settings_requires_auth(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 401


def test_put_settings_requires_auth(client):
    resp = client.put("/api/settings", json={"default_release_tag": "TEST"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/settings
# ---------------------------------------------------------------------------

def test_get_settings_returns_defaults(client, auth_headers):
    resp = client.get("/api/settings", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_release_tag"] == "EMUWAREZ"
    assert isinstance(data["provider_priority_order"], list)
    assert data["tmdb_watch_region"] == "ES"
    assert data["tmdb_api_key_configured"] is False
    assert data["tmdb_api_key_masked"] is None


def test_get_settings_does_not_expose_full_tmdb_key(client, auth_headers, monkeypatch):
    _seed_tmdb_key(client, auth_headers, monkeypatch, "supersecretkey9999")
    resp = client.get("/api/settings", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tmdb_api_key_configured"] is True
    assert "supersecretkey9999" not in json.dumps(data)
    assert data["tmdb_api_key_masked"] is not None
    assert len(data["tmdb_api_key_masked"]) < len("supersecretkey9999")


# ---------------------------------------------------------------------------
# PUT /api/settings
# ---------------------------------------------------------------------------

def test_put_updates_default_release_tag(client, auth_headers):
    resp = client.put("/api/settings", json={"default_release_tag": "TESTAG"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["default_release_tag"] == "TESTAG"


def test_put_updates_provider_priority_order(client, auth_headers):
    order = ["NF", "AMZN", "DSNP"]
    resp = client.put("/api/settings", json={"provider_priority_order": order}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["provider_priority_order"] == order


def test_put_rejects_invalid_provider_codes(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"provider_priority_order": ["AMZN", "INVALID_CODE"]},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_put_rejects_duplicate_providers(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"provider_priority_order": ["AMZN", "NF", "AMZN"]},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_put_rejects_empty_release_tag(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"default_release_tag": "   "},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_put_updates_tmdb_watch_region(client, auth_headers):
    resp = client.put("/api/settings", json={"tmdb_watch_region": "US"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["tmdb_watch_region"] == "US"


def test_put_empty_tmdb_api_key_is_rejected(client, auth_headers, monkeypatch):
    # TMDb is mandatory: explicitly sending an empty key must be rejected
    # outright (not silently ignored) and must not touch the existing key.
    _seed_tmdb_key(client, auth_headers, monkeypatch, "original_key_abc")
    resp = client.put("/api/settings", json={"tmdb_api_key": ""}, headers=auth_headers)
    assert resp.status_code == 422

    get_resp = client.get("/api/settings", headers=auth_headers)
    assert get_resp.json()["tmdb_api_key_configured"] is True, "Key should remain configured"


def test_put_null_tmdb_api_key_does_not_clear_existing(client, auth_headers, monkeypatch):
    # Omitting the field (or sending JSON null, indistinguishable from omitted)
    # means "not touching this setting" — unlike an explicit empty string.
    _seed_tmdb_key(client, auth_headers, monkeypatch, "another_key_xyz")
    resp = client.put("/api/settings", json={"tmdb_api_key": None}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["tmdb_api_key_configured"] is True


def test_put_updates_tmdb_api_key_when_provided(client, auth_headers, monkeypatch):
    _mock_tmdb_ok(monkeypatch)
    resp = client.put("/api/settings", json={"tmdb_api_key": "newkey_abcdefgh"}, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tmdb_api_key_configured"] is True
    assert "newkey_abcdefgh" not in json.dumps(data)


def test_put_rejects_invalid_tmdb_api_key(client, auth_headers, monkeypatch):
    fail = lambda *a, **k: {"ok": False, "service": "tmdb", "status": "invalid_key", "message": "API key de TMDb inválida o no autorizada"}
    monkeypatch.setattr("emuwarez_uploadrr.services.integration_tests.test_tmdb_connection", fail)
    monkeypatch.setattr("emuwarez_uploadrr.web.api.settings.test_tmdb_connection", fail)
    resp = client.put("/api/settings", json={"tmdb_api_key": "bad_key"}, headers=auth_headers)
    assert resp.status_code == 422

    get_resp = client.get("/api/settings", headers=auth_headers)
    assert get_resp.json()["tmdb_api_key_configured"] is False


def test_put_empty_emu_api_key_is_rejected(client, auth_headers, monkeypatch):
    ok = lambda *a, **k: {"ok": True, "service": "emuwarez", "status": "connected", "message": "Conexión correcta"}
    monkeypatch.setattr("emuwarez_uploadrr.services.integration_tests.test_emuwarez_connection", ok)
    monkeypatch.setattr("emuwarez_uploadrr.web.api.settings.test_emuwarez_connection", ok)
    seed = client.put("/api/settings", json={"emu_api_key": "original_emu_key"}, headers=auth_headers)
    assert seed.status_code == 200

    resp = client.put("/api/settings", json={"emu_api_key": ""}, headers=auth_headers)
    assert resp.status_code == 422

    get_resp = client.get("/api/settings", headers=auth_headers)
    assert get_resp.json()["emu_api_key_configured"] is True, "Key should remain configured"


# ---------------------------------------------------------------------------
# Internal Source Tool (Ajustes -> Otros)
# ---------------------------------------------------------------------------

def test_source_engine_is_off_by_default(client, auth_headers):
    """Sigue en desarrollo, así que no decide sources para todo el mundo de
    salida: hay que encenderla a mano."""
    s = client.get("/api/settings", headers=auth_headers).json()
    assert s["source_engine_enabled"] is False


def test_source_engine_toggle_roundtrip(client, auth_headers):
    for value in (True, False):
        client.put("/api/settings", json={"source_engine_enabled": value}, headers=auth_headers)
        s = client.get("/api/settings", headers=auth_headers).json()
        assert s["source_engine_enabled"] is value


def test_source_engine_flag_is_what_media_info_reads(client, auth_headers, isolated_db):
    """El ajuste que guarda la API y el que lee media_info_service tienen que
    ser el mismo, o el interruptor no apagaría nada."""
    import os
    from emuwarez_uploadrr.services.media_info_service import source_engine_enabled
    os.environ["CONFIG_DIR"] = str(isolated_db)
    assert source_engine_enabled() is False
    client.put("/api/settings", json={"source_engine_enabled": True}, headers=auth_headers)
    assert source_engine_enabled() is True


# ---------------------------------------------------------------------------
# Renombrar/Ordenar pistas
# ---------------------------------------------------------------------------
# El desplegable de Configuración y la validación del servidor son dos listas
# distintas del mismo conjunto. Que coincidan lo vigila
# tests/test_copias_frontend.py; lo que se comprueba aquí es la otra mitad: que
# el endpoint acepta los cuatro y rechaza lo que no lo es.

def test_los_cuatro_modos_de_pistas_se_guardan(client, auth_headers):
    from emuwarez_uploadrr.services.mkv_remux import MODOS_PISTAS
    for modo in MODOS_PISTAS:
        resp = client.put("/api/settings", json={"remux_track_mode": modo}, headers=auth_headers)
        assert resp.status_code == 200, (modo, resp.text)
        assert resp.json()["remux_track_mode"] == modo
        assert client.get("/api/settings", headers=auth_headers).json()["remux_track_mode"] == modo


def test_un_modo_de_pistas_inventado_se_rechaza(client, auth_headers):
    resp = client.put("/api/settings", json={"remux_track_mode": "pepe"}, headers=auth_headers)
    assert resp.status_code == 422


def test_el_ajuste_viejo_de_reordenar_se_deja_a_la_par(client, auth_headers):
    """Volver a una versión anterior lee `remux.reorder_tracks`, y
    encontrárselo congelado en el valor de antes sería peor que traducirlo."""
    from emuwarez_uploadrr.database import connect, db_path
    from emuwarez_uploadrr.services.settings import get_setting_canonical

    def viejo():
        conn = connect(db_path())
        try:
            return get_setting_canonical(conn, "remux.reorder_tracks")
        finally:
            conn.close()

    client.put("/api/settings", json={"remux_track_mode": "solo_reordenar"}, headers=auth_headers)
    assert viejo() == "true"
    client.put("/api/settings", json={"remux_track_mode": "solo_renombrar"}, headers=auth_headers)
    assert viejo() == "false"
