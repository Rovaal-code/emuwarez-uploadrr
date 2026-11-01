"""La API de subidas enseña los pasos con nombre y deja reintentar desde el principio."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db


@pytest.fixture
def db_conn(client):
    conn = connect(db_path())
    init_db(conn)
    yield conn
    conn.close()


def _peli(conn, ruta="/fake/movie.mkv"):
    conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status, path,
                                      size_bytes, updated_at)
           VALUES ('movie', 'Peli', 'Disponible', 'Sin petición', 'N/A', ?, 100, CURRENT_TIMESTAMP)""", (ruta,))
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _subida(conn, status, stage, parada=None):
    cur = conn.execute(
        """INSERT INTO upload_jobs (library_item_id, status, stage, etapa_parada, title, path, source_path,
                                    created_at, updated_at)
           VALUES (?, ?, ?, ?, 'Peli', '/fake/movie.mkv', '/fake/movie.mkv', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (_peli(conn), status, stage, parada))
    conn.commit()
    return cur.lastrowid


def test_el_detalle_trae_los_pasos_y_desde_donde_se_reanudaria(client, auth_headers, db_conn):
    j = _subida(db_conn, "failed", "failed", "running")
    datos = client.get(f"/api/uploads/{j}", headers=auth_headers).json()

    assert [(p["clave"], p["estado"]) for p in datos["pasos"]] == [
        ("nomenclatura", "hecho"), ("preparacion", "hecho"), ("verificacion", "hecho"), ("subida", "fallido")]
    assert datos["pasos"][0]["nombre"]
    assert datos["reintento_desde"] == "verificacion"
    assert datos["reintento_desde_nombre"] == "Verificar antes de subir"


def test_una_subida_parada_antes_de_preparar_no_se_reanuda(client, auth_headers, db_conn):
    j = _subida(db_conn, "failed", "failed", "remux")
    datos = client.get(f"/api/uploads/{j}", headers=auth_headers).json()
    assert datos["pasos"][1]["estado"] == "fallido"
    assert datos["reintento_desde"] is None and datos["reintento_desde_nombre"] is None


def test_una_subida_en_marcha_no_se_reanuda(client, auth_headers, db_conn):
    datos = client.get(f"/api/uploads/{_subida(db_conn, 'running', 'running')}", headers=auth_headers).json()
    assert datos["pasos"][3]["estado"] == "en_curso"
    assert datos["reintento_desde"] is None


@pytest.mark.parametrize("query,reutiliza", [("", 1), ("?desde_el_principio=false", 1), ("?desde_el_principio=true", 0)])
def test_reintentar_reanuda_salvo_que_se_pida_desde_el_principio(client, auth_headers, db_conn, query, reutiliza):
    j = _subida(db_conn, "failed", "failed", "running")
    resp = client.post(f"/api/uploads/{j}/retry-queued{query}", json={}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    nuevo = resp.json()["job"]["id"]
    fila = db_conn.execute("SELECT reutiliza_preparacion, retry_of_job_id FROM upload_jobs WHERE id = ?", (nuevo,)).fetchone()
    assert (fila["reutiliza_preparacion"], fila["retry_of_job_id"]) == (reutiliza, j)
