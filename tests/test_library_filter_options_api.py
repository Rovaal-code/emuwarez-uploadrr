"""Tests for GET /library/filter-options — Excel-style filter dropdowns: only
values that actually occur in the library should be offered, never an
invented fixed list."""
from __future__ import annotations

from emuwarez_uploadrr.database import connect, db_path, init_db


def _seed_instance(conn, *, itype="radarr", name="Radarr Test") -> int:
    cur = conn.execute(
        "INSERT INTO instances (type, name, url, api_key) VALUES (?, ?, 'http://x', 'k')",
        (itype, name),
    )
    conn.commit()
    return cur.lastrowid


def _seed_item(conn, *, item_type="movie", local_status="Disponible", request_status="Sin petición",
                nomenclature_status="N/A", instance_id=None, emu_in_catalog=None, emu_aportes=None, title="X"):
    conn.execute(
        """INSERT INTO library_items
           (item_type, title, local_status, request_status, nomenclature_status, instance_id,
            emu_in_catalog, emu_aportes, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (item_type, title, local_status, request_status, nomenclature_status, instance_id,
         emu_in_catalog, emu_aportes),
    )
    conn.commit()


def test_filter_options_only_returns_values_actually_present(client, auth_headers):
    conn = connect(db_path())
    init_db(conn)
    iid = _seed_instance(conn)
    # Only 2 of the many possible LocalStatus values are ever used.
    _seed_item(conn, item_type="movie", local_status="Disponible", instance_id=iid, title="M1")
    _seed_item(conn, item_type="episode", local_status="Faltante", instance_id=iid, title="E1")
    conn.close()

    resp = client.get("/api/library/filter-options", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert set(data["types"]) == {"movie", "episode"}
    assert set(data["statuses"]) == {"Disponible", "Faltante"}
    # "En cola", "Error de importación", etc. never occurred — must not appear.
    assert "Error de importación" not in data["statuses"]
    assert len(data["instances"]) == 1
    assert data["instances"][0]["id"] == iid


def test_filter_options_emu_and_aporte_states_reflect_real_data(client, auth_headers):
    conn = connect(db_path())
    init_db(conn)
    # Only "candidate" (emu_in_catalog=0) items exist — "present" must be absent.
    _seed_item(conn, emu_in_catalog=0, title="Candidate1")
    _seed_item(conn, emu_in_catalog=0, title="Candidate2")
    conn.close()

    resp = client.get("/api/library/filter-options", headers=auth_headers)
    data = resp.json()
    assert data["emu_states"] == ["candidate"]
    # emu_in_catalog=0 always counts as an aporte ("Nuevo").
    assert data["aporte_states"] == ["yes"]


def test_filter_options_aporte_no_when_present_without_aportes(client, auth_headers):
    conn = connect(db_path())
    init_db(conn)
    _seed_item(conn, emu_in_catalog=1, emu_aportes="[]", title="Present-no-aporte")
    conn.close()

    resp = client.get("/api/library/filter-options", headers=auth_headers)
    data = resp.json()
    assert data["emu_states"] == ["present"]
    assert data["aporte_states"] == ["no"]


def test_filter_options_empty_library_returns_empty_lists(client, auth_headers):
    resp = client.get("/api/library/filter-options", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    for key in ("types", "statuses", "request_statuses", "nomenclature_statuses", "instances", "emu_states", "aporte_states"):
        assert data[key] == []
