"""Al migrar se borran las peticiones de ejemplo y lo que colgaba de ellas."""
from __future__ import annotations

from emuwarez_uploadrr.database import connect, db_path, init_db


def _cuenta(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]


def test_las_peticiones_de_ejemplo_se_borran_con_lo_que_colgaba_de_ellas(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    ejemplo = conn.execute(
        "INSERT INTO request_items (emu_id, title, is_example) VALUES ('ejemplo-1', 'Falsa', 1)").lastrowid
    real = conn.execute("INSERT INTO request_items (emu_id, title) VALUES ('7', 'Real')").lastrowid
    de_ejemplo = conn.execute(
        "INSERT INTO library_items (item_type, title, local_status, request_status, request_id)"
        " VALUES ('movie', 'Peli', 'Disponible', 'Compatible', ?)", (ejemplo,)).lastrowid
    de_verdad = conn.execute(
        "INSERT INTO library_items (item_type, title, local_status, request_status, request_id)"
        " VALUES ('movie', 'Otra', 'Disponible', 'Parcial', ?)", (real,)).lastrowid
    for peticion in (ejemplo, real):
        conn.execute("INSERT INTO request_matches (library_item_id, request_item_id, status)"
                     " VALUES (?, ?, 'Compatible')", (de_ejemplo, peticion))
        conn.execute("INSERT INTO request_readiness (request_item_id, status) VALUES (?, 'ready')", (peticion,))
        conn.execute("INSERT INTO request_candidates (request_item_id, library_item_id, candidate_rank, match_status)"
                     " VALUES (?, ?, 1, 'Compatible')", (peticion, de_ejemplo))
        conn.execute("INSERT INTO operational_queue_items (queue_key, item_type, entity_type, request_item_id)"
                     " VALUES (?, 'request_readiness', 'request', ?)", (f"request:{peticion}:readiness", peticion))
    conn.execute("DELETE FROM app_state WHERE key = 'schema_version'")
    conn.commit()

    init_db(conn)

    assert [r[0] for r in conn.execute("SELECT id FROM request_items")] == [real]
    for tabla in ("request_matches", "request_readiness", "request_candidates", "operational_queue_items"):
        assert [r[0] for r in conn.execute(f"SELECT request_item_id FROM {tabla}")] == [real], tabla
    estado = lambda i: tuple(conn.execute(
        "SELECT request_status, request_id FROM library_items WHERE id = ?", (i,)).fetchone())
    assert estado(de_ejemplo) == ("Sin petición", None)
    assert estado(de_verdad) == ("Parcial", real)
    conn.close()
