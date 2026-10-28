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
    conn.execute("INSERT INTO request_items (emu_id, title, url) VALUES ('8', 'Y', 'https://emuwarez.com.example.org/x')")
    conn.execute("INSERT INTO request_items (emu_id, title, url) VALUES ('9', 'Z', 'HTTPS://EMUWAREZ.COM')")
    # Sin id propio, normalize_request usa el enlace como emu_id: si no cambia, la próxima sync duplica la petición.
    conn.execute("INSERT INTO request_items (emu_id, title, url) VALUES ('https://emuwarez.com/requests/10', 'W', NULL)")
    set_state(conn, "enlaces", '{"url": "https://emuwarez.com"}')
    set_state(conn, "schema_version", "38")
    conn.commit()

    init_db(conn)

    assert conn.execute("SELECT result_url FROM upload_jobs").fetchone()[0] == "https://emu-warez.com/torrents/1"
    urls = [r[0] for r in conn.execute("SELECT url FROM request_items WHERE url IS NOT NULL ORDER BY emu_id")]
    assert urls == ["https://emu-warez.com/requests/7", "https://emuwarez.com.example.org/x", "HTTPS://emu-warez.com"]
    assert conn.execute("SELECT 1 FROM request_items WHERE emu_id = 'https://emu-warez.com/requests/10'").fetchone()
    assert conn.execute("SELECT value FROM app_state WHERE key = 'enlaces'").fetchone()[0] == '{"url": "https://emu-warez.com"}'
    conn.close()
