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


def test_no_hacer_copias_reflink_va_apagado_y_se_guarda_en_la_clave_que_lee_la_cola(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path
    from emuwarez_uploadrr.services.settings import get_setting_canonical
    from emuwarez_uploadrr.services.upload_queue import AJUSTE_SIN_COPIAS_REFLINK

    def guardado():
        conn = connect(db_path())
        try:
            return get_setting_canonical(conn, AJUSTE_SIN_COPIAS_REFLINK)
        finally:
            conn.close()

    assert client.get("/api/settings", headers=auth_headers).json()["remux_no_reflink_copies"] is False
    for valor in (True, False):
        resp = client.put("/api/settings", json={"remux_no_reflink_copies": valor}, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["remux_no_reflink_copies"] is valor
        assert guardado() == ("true" if valor else "false")


def test_por_defecto_solo_hay_un_grupo_de_subida(client, auth_headers):
    assert client.get("/api/settings", headers=auth_headers).json()["upload_tags"] == ["EMUWAREZ"]


def test_se_guardan_varios_grupos_de_subida(client, auth_headers):
    resp = client.put(
        "/api/settings",
        json={"default_release_tag": "Ryodan", "upload_tags": ["Ryodan", " Otro ", "Ryodan", "Tercero"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = client.get("/api/settings", headers=auth_headers).json()
    assert data["default_release_tag"] == "Ryodan"
    assert data["upload_tags"] == ["Ryodan", "Otro", "Tercero"]


def test_el_grupo_por_defecto_va_siempre_el_primero(client, auth_headers):
    client.put("/api/settings", json={"upload_tags": ["Otro", "Tercero"]}, headers=auth_headers)
    client.put("/api/settings", json={"default_release_tag": "Tercero"}, headers=auth_headers)
    assert client.get("/api/settings", headers=auth_headers).json()["upload_tags"] == ["Tercero", "Otro"]


def test_no_se_guarda_un_grupo_de_subida_vacio(client, auth_headers):
    resp = client.put("/api/settings", json={"upload_tags": ["Ryodan", "  "]}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.parametrize("cuerpo", [{"upload_tags": ["../fuera"]}, {"default_release_tag": r"a\b"}])
def test_un_grupo_de_subida_no_lleva_barras(client, auth_headers, cuerpo):
    assert client.put("/api/settings", json=cuerpo, headers=auth_headers).status_code == 422


# ---------------------------------------------------------------------------
# Quitar un secreto: un valor vacío deja el que hay, así que se pide con `clear`
# ---------------------------------------------------------------------------

def _guardar_secretos(client, auth_headers):
    resp = client.put("/api/settings", json={
        "qbit_url": "http://qbit:8080", "qbit_password": "clave-qbit",
        "notify_discord_webhook_url": "https://discord.com/api/webhooks/1/abcdefghi",
        "notify_telegram_bot_token": "123456:SECRETTOKEN",
        "image_host_keys": {"lensdump": "pk", "imgbb": "ik"},
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["qbit_password_configured"] is True
    assert data["notify_discord_webhook_configured"] is True
    assert data["notify_telegram_bot_token_configured"] is True


def test_un_valor_vacio_no_quita_los_secretos(client, auth_headers):
    _guardar_secretos(client, auth_headers)
    data = client.put("/api/settings", json={
        "qbit_password": "", "notify_discord_webhook_url": "", "notify_telegram_bot_token": "",
    }, headers=auth_headers).json()
    assert data["qbit_password_configured"] is True
    assert data["notify_discord_webhook_configured"] is True
    assert data["notify_telegram_bot_token_configured"] is True


def test_clear_quita_cada_secreto(client, auth_headers):
    _guardar_secretos(client, auth_headers)
    data = client.put("/api/settings", json={"clear": [
        "qbit_password", "notify_discord_webhook_url", "notify_telegram_bot_token",
    ]}, headers=auth_headers).json()
    assert data["qbit_password_configured"] is False
    assert data["notify_discord_webhook_configured"] is False
    assert data["notify_discord_webhook_masked"] is None
    assert data["notify_telegram_bot_token_configured"] is False
    assert data["notify_telegram_bot_token_masked"] is None
    # Lo demás se queda como estaba.
    assert data["qbit_url"] == "http://qbit:8080"
    assert set(data["image_host_keys_configured"]) >= {"lensdump", "imgbb"}


def test_clear_quita_la_clave_de_un_proveedor_de_imagenes(client, auth_headers):
    _guardar_secretos(client, auth_headers)
    data = client.put("/api/settings", json={"clear": ["image_host_key:lensdump"]}, headers=auth_headers).json()
    assert "lensdump" not in data["image_host_keys_configured"]
    assert "imgbb" in data["image_host_keys_configured"]


def test_clear_con_un_valor_nuevo_a_la_vez_deja_el_nuevo(client, auth_headers):
    _guardar_secretos(client, auth_headers)
    data = client.put("/api/settings", json={
        "clear": ["qbit_password"], "qbit_password": "otra-clave",
    }, headers=auth_headers).json()
    assert data["qbit_password_configured"] is True
    # La vieja también dejaba "configurada": se mira lo guardado.
    from emuwarez_uploadrr.database import connect, get_setting_canonical
    from emuwarez_uploadrr.web.runtime import _db_path
    with connect(_db_path()) as conn:
        assert get_setting_canonical(conn, "qbit.password") == "otra-clave"


@pytest.mark.parametrize("nombre", ["tmdb_api_key", "emu_api_key", "image_host_key:noexiste", "qbit_url"])
def test_clear_rechaza_lo_que_no_es_un_secreto_borrable(client, auth_headers, nombre):
    """Las claves de TMDb y eMuwarez son obligatorias: no se pueden quitar."""
    resp = client.put("/api/settings", json={"clear": [nombre]}, headers=auth_headers)
    assert resp.status_code == 422
    assert nombre in resp.json()["detail"]


def test_sincronizar_al_volver_una_instancia_viene_activado_y_se_puede_apagar(client, auth_headers):
    assert client.get("/api/settings", headers=auth_headers).json()["sincronizar_al_volver_instancia"] is True
    for valor in (False, True):
        resp = client.put("/api/settings", json={"sincronizar_al_volver_instancia": valor}, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["sincronizar_al_volver_instancia"] is valor


# ---------------------------------------------------------------------------
# URL pública de qBittorrent (solo para el enlace «Abrir en qBittorrent»)
# ---------------------------------------------------------------------------

def test_la_url_publica_de_qbit_viene_vacia_y_se_guarda_sin_espacios(client, auth_headers):
    assert client.get("/api/settings", headers=auth_headers).json()["qbit_public_url"] is None
    resp = client.put("/api/settings", json={"qbit_public_url": "  https://qbit.midominio.es:8443/webui  "},
                      headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["qbit_public_url"] == "https://qbit.midominio.es:8443/webui"
    # Es independiente de la URL del servidor (que puede ser un nombre de contenedor).
    assert resp.json()["qbit_url"] is None


def test_la_url_publica_de_qbit_se_quita_con_un_valor_vacio(client, auth_headers):
    client.put("/api/settings", json={"qbit_public_url": "http://192.168.1.5:8080"}, headers=auth_headers)
    resp = client.put("/api/settings", json={"qbit_public_url": ""}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["qbit_public_url"] is None


@pytest.mark.parametrize("mala", [
    "qbit.lan:8080", "ftp://qbit.lan", "javascript:alert(1)", "http://", "https:///ruta", "http://qbit lan",
    "http://admin:clave@qbit.lan:8080", "https://admin@qbit.lan", "http://qbit.lan:puerto",
])
def test_la_url_publica_de_qbit_rechaza_lo_que_no_es_http_o_lleva_credenciales(client, auth_headers, mala):
    resp = client.put("/api/settings", json={"qbit_public_url": mala}, headers=auth_headers)
    assert resp.status_code == 422
    # Lo que se rechaza no se devuelve en el error: podría llevar una clave.
    assert "clave" not in resp.text
    assert client.get("/api/settings", headers=auth_headers).json()["qbit_public_url"] is None


def test_guardar_la_url_publica_no_la_escribe_en_el_registro(client, auth_headers, caplog):
    import logging
    with caplog.at_level(logging.DEBUG):
        client.put("/api/settings", json={"qbit_public_url": "https://qbit.midominio.es"}, headers=auth_headers)
        client.put("/api/settings", json={"qbit_public_url": "https://u:SECRETO-XYZ@qbit.midominio.es"},
                   headers=auth_headers)
    assert "qbit_public_url" in caplog.text  # el nombre del ajuste sí
    assert "midominio" not in caplog.text and "SECRETO-XYZ" not in caplog.text


def test_la_url_publica_de_qbit_no_es_un_secreto_ni_hay_que_pedirla_con_clear(client, auth_headers):
    from emuwarez_uploadrr.services.settings import es_secreto
    assert not es_secreto("qbit.public_url")
    resp = client.put("/api/settings", json={"clear": ["qbit_public_url"]}, headers=auth_headers)
    assert resp.status_code == 422


def test_la_url_publica_de_qbit_viaja_en_la_copia_de_configuracion(client, auth_headers, tmp_path):
    """No lleva claves (el PUT las rechaza), así que va en la copia sin pedir `incluir_claves`."""
    from emuwarez_uploadrr.services.backup_service import _vaciar_claves
    from emuwarez_uploadrr.database import connect, db_path
    client.put("/api/settings", json={"qbit_public_url": "https://qbit.midominio.es"}, headers=auth_headers)
    copia = tmp_path / "copia.db"
    origen = connect(db_path())
    try:
        origen.execute("VACUUM INTO ?", (str(copia),))
    finally:
        origen.close()
    _vaciar_claves(copia)
    import sqlite3
    with sqlite3.connect(copia) as c:
        valor = c.execute("SELECT value FROM settings WHERE key = 'qbit.public_url'").fetchone()
    assert valor and valor[0] == "https://qbit.midominio.es"
