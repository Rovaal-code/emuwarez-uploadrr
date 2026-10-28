"""eMuwarez pasó de emuwarez.com a emu-warez.com y el viejo ya no responde: los
enlaces que ya estaban guardados se reescriben al migrar al esquema 39."""
from __future__ import annotations

from emuwarez_uploadrr.database import connect, db_path, init_db, set_state


def test_los_enlaces_guardados_pasan_al_dominio_nuevo(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    conn.execute(
        "INSERT INTO upload_jobs (title, path, status, stage, result_url, created_at, updated_at)"
        " VALUES ('X', '', 'completed', 'completed', 'https://emuwarez.com/torrents/1',"
        " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO request_items (emu_id, title, url) VALUES ('7', 'X', 'https://emuwarez.com/requests/7')")
    conn.execute("INSERT INTO request_items (emu_id, title, url) VALUES ('8', 'Y', 'https://otra.web/emuwarez.com')")
    set_state(conn, "schema_version", "38")
    conn.commit()

    init_db(conn)

    assert conn.execute("SELECT result_url FROM upload_jobs").fetchone()[0] == "https://emu-warez.com/torrents/1"
    urls = [r[0] for r in conn.execute("SELECT url FROM request_items ORDER BY emu_id")]
    assert urls == ["https://emu-warez.com/requests/7", "https://otra.web/emuwarez.com"]
    conn.close()
