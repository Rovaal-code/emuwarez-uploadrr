"""Acceso: el login se bloquea tras varios fallos y las sesiones caducan, se listan y se cierran.

F9 de la revisión de 2026-10-31.
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from emuwarez_uploadrr.database import _migrate_auth_sessions_last_used, connect, init_db
from emuwarez_uploadrr.web.app import create_app
from emuwarez_uploadrr.web.services import auth_service
from emuwarez_uploadrr.web.services.auth_service import (
    BLOQUEO_SEGUNDOS,
    MAX_FALLOS,
    MAX_FALLOS_IP,
    create_session,
    create_user,
    get_user_by_token,
    registrar_acierto,
    registrar_fallo,
    segundos_de_bloqueo,
)

USUARIO = "testadmin"
CLAVE = "TestPass1!secret"


def _login(client, usuario=USUARIO, clave=CLAVE):
    return client.post("/api/auth/login", json={"username": usuario, "password": clave})


def _sql(isolated_db, sql: str, params: tuple = ()) -> list:
    conn = sqlite3.connect(str(isolated_db / "emuwarez_uploadrr.db"))
    try:
        filas = conn.execute(sql, params).fetchall()
        conn.commit()
        return filas
    finally:
        conn.close()


@pytest.fixture
def reloj(monkeypatch):
    """El reloj del bloqueo, a mano: [segundos]."""
    ahora = [1000.0]
    monkeypatch.setattr(auth_service, "time", SimpleNamespace(monotonic=lambda: ahora[0]))
    return ahora


# ---------------------------------------------------------------------------
# Bloqueo del login
# ---------------------------------------------------------------------------

def test_al_quinto_fallo_el_login_se_bloquea_aunque_la_clave_sea_buena(client, admin_token):
    for _ in range(MAX_FALLOS):
        assert _login(client, clave="Incorrecta1!").status_code == 401

    resp = _login(client)

    assert resp.status_code == 429
    assert int(resp.headers["retry-after"]) == BLOQUEO_SEGUNDOS
    assert "15 min" in resp.json()["detail"]


def test_cuatro_fallos_no_bloquean(client, admin_token):
    for _ in range(MAX_FALLOS - 1):
        assert _login(client, clave="Incorrecta1!").status_code == 401
    assert _login(client).status_code == 200


def test_un_acierto_pone_el_contador_a_cero(client, admin_token):
    for _ in range(MAX_FALLOS - 1):
        _login(client, clave="Incorrecta1!")
    assert _login(client).status_code == 200
    for _ in range(MAX_FALLOS - 1):
        assert _login(client, clave="Incorrecta1!").status_code == 401
    assert _login(client).status_code == 200


def test_el_bloqueo_es_por_ip_y_usuario(client, admin_token):
    for _ in range(MAX_FALLOS):
        _login(client, clave="Incorrecta1!")
    assert _login(client).status_code == 429

    otra_ip = TestClient(create_app(), client=("10.9.9.9", 5000))
    assert _login(otra_ip).status_code == 200
    assert _login(client, usuario="otro", clave="Incorrecta1!").status_code == 401


def test_un_usuario_que_no_existe_tambien_se_bloquea(client):
    """Si no, el bloqueo diría qué usuarios existen."""
    for _ in range(MAX_FALLOS):
        assert _login(client, usuario="nadie", clave="Incorrecta1!").status_code == 401
    assert _login(client, usuario="nadie", clave="Incorrecta1!").status_code == 429


def test_el_bloqueo_no_distingue_mayusculas_del_usuario(client, admin_token):
    for _ in range(MAX_FALLOS):
        _login(client, usuario=USUARIO.upper(), clave="Incorrecta1!")
    assert _login(client).status_code == 429


def test_pasados_los_15_minutos_se_puede_volver_a_probar(client, admin_token, reloj):
    for _ in range(MAX_FALLOS):
        _login(client, clave="Incorrecta1!")
    assert _login(client).status_code == 429

    reloj[0] += BLOQUEO_SEGUNDOS - 1
    assert _login(client).status_code == 429
    reloj[0] += 1
    assert _login(client).status_code == 200


def test_los_fallos_viejos_no_suman(reloj):
    for _ in range(MAX_FALLOS - 1):
        registrar_fallo("1.1.1.1", "ana")
    reloj[0] += BLOQUEO_SEGUNDOS
    registrar_fallo("1.1.1.1", "ana")
    assert segundos_de_bloqueo("1.1.1.1", "ana") == 0


def test_la_tabla_de_fallos_se_limpia_sola(reloj):
    for i in range(auth_service._MAX_CLAVES + 1):
        registrar_fallo(f"10.0.{i // 250}.{i % 250}", "ana")
    reloj[0] += BLOQUEO_SEGUNDOS
    registrar_fallo("1.1.1.1", "nuevo")
    assert len(auth_service._fallos) == 2        # la de ese usuario y la de esa IP
    registrar_acierto("1.1.1.1", "nuevo")
    assert list(auth_service._fallos) == [("1.1.1.1", None)]


def test_la_limpieza_no_expulsa_a_quien_sigue_bloqueado(reloj):
    """Al llegar al tope solo caducan las viejas: si no, quien inunda la tabla se borraría su propio bloqueo."""
    for _ in range(MAX_FALLOS):
        registrar_fallo("2.2.2.2", "ana")
    for i in range(auth_service._MAX_CLAVES + 1):
        registrar_fallo(f"10.0.{i // 250}.{i % 250}", "x")
    reloj[0] += 61                               # toca podar, y nada ha caducado
    registrar_fallo("3.3.3.3", "x")
    assert segundos_de_bloqueo("2.2.2.2", "ana") > 0
    assert len(auth_service._fallos) > auth_service._MAX_CLAVES


def test_la_tabla_no_se_recorre_en_cada_fallo(reloj):
    def lote(prefijo):
        for i in range(auth_service._MAX_CLAVES):
            registrar_fallo(f"{prefijo}.{i // 250}.{i % 250}", "x")

    lote("10.0")                                  # t=1000: tira de aquí a 1900
    reloj[0] = 1030
    lote("10.1")                                  # t=1030: caduca a las 1930
    reloj[0] = 1900
    registrar_fallo("4.4.4.4", "x")               # poda: caduca el primer lote, no el segundo
    assert len(auth_service._fallos) == 2 * auth_service._MAX_CLAVES + 2
    reloj[0] = 1930                               # el segundo lote ya caducó, pero la última poda fue hace 30 s
    registrar_fallo("5.5.5.5", "x")
    assert len(auth_service._fallos) == 2 * auth_service._MAX_CLAVES + 4
    reloj[0] = 1961                               # ya pasó el minuto
    registrar_fallo("6.6.6.6", "x")
    assert len(auth_service._fallos) == 6


def test_la_clave_del_usuario_se_recorta():
    registrar_fallo("1.1.1.1", "u" * 100_000)
    claves = [c for c in auth_service._fallos if c[1] is not None]
    assert len(claves) == 1 and len(claves[0][1]) == auth_service._LARGO_USUARIO


def test_una_ip_que_prueba_muchos_usuarios_se_bloquea(reloj):
    for i in range(MAX_FALLOS_IP):
        assert segundos_de_bloqueo("1.1.1.1", f"u{i}") == 0
        registrar_fallo("1.1.1.1", f"u{i}")
    assert segundos_de_bloqueo("1.1.1.1", "otro-mas") == BLOQUEO_SEGUNDOS
    assert segundos_de_bloqueo("9.9.9.9", "u0") == 0
    assert len(auth_service._fallos) == MAX_FALLOS_IP + 1


def test_un_acierto_no_borra_el_contador_de_la_ip(reloj):
    for i in range(MAX_FALLOS_IP - 1):
        registrar_fallo("1.1.1.1", f"u{i}")
    registrar_acierto("1.1.1.1", "u0")
    registrar_fallo("1.1.1.1", "otro")
    assert segundos_de_bloqueo("1.1.1.1", "cualquiera") > 0


def test_la_api_bloquea_a_la_ip_que_prueba_muchos_usuarios(client, admin_token):
    for i in range(MAX_FALLOS_IP):
        assert _login(client, usuario=f"nadie{i}", clave="Incorrecta1!").status_code == 401
    resp = _login(client)
    assert resp.status_code == 429
    assert int(resp.headers["retry-after"]) == BLOQUEO_SEGUNDOS


def test_un_fallo_de_la_base_al_entrar_es_503_no_500(client, admin_token, monkeypatch):
    def _bloqueada(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("emuwarez_uploadrr.web.api.auth.db", _bloqueada)
    resp = _login(client)
    assert resp.status_code == 503
    assert resp.headers["retry-after"]


# ---------------------------------------------------------------------------
# Caducidad de las sesiones
# ---------------------------------------------------------------------------

def test_una_sesion_sin_usar_30_dias_caduca(client, auth_headers, isolated_db):
    _sql(isolated_db, "UPDATE auth_sessions SET last_used_at = datetime('now', '-29 days')")
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 200

    _sql(isolated_db, "UPDATE auth_sessions SET last_used_at = datetime('now', '-31 days')")
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401


def test_una_sesion_no_dura_mas_de_90_dias_aunque_se_use(client, auth_headers, isolated_db):
    _sql(isolated_db, "UPDATE auth_sessions SET created_at = datetime('now', '-89 days')")
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 200

    _sql(isolated_db, "UPDATE auth_sessions SET created_at = datetime('now', '-91 days'), "
                      "last_used_at = datetime('now')")
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401


def test_una_sesion_sin_dato_de_uso_cuenta_desde_que_se_abrio(client, auth_headers, isolated_db):
    """Las de antes de la migración, si no se completaron, no valen para siempre."""
    _sql(isolated_db, "UPDATE auth_sessions SET last_used_at = NULL, created_at = datetime('now', '-40 days')")
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401


def test_usar_la_sesion_apunta_el_ultimo_uso(client, auth_headers, isolated_db):
    _sql(isolated_db, "UPDATE auth_sessions SET last_used_at = datetime('now', '-1 hour')")
    auth_service._apuntadas.clear()

    assert client.get("/api/auth/me", headers=auth_headers).status_code == 200

    assert _sql(isolated_db, "SELECT last_used_at > datetime('now', '-1 minute') FROM auth_sessions") == [(1,)]


def test_un_uso_reciente_no_escribe_en_la_base(client, auth_headers, isolated_db):
    _sql(isolated_db, "UPDATE auth_sessions SET last_used_at = datetime('now', '-2 minutes')")
    antes = _sql(isolated_db, "SELECT last_used_at FROM auth_sessions")

    assert client.get("/api/auth/me", headers=auth_headers).status_code == 200

    assert _sql(isolated_db, "SELECT last_used_at FROM auth_sessions") == antes


class _ConexionOcupada:
    """Una conexión a la que no le deja escribir una sincronización: cuenta los intentos."""

    def __init__(self, conn):
        self.conn = conn
        self.escrituras = 0

    def execute(self, sql, params=()):
        if sql.lstrip().startswith("UPDATE"):
            self.escrituras += 1
            raise sqlite3.OperationalError("database is locked")
        return self.conn.execute(sql, params)


def test_con_la_base_ocupada_la_peticion_pasa_y_no_se_insiste(isolated_db):
    conn = connect()
    init_db(conn)
    user_id = create_user(conn, "ana", "Clave1!claveclave")
    token = create_session(conn, user_id)
    conn.execute("UPDATE auth_sessions SET last_used_at = datetime('now', '-1 hour')")
    conn.commit()
    ocupada = _ConexionOcupada(conn)

    assert get_user_by_token(ocupada, token)["username"] == "ana"
    assert get_user_by_token(ocupada, token)["username"] == "ana"

    assert ocupada.escrituras == 1
    conn.close()


def test_el_usuario_que_devuelve_el_token_no_lleva_el_campo_interno(client, auth_headers, isolated_db):
    conn = connect()
    token = auth_headers["Authorization"].split(" ", 1)[1]
    assert "por_apuntar" not in get_user_by_token(conn, token)
    conn.close()


# ---------------------------------------------------------------------------
# Sesiones abiertas
# ---------------------------------------------------------------------------

def test_las_sesiones_abiertas_se_listan_marcando_la_actual(client, auth_headers):
    otra = _login(client).json()["token"]

    resp = client.get("/api/auth/sessions", headers=auth_headers)

    assert resp.status_code == 200
    sesiones = resp.json()["sessions"]
    assert resp.json()["inactive_days"] == auth_service.SESION_INACTIVA_DIAS
    assert len(sesiones) == 2
    assert [s["current"] for s in sesiones].count(True) == 1
    assert all(s["last_used_at"] and s["created_at"] for s in sesiones)
    # Desde la otra sesión la marcada es la otra.
    desde_otra = client.get("/api/auth/sessions", headers={"Authorization": f"Bearer {otra}"}).json()["sessions"]
    assert [s["id"] for s in desde_otra if s["current"]] != [s["id"] for s in sesiones if s["current"]]


def test_la_lista_no_incluye_las_caducadas_ni_las_cerradas(client, auth_headers, isolated_db):
    _login(client)
    cerrada = _login(client).json()["token"]
    client.post("/api/auth/logout", headers={"Authorization": f"Bearer {cerrada}"})
    _login(client)
    _sql(isolated_db, "UPDATE auth_sessions SET last_used_at = datetime('now', '-40 days') "
                      "WHERE id = (SELECT MAX(id) FROM auth_sessions)")

    sesiones = client.get("/api/auth/sessions", headers=auth_headers).json()["sessions"]

    assert len(sesiones) == 2


def test_cerrar_las_demas_deja_solo_la_actual(client, auth_headers):
    otra = _login(client).json()["token"]
    _login(client)

    resp = client.post("/api/auth/sessions/close-others", headers=auth_headers)

    assert resp.status_code == 200 and resp.json() == {"closed": 2}
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {otra}"}).status_code == 401
    sesiones = client.get("/api/auth/sessions", headers=auth_headers).json()["sessions"]
    assert len(sesiones) == 1 and sesiones[0]["current"]
    assert client.post("/api/auth/sessions/close-others", headers=auth_headers).json() == {"closed": 0}


def test_las_sesiones_piden_estar_dentro(client):
    assert client.get("/api/auth/sessions").status_code == 401
    assert client.post("/api/auth/sessions/close-others").status_code == 401


def test_un_user_agent_enorme_se_recorta(client, admin_token, isolated_db):
    _login_con_agente = client.post(
        "/api/auth/login", json={"username": USUARIO, "password": CLAVE}, headers={"user-agent": "x" * 5000},
    )
    assert _login_con_agente.status_code == 200
    largo = _sql(isolated_db, "SELECT MAX(LENGTH(user_agent)) FROM auth_sessions")[0][0]
    assert largo == 300


# ---------------------------------------------------------------------------
# Migración
# ---------------------------------------------------------------------------

def test_la_migracion_apunta_como_usadas_las_sesiones_que_ya_estan_abiertas(isolated_db):
    conn = connect()
    init_db(conn)
    uid = create_user(conn, "ana", "Clave1!claveclave")
    abierta = create_session(conn, uid)
    cerrada = create_session(conn, uid)
    conn.execute("UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE id = 2")
    conn.commit()
    conn.execute("ALTER TABLE auth_sessions DROP COLUMN last_used_at")

    _migrate_auth_sessions_last_used(conn)
    _migrate_auth_sessions_last_used(conn)  # idempotente

    filas = conn.execute("SELECT id, last_used_at FROM auth_sessions ORDER BY id").fetchall()
    assert filas[0]["last_used_at"] is not None
    assert filas[1]["last_used_at"] is None
    assert get_user_by_token(conn, abierta)["username"] == "ana"
    assert get_user_by_token(conn, cerrada) is None
    conn.close()
