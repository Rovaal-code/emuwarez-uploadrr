"""Historial de la cuenta de eMuwarez: una instantánea al día que sale del perfil horario, y su lectura."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from emuwarez_uploadrr.database import SCHEMA_VERSION, connect, db_path, get_state, init_db, set_state
from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import emu_perfil
from emuwarez_uploadrr.services.emu_perfil import perfil_emu
from emuwarez_uploadrr.services.perfil_historial import (
    RETENCION_DIAS, bytes_de_texto, guardar_instantanea, serie_cuenta,
)
from emuwarez_uploadrr.services.settings import get_setting_canonical, set_setting

# Lo que devuelve UNIT3D (app/Http/Resources/UserResource.php).
USUARIO = {
    "username": "Kisnov", "group": "Uploader", "uploaded": "1.2 TiB", "downloaded": "300 GiB",
    "ratio": "4.1", "buffer": "900 GiB", "seeding": 120, "leeching": 0, "seedbonus": "12345.50",
    "hit_and_runs": 2,
}
AHORA = datetime(2026, 11, 2, 10, 30)


@pytest.fixture
def conn(isolated_db):
    c = connect(db_path())
    init_db(c)
    yield c
    c.close()


def _filas(conn):
    return [tuple(f) for f in conn.execute(
        "SELECT dia, ratio, subido_bytes, bajado_bytes, bonus, hit_and_runs FROM perfil_historial ORDER BY dia")]


def _dia(dias_atras: int) -> str:
    return (AHORA - timedelta(days=dias_atras)).strftime("%Y-%m-%d")


# ---- migración ----

def test_base_nueva_trae_la_tabla(conn):
    assert get_state(conn, "schema_version") == str(SCHEMA_VERSION)
    columnas = [f[1] for f in conn.execute("PRAGMA table_info(perfil_historial)")]
    assert columnas == ["dia", "ratio", "subido_bytes", "bajado_bytes", "bonus", "hit_and_runs", "actualizado_at"]


def test_base_anterior_se_actualiza_sin_perder_nada(conn):
    set_setting(conn, "emu.username", "Kisnov")
    conn.execute("DROP TABLE perfil_historial")  # como una base del esquema anterior
    set_state(conn, "schema_version", str(SCHEMA_VERSION - 1))
    conn.commit()

    init_db(conn)

    assert get_state(conn, "schema_version") == str(SCHEMA_VERSION)
    assert _filas(conn) == []
    assert get_setting_canonical(conn, "emu.username") == "Kisnov"
    # idempotente: una segunda pasada no falla ni borra lo ya escrito
    guardar_instantanea(conn, USUARIO, AHORA)
    set_state(conn, "schema_version", str(SCHEMA_VERSION - 1))
    init_db(conn)
    assert len(_filas(conn)) == 1


# ---- lectura de las cifras ----

@pytest.mark.parametrize("texto, esperado", [
    ("1.2 TiB", round(1.2 * 1024 ** 4)),
    ("300 GiB", 300 * 1024 ** 3),
    ("512 MiB", 512 * 1024 ** 2),
    ("1,024.5 KiB", round(1024.5 * 1024)),
    ("0 B", 0),
    ("2.5 PiB", round(2.5 * 1024 ** 5)),
    ("∞", None),
    ("", None),
    (None, None),
    (12, None),
])
def test_bytes_de_texto(texto, esperado):
    assert bytes_de_texto(texto) == esperado


def test_instantanea_con_las_cifras_del_perfil(conn):
    guardar_instantanea(conn, USUARIO, AHORA)
    assert _filas(conn) == [(_dia(0), 4.1, round(1.2 * 1024 ** 4), 300 * 1024 ** 3, 12345.5, 2)]


def test_ratio_infinito_o_cifras_ausentes_quedan_a_none(conn):
    guardar_instantanea(conn, {"username": "K", "ratio": "∞", "uploaded": "1 GiB"}, AHORA)
    assert _filas(conn) == [(_dia(0), None, 1024 ** 3, None, None, None)]


def test_el_ultimo_valor_del_dia_gana(conn):
    guardar_instantanea(conn, USUARIO, AHORA)
    guardar_instantanea(conn, {**USUARIO, "ratio": "4.3", "hit_and_runs": 0}, AHORA.replace(hour=22))
    filas = _filas(conn)
    assert len(filas) == 1
    assert (filas[0][1], filas[0][5]) == (4.3, 0)
    assert conn.execute("SELECT actualizado_at FROM perfil_historial").fetchone()[0] == "2026-11-02T22:30:00"


def test_un_dia_nuevo_es_una_fila_nueva(conn):
    guardar_instantanea(conn, USUARIO, AHORA - timedelta(days=1))
    guardar_instantanea(conn, {**USUARIO, "ratio": "4.5"}, AHORA)
    assert [(f[0], f[1]) for f in _filas(conn)] == [(_dia(1), 4.1), (_dia(0), 4.5)]


def test_poda_lo_que_pasa_de_la_retencion(conn):
    for atras in (RETENCION_DIAS + 5, RETENCION_DIAS + 1, RETENCION_DIAS, 10):
        conn.execute("INSERT INTO perfil_historial (dia, actualizado_at) VALUES (?, 'x')", (_dia(atras),))
    guardar_instantanea(conn, USUARIO, AHORA)
    assert [f[0] for f in _filas(conn)] == [_dia(RETENCION_DIAS), _dia(10), _dia(0)]


def test_guardar_nunca_lanza(conn, caplog):
    guardar_instantanea(conn, {"ratio": object()}, AHORA)  # un perfil con forma rara
    assert _filas(conn) == [(_dia(0), None, None, None, None, None)]
    conn.execute("DROP TABLE perfil_historial")
    guardar_instantanea(conn, USUARIO, AHORA)
    assert "No se pudo guardar la instantánea" in caplog.text


def test_serie_ordenada_y_solo_la_ventana_pedida(conn):
    for atras in (40, 0, 29, 30, 5):
        guardar_instantanea(conn, {**USUARIO, "hit_and_runs": atras}, AHORA - timedelta(days=atras))
    serie = serie_cuenta(conn, 30, AHORA)
    assert [p["dia"] for p in serie] == [_dia(29), _dia(5), _dia(0)]
    assert [p["hit_and_runs"] for p in serie] == [29, 5, 0]
    assert set(serie[0]) == {"dia", "ratio", "subido_bytes", "bajado_bytes", "bonus", "hit_and_runs"}
    assert len(serie_cuenta(conn, 90, AHORA)) == 5
    assert serie_cuenta(conn, 1, AHORA)[0]["dia"] == _dia(0)


# ---- el punto de escritura: la lectura del perfil ----

def _con_clave(conn):
    set_setting(conn, "emu.api_key", "clave")
    conn.commit()


def test_leer_el_perfil_guarda_la_instantanea(conn, monkeypatch):
    _con_clave(conn)
    monkeypatch.setattr(emu_perfil, "emu_get_user", lambda api_key, base_url=None: dict(USUARIO))
    perfil_emu(conn)
    filas = _filas(conn)
    assert len(filas) == 1 and filas[0][1] == 4.1


def test_un_fallo_de_emuwarez_no_guarda_nada(conn, monkeypatch):
    _con_clave(conn)

    def falla(api_key, base_url=None):
        raise IntegrationError("sin red")

    monkeypatch.setattr(emu_perfil, "emu_get_user", falla)
    perfil_emu(conn)
    assert _filas(conn) == []


def test_si_el_historial_falla_el_perfil_se_guarda_igual(conn, monkeypatch):
    _con_clave(conn)
    monkeypatch.setattr(emu_perfil, "emu_get_user", lambda api_key, base_url=None: dict(USUARIO))
    conn.execute("DROP TABLE perfil_historial")
    assert perfil_emu(conn)["ratio"] == "4.1"


# ---- endpoint ----

def test_endpoint_exige_sesion(client):
    assert client.get("/api/estadisticas/cuenta").status_code == 401


def test_endpoint_devuelve_la_serie(client, auth_headers, conn):
    hoy = datetime.now()
    for atras in (100, 3, 0):
        guardar_instantanea(conn, {**USUARIO, "hit_and_runs": atras}, hoy - timedelta(days=atras))
    conn.commit()

    resp = client.get("/api/estadisticas/cuenta", headers=auth_headers)
    assert resp.status_code == 200
    cuerpo = resp.json()
    assert cuerpo["dias"] == 90
    assert [p["hit_and_runs"] for p in cuerpo["puntos"]] == [3, 0]  # la de hace 100 días queda fuera de los 90
    assert cuerpo["puntos"][0]["ratio"] == 4.1 and cuerpo["puntos"][0]["subido_bytes"] == round(1.2 * 1024 ** 4)

    todo = client.get("/api/estadisticas/cuenta?dias=365", headers=auth_headers).json()
    assert [p["hit_and_runs"] for p in todo["puntos"]] == [100, 3, 0]
    assert client.get("/api/estadisticas/cuenta?dias=1", headers=auth_headers).json()["puntos"][0]["hit_and_runs"] == 0


def test_endpoint_sin_instantaneas_devuelve_lista_vacia(client, auth_headers):
    assert client.get("/api/estadisticas/cuenta", headers=auth_headers).json() == {"dias": 90, "puntos": []}


@pytest.mark.parametrize("dias", ["0", "-1", "731", "x"])
def test_endpoint_rechaza_rangos_absurdos(client, auth_headers, dias):
    assert client.get(f"/api/estadisticas/cuenta?dias={dias}", headers=auth_headers).status_code == 422
