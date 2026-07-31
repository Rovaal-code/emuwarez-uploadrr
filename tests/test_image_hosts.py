"""Tests for image-host config (services/image_hosts) + settings roundtrip."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import image_hosts as ih


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
    from emuwarez_uploadrr.web.services.settings_service import set_setting
    set_setting(db_conn, "imghost.enabled", json.dumps(["ptpimg", "imgbb", "hamster"]))
    assert ih.get_enabled_hosts(db_conn) == ["imgbb"]
    assert ih.fallback_order(db_conn) == ["imgbb", "imgbox"]
    assert ih.host_meta("ptpimg") is None
