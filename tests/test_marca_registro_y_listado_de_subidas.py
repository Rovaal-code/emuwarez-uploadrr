"""La marca de torrent subido, y el registro y el listado de subidas sin recorrer tablas enteras."""
from __future__ import annotations

import os
import threading

import pytest

from emuwarez_uploadrr.database import _migrate_upload_jobs_torrent_subido, connect, db_path, init_db
from emuwarez_uploadrr.services.upload_execution import (
    DELETE_CONFIRMATION_TOKEN,
    QBIT_AÑADIDO,
    append_upload_log,
    count_upload_jobs,
    delete_upload_job,
    get_upload_job_logs,
    list_upload_jobs,
)


@pytest.fixture
def db_conn(isolated_db):
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _job(conn, status="completed", *, title="Peli", prepared_path=None):
    cur = conn.execute(
        "INSERT INTO upload_jobs (title, path, status, stage, prepared_path, source_path, created_at, updated_at)"
        " VALUES (?, '', ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (title, status, status, prepared_path, prepared_path),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# EJEC-7: una marca duradera para no borrar el enlace que qBittorrent siembra
# ---------------------------------------------------------------------------

def _marca(conn, jid):
    return conn.execute("SELECT torrent_subido FROM upload_jobs WHERE id = ?", (jid,)).fetchone()[0]


def test_la_linea_del_torrent_marca_la_subida_al_escribirla(db_conn):
    jid = _job(db_conn, "running")
    append_upload_log(jid, "info", "Hashing 100%", stream="stdout", conn=db_conn)
    append_upload_log(jid, "info", "[pixhost] https://t.pixhost.to/a.jpg", stream="stdout", conn=db_conn)
    assert _marca(db_conn, jid) == 0

    append_upload_log(jid, "info", "Torrent URL: https://emu-warez.com/torrents/7", stream="stdout", conn=db_conn)
    assert _marca(db_conn, jid) == 1


def test_el_aviso_de_qbittorrent_tambien_marca(db_conn):
    jid = _job(db_conn, "running")
    append_upload_log(jid, "info", QBIT_AÑADIDO, stream="system", conn=db_conn)
    assert _marca(db_conn, jid) == 1


def _enlace(tmp_path):
    raiz = tmp_path / "uploads"
    raiz.mkdir()
    enlace = raiz / "Peli.mkv"
    enlace.write_bytes(b"x")
    return str(raiz), str(enlace)


def test_borrar_un_fallo_interrumpido_tras_subir_deja_el_enlace(db_conn, tmp_path, monkeypatch):
    """Cortado por el tiempo o por un reinicio entre subir el torrent y leer «Added to:»: qBittorrent ya lo siembra."""
    from emuwarez_uploadrr.services import carpeta_subida

    raiz, enlace = _enlace(tmp_path)
    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", raiz)
    fallida = _job(db_conn, "failed", prepared_path=enlace)
    append_upload_log(fallida, "info", "Torrent URL: https://emu-warez.com/torrents/7", stream="stdout", conn=db_conn)

    assert delete_upload_job(fallida, confirmation=DELETE_CONFIRMATION_TOKEN, conn=db_conn)["ok"]
    assert os.path.lexists(enlace)


def test_borrar_un_fallo_que_no_llego_a_subir_quita_el_enlace(db_conn, tmp_path, monkeypatch):
    from emuwarez_uploadrr.services import carpeta_subida

    raiz, enlace = _enlace(tmp_path)
    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", raiz)
    fallida = _job(db_conn, "failed", prepared_path=enlace)
    append_upload_log(fallida, "info", "[pixhost] https://t.pixhost.to/a.jpg", stream="stdout", conn=db_conn)

    assert delete_upload_job(fallida, confirmation=DELETE_CONFIRMATION_TOKEN, conn=db_conn)["ok"]
    assert not os.path.lexists(enlace)


def test_la_migracion_marca_las_subidas_que_ya_lo_dejaron_escrito(db_conn):
    marcada_por_qbit = _job(db_conn, "failed")
    marcada_por_ficha = _job(db_conn, "failed")
    sin_marca = _job(db_conn, "failed")
    for jid, mensaje in ((marcada_por_qbit, QBIT_AÑADIDO), (marcada_por_ficha, "Torrent URL: https://emu-warez.com/torrents/7"),
                         (sin_marca, "Proceso fallido")):
        append_upload_log(jid, "info", mensaje, stream="system", conn=db_conn)
    # Como estaba la base antes: sin la columna ni el índice.
    db_conn.execute("DROP INDEX idx_upload_job_logs_job_sequence")
    db_conn.execute("ALTER TABLE upload_jobs DROP COLUMN torrent_subido")

    _migrate_upload_jobs_torrent_subido(db_conn)

    assert [_marca(db_conn, j) for j in (marcada_por_qbit, marcada_por_ficha, sin_marca)] == [1, 1, 0]
    indices = {f[1] for f in db_conn.execute("PRAGMA index_list(upload_job_logs)")}
    assert "idx_upload_job_logs_job_sequence" in indices


def test_la_migracion_completa_el_relleno_si_una_pasada_cayo_tras_anadir_la_columna(db_conn):
    """El ALTER se confirma solo: si la pasada cae antes del UPDATE, la siguiente ya ve la columna y debe rellenar igual."""
    jid = _job(db_conn, "failed")
    db_conn.execute(
        "INSERT INTO upload_job_logs (upload_job_id, level, message, stream, created_at, sequence)"
        " VALUES (?, 'info', 'Torrent URL: https://emu-warez.com/torrents/7', 'stdout', CURRENT_TIMESTAMP, 1)", (jid,))
    db_conn.commit()
    assert _marca(db_conn, jid) == 0

    _migrate_upload_jobs_torrent_subido(db_conn)

    assert _marca(db_conn, jid) == 1


def test_una_base_del_esquema_43_se_migra_al_arrancar_con_copia_previa(isolated_db):
    """Como la deja la versión anterior: sin la columna ni el índice, con una subida que ya subió el torrent."""
    from emuwarez_uploadrr.database import SCHEMA_VERSION, olvidar_esquema, preparar_base

    olvidar_esquema()
    ruta = db_path()
    conn = connect(ruta)
    init_db(conn)
    jid = _job(conn, "failed")
    conn.execute(
        "INSERT INTO upload_job_logs (upload_job_id, level, message, stream, created_at, sequence)"
        " VALUES (?, 'info', 'Torrent URL: https://emu-warez.com/torrents/7', 'stdout', CURRENT_TIMESTAMP, 1)", (jid,))
    conn.execute("DROP INDEX idx_upload_job_logs_job_sequence")
    conn.execute("ALTER TABLE upload_jobs DROP COLUMN torrent_subido")
    conn.execute("UPDATE app_state SET value = '43' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()
    olvidar_esquema()

    preparar_base()

    conn = connect(ruta)
    try:
        assert _marca(conn, jid) == 1
        assert conn.execute("SELECT value FROM app_state WHERE key = 'schema_version'").fetchone()[0] == str(SCHEMA_VERSION)
        assert "idx_upload_job_logs_job_sequence" in {f[1] for f in conn.execute("PRAGMA index_list(upload_job_logs)")}
    finally:
        conn.close()
    assert list((ruta.parent / "backups").glob("pre-migracion-*-v43.db"))
    olvidar_esquema()


def test_la_migracion_se_puede_repetir(db_conn):
    jid = _job(db_conn, "failed")
    append_upload_log(jid, "info", "Torrent URL: https://emu-warez.com/torrents/7", stream="stdout", conn=db_conn)
    _migrate_upload_jobs_torrent_subido(db_conn)
    assert _marca(db_conn, jid) == 1


def test_el_texto_de_la_migracion_es_el_del_aviso_de_qbittorrent():
    import inspect

    from emuwarez_uploadrr import database
    assert QBIT_AÑADIDO in inspect.getsource(database._migrate_upload_jobs_torrent_subido)


# ---------------------------------------------------------------------------
# F6 / FE-4: el registro se lee por el índice, de dos en dos y desde donde se quedó
# ---------------------------------------------------------------------------

def _plan(conn, sql, params):
    return " | ".join(f[3] for f in conn.execute("EXPLAIN QUERY PLAN " + sql, params))


def test_el_registro_se_lee_y_se_escribe_por_el_indice(db_conn):
    usa_indice = "idx_upload_job_logs_job_sequence"
    assert usa_indice in _plan(
        db_conn, "SELECT COALESCE(MAX(sequence), 0) + 1 FROM upload_job_logs WHERE upload_job_id = ?", (1,))
    assert usa_indice in _plan(
        db_conn, "SELECT * FROM upload_job_logs WHERE upload_job_id = ? ORDER BY sequence DESC, id DESC LIMIT ?", (1, 500))
    assert usa_indice in _plan(
        db_conn,
        "SELECT * FROM upload_job_logs WHERE upload_job_id = ? AND sequence > ? ORDER BY sequence ASC, id ASC LIMIT ?",
        (1, 10, 500))


def test_las_secuencias_no_se_repiten_con_dos_hilos_escribiendo(db_conn):
    jid = _job(db_conn, "running")

    def escribe(flujo):
        for i in range(100):
            append_upload_log(jid, "info", f"{flujo} {i}", stream=flujo)

    hilos = [threading.Thread(target=escribe, args=(f,)) for f in ("stdout", "stderr")]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    secuencias = [f[0] for f in db_conn.execute("SELECT sequence FROM upload_job_logs WHERE upload_job_id = ?", (jid,))]
    assert sorted(secuencias) == list(range(1, 201))


def test_leer_lo_posterior_a_una_linea_trae_solo_lo_nuevo(db_conn):
    jid = _job(db_conn, "running")
    for i in range(10):
        append_upload_log(jid, "info", f"linea {i}", stream="stdout", conn=db_conn)

    final = get_upload_job_logs(jid, limit=3, tail=True, conn=db_conn)
    assert [r["message"] for r in final["logs"]] == ["linea 7", "linea 8", "linea 9"]
    assert final["total"] == 10
    ultima = final["logs"][-1]["sequence"]

    assert get_upload_job_logs(jid, after_sequence=ultima, conn=db_conn)["logs"] == []

    append_upload_log(jid, "info", "linea 10", stream="stdout", conn=db_conn)
    append_upload_log(jid, "info", "linea 11", stream="stdout", conn=db_conn)
    nuevas = get_upload_job_logs(jid, after_sequence=ultima, conn=db_conn)
    assert [r["message"] for r in nuevas["logs"]] == ["linea 10", "linea 11"]
    assert nuevas["total"] == 12

    primeras = get_upload_job_logs(jid, limit=1, after_sequence=ultima, conn=db_conn)
    assert [r["message"] for r in primeras["logs"]] == ["linea 10"]


def test_el_registro_de_otra_subida_no_se_mezcla(db_conn):
    a, b = _job(db_conn, "running"), _job(db_conn, "running")
    append_upload_log(a, "info", "de a", conn=db_conn)
    append_upload_log(b, "info", "de b", conn=db_conn)
    append_upload_log(a, "info", "de a otra vez", conn=db_conn)
    assert [r["message"] for r in get_upload_job_logs(a, tail=True, conn=db_conn)["logs"]] == ["de a", "de a otra vez"]
    assert [r["sequence"] for r in get_upload_job_logs(b, tail=True, conn=db_conn)["logs"]] == [1]


# ---------------------------------------------------------------------------
# FE-1: el listado filtra en SQL, y el total no depende del límite
# ---------------------------------------------------------------------------

def test_el_listado_oculta_los_estados_preparatorios_en_sql_antes_de_limitar(db_conn):
    for _ in range(5):
        _job(db_conn, "preflight")
    reales = [_job(db_conn, "completed", title=f"Peli {i}") for i in range(3)]
    _job(db_conn, "blocked")

    sin_filtro = list_upload_jobs({"limit": 4}, conn=db_conn)
    assert len(sin_filtro) == 4

    con_filtro = list_upload_jobs({"limit": 4, "hide_preparatory": True}, conn=db_conn)
    assert sorted(j["id"] for j in con_filtro) == sorted(reales)


def test_el_total_ignora_el_limite_y_respeta_los_filtros(db_conn):
    for i in range(6):
        _job(db_conn, "completed", title=f"Serie {i}")
    _job(db_conn, "failed", title="Serie fallida")
    _job(db_conn, "draft", title="Serie borrador")

    assert count_upload_jobs({"hide_preparatory": True}, conn=db_conn) == 7
    assert count_upload_jobs({"hide_preparatory": True, "status": "completed"}, conn=db_conn) == 6
    assert count_upload_jobs({"hide_preparatory": True, "search": "fallida"}, conn=db_conn) == 1
    assert count_upload_jobs(conn=db_conn) == 8


def test_el_filtro_subiendo_junta_running_y_preparing_antes_de_paginar_y_contar(db_conn):
    """«Subiendo» son dos estados: filtrado después de paginar, una más antigua quedaba fuera de la primera página."""
    viejas = [_job(db_conn, "running", title="Sube 1"), _job(db_conn, "preparing", title="Sube 2")]
    for i in range(5):
        _job(db_conn, "queued", title=f"En cola {i}")
    _job(db_conn, "completed", title="Terminada")

    assert sorted(j["id"] for j in list_upload_jobs({"status": "running,preparing", "limit": 2}, conn=db_conn)) == sorted(viejas)
    assert count_upload_jobs({"status": "running,preparing"}, conn=db_conn) == 2
    assert count_upload_jobs({"status": "running"}, conn=db_conn) == 1
    assert count_upload_jobs({"status": " running , preparing "}, conn=db_conn) == 2


def test_la_api_lista_cuenta_y_lee_el_registro_por_partes(client, auth_headers, db_conn):
    for _ in range(3):
        _job(db_conn, "draft")
    ids = [_job(db_conn, "completed") for _ in range(4)]
    for i in range(5):
        append_upload_log(ids[0], "info", f"linea {i}", stream="stdout", conn=db_conn)

    r = client.get("/api/uploads", params={"hide_preparatory": "true", "limit": 3}, headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 3
    assert {j["status"] for j in r.json()} == {"completed"}

    r = client.get("/api/uploads", params={"status": "completed,failed"}, headers=auth_headers)
    assert {j["status"] for j in r.json()} == {"completed"} and len(r.json()) == 4
    r = client.get("/api/uploads/count", params={"status": "completed,failed"}, headers=auth_headers)
    assert r.json() == {"total": 4}

    # «count» no se lee como el id de una subida.
    r = client.get("/api/uploads/count", params={"hide_preparatory": "true"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"total": 4}
    assert client.get("/api/uploads/count").status_code == 401

    r = client.get(f"/api/uploads/{ids[0]}/logs", params={"tail": "true", "limit": 2}, headers=auth_headers)
    assert [l["message"] for l in r.json()["logs"]] == ["linea 3", "linea 4"]
    ultima = r.json()["logs"][-1]["sequence"]
    assert ultima == 5

    append_upload_log(ids[0], "info", "linea 5", stream="stdout", conn=db_conn)
    r = client.get(f"/api/uploads/{ids[0]}/logs", params={"after_sequence": ultima}, headers=auth_headers)
    assert [l["message"] for l in r.json()["logs"]] == ["linea 5"]
