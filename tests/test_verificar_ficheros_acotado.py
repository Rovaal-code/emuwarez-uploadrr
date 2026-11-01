"""Verificar ficheros en lote: acotado, una sola escritura y sin devolver cada fila.

Un clic en una biblioteca de 55.000 filas hacía 55.000 stat, 55.000 UPDATE con su
commit, abría una conexión nueva por ruta para leer las asignaciones de rutas y
devolvía un cuerpo de ~10 MB. Todo en el hilo de la petición, con un solo proceso
atendiendo.
"""
from __future__ import annotations

import os

import pytest

from emuwarez_uploadrr.database import connect, db_path, init_db
from emuwarez_uploadrr.services import library_verification as lv
from emuwarez_uploadrr.services import path_mapping


@pytest.fixture
def conn(isolated_db):
    c = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(c)
    return c


def _fila(conn, titulo, ruta, *, verificado=None, estado="Disponible") -> int:
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, path, file_verified_at, updated_at)
           VALUES ('movie', ?, ?, ?, ?, CURRENT_TIMESTAMP)""", (titulo, estado, ruta, verificado))
    conn.commit()
    return cur.lastrowid


def test_el_resumen_trae_solo_los_recuentos(conn, isolated_db):
    (isolated_db / "a.mkv").write_bytes(b"x")
    _fila(conn, "Está", str(isolated_db / "a.mkv"))
    _fila(conn, "No está", str(isolated_db / "b.mkv"))
    _fila(conn, "Sin ruta", None)
    _fila(conn, "Mal tipo", str(isolated_db))  # un directorio: aviso, no error
    resumen = lv.verify_library_files(conn)
    assert resumen == {"ok": True, "items_checked": 4, "files_found": 1, "errors": 1, "warnings": 2}


def test_se_guarda_una_sola_vez_y_con_todo(conn, isolated_db):
    for i in range(5):
        (isolated_db / f"{i}.mkv").write_bytes(b"x")
        _fila(conn, f"T{i}", str(isolated_db / f"{i}.mkv"))
    sentencias: list[str] = []
    conn.set_trace_callback(sentencias.append)
    lv.verify_library_files(conn)
    conn.set_trace_callback(None)
    assert sum(s.strip().upper() == "COMMIT" for s in sentencias) == 1
    assert sum(s.lstrip().upper().startswith("UPDATE LIBRARY_ITEMS") for s in sentencias) == 5
    assert conn.execute("SELECT COUNT(*) FROM library_items WHERE file_exists = 1 AND file_verified_at IS NOT NULL"
                        ).fetchone()[0] == 5


def test_las_asignaciones_de_rutas_se_leen_una_vez_y_se_aplican(conn, isolated_db, monkeypatch):
    (isolated_db / "peli.mkv").write_bytes(b"x")
    for i in range(4):
        _fila(conn, f"T{i}", f"/data/media/{'peli' if i == 0 else 'otra' + str(i)}.mkv")
    lecturas = []

    def leer(c=None):
        lecturas.append(c)
        return [{"from": "/data/media", "to": str(isolated_db)}]

    def no_deberia(c=None):
        raise AssertionError("cada ruta no puede volver a leer las asignaciones")

    monkeypatch.setattr(lv, "get_path_mappings", leer)
    monkeypatch.setattr(path_mapping, "get_path_mappings", no_deberia)
    resumen = lv.verify_library_files(conn)
    assert len(lecturas) == 1
    assert resumen["files_found"] == 1 and resumen["errors"] == 3


def test_con_limite_se_miran_primero_los_que_hace_mas_que_no_se_comprueban(conn, isolated_db):
    nuevo = _fila(conn, "Reciente", str(isolated_db / "1.mkv"), verificado="2026-10-31T10:00:00")
    viejo = _fila(conn, "Antiguo", str(isolated_db / "2.mkv"), verificado="2026-01-01T10:00:00")
    nunca = _fila(conn, "Nunca", str(isolated_db / "3.mkv"))
    assert lv.verify_library_files(conn, limit=2)["items_checked"] == 2
    verificados = {r["id"]: r["file_verified_at"] for r in conn.execute("SELECT id, file_verified_at FROM library_items")}
    assert verificados[nunca] and verificados[viejo] != "2026-01-01T10:00:00"
    assert verificados[nuevo] == "2026-10-31T10:00:00"
    # La siguiente vuelta sigue por el que quedó.
    lv.verify_library_files(conn, limit=1)
    assert conn.execute("SELECT file_verified_at FROM library_items WHERE id = ?", (nuevo,)).fetchone()[0] != "2026-10-31T10:00:00"


def test_cada_caso_de_ruta_da_su_aviso(conn, isolated_db, monkeypatch):
    (isolated_db / "texto.txt").write_bytes(b"x")
    ids = {
        "extension": _fila(conn, "Texto", str(isolated_db / "texto.txt")),
        "directorio": _fila(conn, "Carpeta", str(isolated_db)),
        "falla": _fila(conn, "Falla", str(isolated_db / "x.mkv")),
    }
    if hasattr(os, "mkfifo"):
        os.mkfifo(isolated_db / "tuberia.mkv")
        ids["no_regular"] = _fila(conn, "Tubería", str(isolated_db / "tuberia.mkv"))
    original = lv.safe_stat

    def stat(path, mappings=None):
        if path.endswith("x.mkv"):
            raise OSError("disco caído")
        return original(path, mappings)

    monkeypatch.setattr(lv, "safe_stat", stat)
    lv.verify_library_files(conn)
    errores = {k: conn.execute("SELECT file_verification_error FROM library_items WHERE id = ?", (i,)).fetchone()[0]
               for k, i in ids.items()}
    assert errores["extension"] == "extensión no reconocida como vídeo: .txt"
    assert "directorio" in errores["directorio"]
    assert errores["falla"] == "error al inspeccionar: disco caído"
    if "no_regular" in errores:
        assert errores["no_regular"] == "la ruta existe pero no es un archivo regular"


def test_el_filtro_de_estado_sigue_funcionando(conn, isolated_db):
    _fila(conn, "A", str(isolated_db / "a.mkv"), estado="Disponible")
    _fila(conn, "B", str(isolated_db / "b.mkv"), estado="Faltante")
    assert lv.verify_library_files(conn, filters={"status": "Faltante"})["items_checked"] == 1


def test_la_ficha_suelta_sigue_guardando_su_resultado(conn, isolated_db):
    (isolated_db / "a.mkv").write_bytes(b"x")
    item = _fila(conn, "A", str(isolated_db / "a.mkv"))
    r = lv.verify_library_item_file(item, conn)
    assert r["file_exists"] is True and r["title"] == "A"
    assert conn.execute("SELECT file_exists FROM library_items WHERE id = ?", (item,)).fetchone()[0] == 1
    assert lv.verify_library_item_file(9999, conn)["ok"] is False


# --- Por el endpoint ---------------------------------------------------------------------------

def test_el_endpoint_devuelve_recuentos_sin_el_detalle_de_cada_fila(client, auth_headers):
    c = connect(db_path())
    init_db(c)
    _fila(c, "Falta", "/no/existe.mkv")
    c.close()
    r = client.post("/api/library/verify-files", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "items_checked": 1, "files_found": 0, "errors": 1, "warnings": 0}


def test_el_endpoint_respeta_el_limite_pedido(client, auth_headers):
    c = connect(db_path())
    init_db(c)
    for i in range(3):
        _fila(c, f"T{i}", f"/no/existe{i}.mkv")
    c.close()
    assert client.post("/api/library/verify-files?limit=2", headers=auth_headers).json()["items_checked"] == 2


@pytest.mark.parametrize("limite", [0, -1, lv.MAX_VERIFICACION + 1])
def test_el_endpoint_no_admite_un_limite_fuera_de_rango(client, auth_headers, limite):
    assert client.post(f"/api/library/verify-files?limit={limite}", headers=auth_headers).status_code == 422


def test_el_endpoint_sin_limite_usa_el_maximo(client, auth_headers, monkeypatch):
    pedidos = []
    monkeypatch.setattr(lv, "verify_library_files",
                        lambda conn, filters=None, limit=None: pedidos.append(limit) or {"ok": True, "items_checked": 0,
                                                                                         "files_found": 0, "errors": 0,
                                                                                         "warnings": 0})
    assert client.post("/api/library/verify-files", headers=auth_headers).status_code == 200
    assert pedidos == [lv.MAX_VERIFICACION]


@pytest.mark.parametrize("tamano", [0, -5, 501])
def test_el_tamano_de_pagina_del_historial_esta_acotado(client, auth_headers, tamano):
    r = client.post(f"/api/arr/health/refresh?history_page_size={tamano}", headers=auth_headers)
    assert r.status_code == 422


def test_el_tamano_de_pagina_del_historial_dentro_del_rango_pasa(client, auth_headers):
    assert client.post("/api/arr/health/refresh?history_page_size=500", headers=auth_headers).status_code == 200
