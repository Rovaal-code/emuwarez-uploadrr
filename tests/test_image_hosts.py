"""Tests for image-host config (services/image_hosts) + settings roundtrip."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import image_hosts as ih
from tests.http_falso import falla_conexion, respuesta


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def test_default_fallback_is_imgbox(db_conn):
    assert ih.get_enabled_hosts(db_conn) == []
    assert ih.fallback_order(db_conn) == ["imgbox"]


def test_set_config_and_fallback_order(db_conn):
    ih.set_config(db_conn, ["imgbb", "lensdump"], {"imgbb": "KEY123"})
    assert ih.get_enabled_hosts(db_conn) == ["imgbb", "lensdump"]
    # imgbox always appended last
    assert ih.fallback_order(db_conn) == ["imgbb", "lensdump", "imgbox"]
    assert ih.get_host_key(db_conn, "imgbb") == "KEY123"


def test_set_config_dedupes_imgbox_last(db_conn):
    ih.set_config(db_conn, ["imgbox", "imgbb"], {})
    # imgbox not duplicated; still last
    assert ih.fallback_order(db_conn) == ["imgbb", "imgbox"]


def test_test_image_host_needs_key(db_conn):
    r = ih.test_image_host("imgbb", None)
    assert r["ok"] is False and "key" in r["error"].lower()


def test_settings_roundtrip_image_hosts(client, auth_headers):
    client.put("/api/settings", json={
        "image_hosts_enabled": ["lensdump", "imgbb"],
        "image_host_keys": {"lensdump": "pk", "imgbb": "ik"},
    }, headers=auth_headers)
    s = client.get("/api/settings", headers=auth_headers).json()
    assert s["image_hosts_enabled"] == ["lensdump", "imgbb"]
    assert set(s["image_host_keys_configured"]) >= {"lensdump", "imgbb"}
    assert len(s["image_hosts_available"]) == len(ih.IMAGE_HOSTS)
    # keys never echoed
    assert "pk" not in client.get("/api/settings", headers=auth_headers).text


def test_imghost_test_endpoint(client, auth_headers, monkeypatch):
    monkeypatch.setattr("emuwarez_uploadrr.services.image_hosts.test_image_host",
                        lambda host_id, api_key=None, **k: {"ok": True})
    r = client.post("/api/integrations/test/imghost", json={"host": "imgbox"}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["ok"] is True


def test_a_retired_host_left_in_the_settings_is_ignored(db_conn):
    """hamster.is dejó de resolver y ptpimg.me pasó a solo lectura, así que
    salieron del catálogo. A quien los tuviera activados le queda el id
    guardado en la base: tiene que caerse solo, no colarse en el orden de
    subida ni reventar nada."""
    import json
    from emuwarez_uploadrr.services.settings import set_setting
    set_setting(db_conn, "imghost.enabled", json.dumps(["ptpimg", "imgbb", "hamster"]))
    assert ih.get_enabled_hosts(db_conn) == ["imgbb"]
    assert ih.fallback_order(db_conn) == ["imgbb", "imgbox"]
    assert ih.host_meta("ptpimg") is None


# ---------------------------------------------------------------------------
# La API key se comprueba de verdad, sin subir ninguna imagen
# ---------------------------------------------------------------------------

def _respuesta(payload, status=400):
    """Imita lo que devuelve un Chevereto: 400 con un JSON de error."""
    return respuesta(status, json=payload)


def test_an_invalid_key_is_reported_as_invalid(http_falso):
    """code 100 es lo que responden los cinco proveedores cuando la clave no
    vale, y lo comprueban ANTES de mirar la imagen: por eso se puede validar
    mandando la petición sin ninguna."""
    http_falso.responde(_respuesta({"error": {"message": "Invalid API key.", "code": 100}}))
    r = ih.validate_image_host_key("lensdump", "clave-mala")
    assert r["checked"] is True and r["ok"] is False
    assert "Invalid API key" in r["error"]


def test_any_other_complaint_means_the_key_passed(http_falso):
    """Si se queja de que falta la imagen y no de la clave, la clave pasó la
    autenticación, que es lo único que se estaba comprobando."""
    http_falso.responde(_respuesta({"error": {"message": "Empty upload source.", "code": 130}}))
    r = ih.validate_image_host_key("imgbb", "clave-buena")
    assert r["checked"] is True and r["ok"] is True


def test_a_network_failure_is_not_a_bad_key(http_falso):
    """No poder preguntar NO es lo mismo que una respuesta negativa: si la red
    falla, una clave perfectamente buena no puede salir marcada en rojo."""
    http_falso.responde(falla_conexion("la red no va"))
    r = ih.validate_image_host_key("imgbb", "clave-buena")
    assert r["checked"] is False
    assert r["ok"] is False          # no se puede afirmar que valga
    assert "No se pudo comprobar" in r["error"]


def test_hosts_without_a_key_are_not_validated():
    """imgbox y compañía no llevan clave: no hay nada que comprobar."""
    assert ih.validate_image_host_key("imgbox", "loquesea")["checked"] is False
    assert ih.validate_image_host_key("imgbb", "")["checked"] is False


def test_every_host_that_needs_a_key_can_be_validated():
    """Si mañana se añade un proveedor con clave y nadie le pone su endpoint,
    su clave se guardaría sin comprobar y la insignia verde mentiría."""
    con_clave = {h["id"] for h in ih.IMAGE_HOSTS if h["needs_key"]}
    assert con_clave == set(ih._KEY_CHECK), con_clave.symmetric_difference(ih._KEY_CHECK)


def test_un_limite_de_peticiones_no_es_una_clave_valida(http_falso):
    """Un 429 sin el código 100 no dice nada de la clave: antes salía "válida"."""
    http_falso.responde(_respuesta({"error": {"message": "Flood detected", "code": 999}}, status=429))
    r = ih.validate_image_host_key("lensdump", "clave")
    assert r["checked"] is False and r["ok"] is False


def test_un_403_de_cloudflare_en_la_portada_no_es_caido(http_falso):
    """La portada responde 403 (Cloudflare) pero las subidas van: responde."""
    http_falso.responde(_respuesta({}, status=403))
    assert ih.test_image_host("imgbox")["ok"] is True


def test_una_clave_sin_comprobar_no_se_guarda_como_buena(monkeypatch, http_falso):
    """La API no contesta y la portada da 403: responde, pero la clave no está
    comprobada, así que Ajustes no puede darla por buena."""
    from emuwarez_uploadrr.services.integration_tests import test_imghost_connection
    monkeypatch.setattr(ih, "validate_image_host_key",
                        lambda *a, **k: {"ok": False, "error": "No se pudo comprobar: timeout", "checked": False})

    http_falso.responde(_respuesta({}, status=403))
    r = test_imghost_connection("imgbb", "clave")
    assert r["ok"] is False and r["status"] == "key_unchecked"
    assert "timeout" in r["message"]


def test_la_comprobacion_de_la_clave_sale_igual_que_con_urllib(http_falso):
    """POST sin cuerpo (Content-Type de formulario y longitud 0, lo que mandaba urllib), clave en ?key= para imgbb
    y en X-API-Key para los Chevereto; y solo se miran los primeros 4096 bytes de la respuesta."""
    http_falso.responde(_respuesta({"error": {"message": "Empty upload source.", "code": 130}}))
    ih.validate_image_host_key("imgbb", " clave/buena ")
    p = http_falso.ultima
    assert p.method == "POST" and str(p.url) == "https://api.imgbb.com/1/upload?key=clave%2Fbuena"
    assert p.content == b"" and p.headers["Content-Length"] == "0"
    assert p.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert p.headers["User-Agent"] == "emuwarez-uploadrr/2"

    ih.validate_image_host_key("lensdump", "clave")
    assert http_falso.ultima.headers["X-API-Key"] == "clave"
    assert "?" not in str(http_falso.ultima.url)

    relleno = {"error": {"message": "Empty upload source.", "code": 130}, "x": "a" * 5000}
    http_falso.responde(_respuesta(relleno))
    assert ih.validate_image_host_key("lensdump", "clave")["checked"] is False


def test_la_portada_caida_con_5xx_no_responde(http_falso):
    http_falso.responde(respuesta(502))
    assert ih.test_image_host("imgbox") == {"ok": False, "error": "HTTP 502"}
    http_falso.responde(falla_conexion("[Errno -2] Name or service not known"))
    assert ih.test_image_host("imgbox") == {"ok": False, "error": "No responde: [Errno -2] Name or service not known"}
