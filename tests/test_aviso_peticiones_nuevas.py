"""La sincronización avisa de las peticiones nuevas que ya se pueden rellenar, una sola vez y en un solo mensaje.

Nada aquí habla con el tracker: `emu_fetch_all_pages` se sustituye por lo que devolvería."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import notification_center as nc
from emuwarez_uploadrr.services import requests as reqs
from emuwarez_uploadrr.services.settings import set_setting


def _fila(id_, nombre=None, tmdb=0):
    return {"id": id_, "name": nombre or f"Petición {id_}", "category_id": 1, "tmdb": tmdb or id_ + 1000,
            "status": "unfilled", "bounty": "10.00", "created": f"2025-01-{id_:02d}T00:00:00+00:00"}


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    set_setting(conn, "emu.api_key", "clave")
    return conn


@pytest.fixture
def sincroniza(db_conn, monkeypatch):
    def hacer(filas):
        monkeypatch.setattr(reqs.emu, "emu_fetch_all_pages", lambda *a, **kw: (filas, len(filas)))
        return reqs.sync_emu_requests(db_conn, force=True)
    return hacer


def _lista_para_subir(conn, id_):
    """Deja en la biblioteca lo que hace «ready_to_upload» la petición `_fila(id_)`."""
    conn.execute(
        "INSERT INTO library_items (item_type, title, year, tmdb_id, local_status, file_exists, nomenclature_status,"
        " prepared_path) VALUES ('movie', ?, 2020, ?, 'Disponible', 1, 'Correcta', ?)",
        (f"Peli {id_}", str(id_ + 1000), f"/data/prepared/{id_}.mkv"))
    conn.commit()


def _avisos(conn):
    return [n for n in nc.list_notifications(conn, limit=50) if n["event_type"] == "request_new_ready"]


def test_la_primera_sincronizacion_no_avisa_de_lo_que_ya_estaba(db_conn, sincroniza):
    for i in (1, 2, 3):
        _lista_para_subir(db_conn, i)
    sincroniza([_fila(1), _fila(2), _fila(3)])
    assert _avisos(db_conn) == []
    assert db_conn.execute("SELECT COUNT(*) FROM request_items WHERE aviso_pendiente = 1").fetchone()[0] == 0


def test_una_peticion_nueva_ya_lista_avisa_una_sola_vez(db_conn, sincroniza):
    sincroniza([_fila(1)])
    _lista_para_subir(db_conn, 2)
    sincroniza([_fila(1), _fila(2, "Dune")])
    aviso, = _avisos(db_conn)
    assert "«Dune»" in aviso["body"] and "http" not in aviso["body"] and aviso["link"] == "/requests"
    sincroniza([_fila(1), _fila(2, "Dune")])
    assert len(_avisos(db_conn)) == 1


def test_una_nueva_que_aun_no_se_puede_rellenar_no_avisa_ni_despues(db_conn, sincroniza):
    sincroniza([_fila(1)])
    sincroniza([_fila(1), _fila(2)])  # sin nada en la biblioteca: no está lista
    assert _avisos(db_conn) == []
    _lista_para_subir(db_conn, 2)
    sincroniza([_fila(1), _fila(2)])  # ya no es nueva: lo de la biblioteca lo cubre «Contenido compatible»
    assert _avisos(db_conn) == []


def test_una_peticion_que_ya_se_conocia_no_avisa_al_ponerse_lista(db_conn, sincroniza):
    sincroniza([_fila(1)])
    _lista_para_subir(db_conn, 1)
    sincroniza([_fila(1)])
    assert _avisos(db_conn) == []


def test_varias_nuevas_van_en_un_solo_aviso_con_el_recuento_y_las_primeras(db_conn, sincroniza):
    sincroniza([_fila(1)])
    filas = [_fila(i) for i in range(2, 9)]
    for i in range(2, 9):
        _lista_para_subir(db_conn, i)
    sincroniza([_fila(1), *filas])
    aviso, = _avisos(db_conn)
    assert "Hay 7 peticiones nuevas" in aviso["body"]
    assert "«Petición 2»" in aviso["body"] and "«Petición 6»" in aviso["body"] and "«Petición 7»" not in aviso["body"]
    assert aviso["body"].endswith("y 2 más.")


def test_con_el_evento_desactivado_no_llega_a_la_campana_ni_a_los_bots(db_conn, sincroniza, monkeypatch):
    enviados = []
    monkeypatch.setattr(nc, "send_discord", lambda url, mensaje, **kw: enviados.append(mensaje) or {"ok": True})
    set_setting(db_conn, "notify.discord.enabled", "true")
    set_setting(db_conn, "notify.discord.webhook_url", "https://discord.test/hook")
    set_setting(db_conn, "notify.discord.events", "upload_completed")
    set_setting(db_conn, "notify.ui.events", "upload_completed")
    sincroniza([_fila(1)])
    _lista_para_subir(db_conn, 2)
    sincroniza([_fila(1), _fila(2)])
    assert _avisos(db_conn) == [] and enviados == []


def test_con_el_evento_activado_llega_tambien_a_los_bots(db_conn, sincroniza, monkeypatch):
    enviados = []
    monkeypatch.setattr(nc, "send_discord", lambda url, mensaje, **kw: enviados.append(mensaje) or {"ok": True})
    set_setting(db_conn, "notify.discord.enabled", "true")
    set_setting(db_conn, "notify.discord.webhook_url", "https://discord.test/hook")
    sincroniza([_fila(1)])
    _lista_para_subir(db_conn, 2)
    sincroniza([_fila(1), _fila(2, "Dune")])
    # «Contenido compatible» sale por su lado para la misma petición; aquí solo cuenta el aviso nuevo.
    nuevos = [m for m in enviados if "Peticiones nuevas listas para subir" in m]
    assert len(nuevos) == 1 and "«Dune»" in nuevos[0]


def test_sin_preparacion_calculada_la_peticion_se_mira_en_la_siguiente(db_conn, sincroniza, monkeypatch):
    sincroniza([_fila(1)])
    _lista_para_subir(db_conn, 2)
    real = reqs.refresh_request_readiness
    monkeypatch.setattr(reqs, "refresh_request_readiness", lambda conn: (_ for _ in ()).throw(RuntimeError("rota")))
    sincroniza([_fila(1), _fila(2)])
    assert _avisos(db_conn) == []
    monkeypatch.setattr(reqs, "refresh_request_readiness", real)
    sincroniza([_fila(1), _fila(2)])
    assert len(_avisos(db_conn)) == 1


def test_un_fallo_al_avisar_no_tumba_la_sincronizacion_ni_lo_repite(db_conn, sincroniza, monkeypatch, caplog):
    sincroniza([_fila(1)])
    _lista_para_subir(db_conn, 2)

    def rota(*a, **kw):
        raise RuntimeError("rota")

    monkeypatch.setattr(nc, "emit", rota)
    assert sincroniza([_fila(1), _fila(2)])["status"] == "ok"
    assert "No se pudo avisar de las peticiones nuevas listas para subir" in caplog.text
    assert db_conn.execute("SELECT COUNT(*) FROM request_items WHERE aviso_pendiente = 1").fetchone()[0] == 0


def test_el_evento_es_un_tipo_mas_de_la_matriz_de_ajustes(db_conn):
    assert "request_new_ready" in nc.EVENT_TYPES
    assert all("request_new_ready" in nc.channel_events(db_conn, c) for c in ("ui", "discord", "telegram"))


def test_un_titulo_con_arroba_no_avisa_a_todo_el_canal_de_discord(db_conn, sincroniza):
    sincroniza([_fila(1)])
    _lista_para_subir(db_conn, 2)
    sincroniza([_fila(1), _fila(2, "@everyone")])
    aviso, = _avisos(db_conn)
    assert "@everyone" not in aviso["body"] and "@​everyone" in aviso["body"]
