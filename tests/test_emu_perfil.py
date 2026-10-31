"""Tu cuenta de eMuwarez (/api/user): una llamada por hora como mucho, y el último perfil bueno si falla."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from emuwarez_uploadrr.database import connect, db_path, get_json_state, init_db, set_json_state
from emuwarez_uploadrr.integrations import emu
from emuwarez_uploadrr.integrations.base import IntegrationError
from emuwarez_uploadrr.services import emu_perfil
from emuwarez_uploadrr.services.emu_perfil import PERFIL_STATE_KEY, perfil_emu
from emuwarez_uploadrr.services.settings import get_setting_canonical, set_setting

# Lo que devuelve UNIT3D (app/Http/Resources/UserResource.php).
USUARIO = {
    "username": "Kisnov", "group": "Uploader", "uploaded": "1.2 TiB", "downloaded": "300 GiB",
    "ratio": "4.1", "buffer": "900 GiB", "seeding": 120, "leeching": 0, "seedbonus": "12345.50",
    "hit_and_runs": 0,
}


@pytest.fixture
def conn():
    c = connect(db_path())
    init_db(c)
    set_setting(c, "emu.api_key", "clave")
    c.commit()
    yield c
    c.close()


@pytest.fixture
def llamadas(monkeypatch):
    hechas: list[str] = []

    def falso(api_key, base_url=None):
        hechas.append(api_key)
        return dict(USUARIO)

    monkeypatch.setattr(emu_perfil, "emu_get_user", falso)
    return hechas


def _intento_hace(conn, plazo: timedelta) -> None:
    guardado = get_json_state(conn, PERFIL_STATE_KEY)
    guardado["intento_at"] = (datetime.now(timezone.utc) - plazo).isoformat()
    set_json_state(conn, PERFIL_STATE_KEY, guardado)
    conn.commit()


def test_emu_get_user_pide_api_user_con_la_clave(monkeypatch):
    urls = []
    monkeypatch.setattr(emu, "request_json", lambda method, url: urls.append(url) or dict(USUARIO))
    assert emu.emu_get_user("k")["group"] == "Uploader"
    assert urls == ["https://emu-warez.com/api/user?api_token=k"]


@pytest.mark.parametrize("estado", [401, 403, 429])
def test_emu_get_user_no_ensena_la_url(monkeypatch, estado):
    def falso(method, url):
        raise IntegrationError(f"HTTP {estado} en {url}", status=estado)

    monkeypatch.setattr(emu, "request_json", falso)
    with pytest.raises(IntegrationError) as exc:
        emu.emu_get_user("secreta")
    assert "secreta" not in str(exc.value) and exc.value.status == estado


def test_emu_get_user_rechaza_una_respuesta_sin_usuario(monkeypatch):
    monkeypatch.setattr(emu, "request_json", lambda method, url: {"message": "Unauthenticated."})
    with pytest.raises(IntegrationError, match="formato"):
        emu.emu_get_user("k")


def test_sin_clave_no_llama_y_los_enlaces_usan_el_usuario_de_ajustes(conn, llamadas):
    set_setting(conn, "emu.api_key", "")
    set_setting(conn, "emu.username", "Gabriel")
    perfil = perfil_emu(conn)
    assert llamadas == []
    assert (perfil["configured"], perfil["username"], perfil["ratio"]) == (False, "Gabriel", None)


def test_lee_el_perfil_y_lo_guarda_una_hora(conn, llamadas):
    perfil = perfil_emu(conn)
    assert llamadas == ["clave"]
    assert perfil["configured"] and perfil["error"] is None and perfil["updated_at"]
    assert {c: perfil[c] for c in USUARIO} == USUARIO

    perfil_emu(conn)
    _intento_hace(conn, timedelta(minutes=59))
    perfil_emu(conn)
    assert llamadas == ["clave"]

    _intento_hace(conn, timedelta(hours=1))
    perfil_emu(conn)
    assert llamadas == ["clave", "clave"]


def test_actualizar_espera_un_minuto(conn, llamadas):
    perfil_emu(conn)
    perfil_emu(conn, actualizar=True)
    assert len(llamadas) == 1
    _intento_hace(conn, timedelta(minutes=1))
    perfil_emu(conn, actualizar=True)
    assert len(llamadas) == 2


def test_un_fallo_deja_el_ultimo_perfil_y_no_se_reintenta_hasta_la_hora(conn, llamadas, monkeypatch):
    perfil_emu(conn)
    _intento_hace(conn, timedelta(hours=2))
    fallos = []

    def falla(api_key, base_url=None):
        fallos.append(api_key)
        raise IntegrationError("eMuwarez ha rechazado la API key (¿ratio por debajo de 1?)", status=401)

    monkeypatch.setattr(emu_perfil, "emu_get_user", falla)
    perfil = perfil_emu(conn)
    assert perfil["error"].startswith("eMuwarez ha rechazado")
    assert perfil["ratio"] == "4.1"
    perfil_emu(conn)
    assert len(fallos) == 1


def test_rellena_el_usuario_de_ajustes_solo_si_esta_vacio(conn, llamadas):
    perfil_emu(conn)
    assert get_setting_canonical(conn, "emu.username") == "Kisnov"

    set_setting(conn, "emu.username", "OtroNombre")
    _intento_hace(conn, timedelta(hours=1))
    perfil_emu(conn)
    assert get_setting_canonical(conn, "emu.username") == "OtroNombre"


def test_si_otra_peticion_ya_esta_pidiendo_no_llama(conn, llamadas):
    assert emu_perfil._PIDIENDO.acquire(blocking=False)
    try:
        perfil = perfil_emu(conn)
    finally:
        emu_perfil._PIDIENDO.release()
    assert llamadas == [] and perfil["ratio"] is None


def test_endpoint(client, auth_headers, conn, llamadas):
    assert client.get("/api/dashboard/emu-perfil").status_code == 401
    resp = client.get("/api/dashboard/emu-perfil", headers=auth_headers)
    assert resp.status_code == 200
    assert (resp.json()["username"], resp.json()["seedbonus"]) == ("Kisnov", 12345.5)
    assert client.post("/api/dashboard/emu-perfil/actualizar", headers=auth_headers).status_code == 200
    assert len(llamadas) == 1
