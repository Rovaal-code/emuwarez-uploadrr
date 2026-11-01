"""Shared pytest fixtures.

Every test gets its own temp directory as CONFIG_DIR so the database is
isolated from the real ~/.config/emuwarez-renamer/ path.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FAKE_UPLOADRR_EMU_SCRIPT = Path(__file__).parent / "fixtures" / "fake_uploadrr_emu.py"


_LOCALES = {"localhost", "127.0.0.1", "::1", "testserver"}


class RedBloqueada(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Ningún test sale a la red: una petición real a eMuwarez puede costar el
    ban de la cuenta. Solo se permite loopback (servidores falsos locales).
    El intento se corta y además suspende el test, aunque el código se trague
    el error y siga por otro camino."""
    import socket

    intentos: list[str] = []

    conectar = socket.socket.connect
    conectar_envio = socket.socket.sendto
    resolver = socket.getaddrinfo

    def _host(direccion):
        return direccion[0] if isinstance(direccion, tuple) else None

    def connect(sock, direccion):
        host = _host(direccion)
        if sock.family in (socket.AF_INET, socket.AF_INET6) and host not in _LOCALES:
            intentos.append(f"conexión a {host}")
            raise RedBloqueada(f"conexión real a {host} desde un test: haz mock")
        return conectar(sock, direccion)

    def getaddrinfo(host, *args, **kwargs):
        if host not in _LOCALES:
            intentos.append(f"DNS de {host}")
            raise RedBloqueada(f"resolución DNS de {host} desde un test: haz mock")
        return resolver(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect)
    monkeypatch.setattr(socket.socket, "sendto", lambda sock, data, *args: connect(sock, args[-1]) or conectar_envio(sock, data, *args))
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield
    if intentos:
        pytest.fail(f"el test intentó salir a la red: {sorted(set(intentos))}")


@pytest.fixture(autouse=True)
def _sin_listas_de_anime(monkeypatch):
    """Cada sincronización de biblioteca intenta bajar anime-list-full.json de
    GitHub; en los tests falla igual que sin red (ensure_anime_id_map lo tolera)."""
    from emuwarez_uploadrr.services import anime_lists

    def _sin_red(*_a, **_k):
        raise RuntimeError("sin red en los tests")

    monkeypatch.setattr(anime_lists, "request_json", _sin_red)


@pytest.fixture(autouse=True)
def _sin_manifiesto_de_version(monkeypatch):
    """El planificador y el arranque comprueban la versión contra GitHub: en
    los tests, a un puerto cerrado de loopback (falla al instante)."""
    from emuwarez_uploadrr.services import version_info

    monkeypatch.setattr(version_info, "URL_MANIFIESTO", "http://127.0.0.1:9/latest.json")


@pytest.fixture
def ficheros_de_mentira(monkeypatch):
    """Para las pruebas que crean un .mkv con bytes cualquiera. Con mkvmerge y
    mediainfo instalados (la imagen de Docker), un fichero así ya no pasa la
    comprobación de integridad; aquí se lee sin mkvmerge y con un MediaInfo
    que no encuentra nada (lo que contesta el real a esos bytes), esté o no
    instalado."""
    from emuwarez_uploadrr.services import media_info_service, media_probe, mkv_remux
    monkeypatch.setattr(mkv_remux, "check_mkvmerge_available", lambda: {"available": False, "path": None})
    monkeypatch.setattr(media_info_service, "mediainfo_available", lambda: True)

    def _mediainfo_sin_pistas(path):
        return {"media": {"@ref": str(path), "track": [{"@type": "General", "FileSize": str(path.stat().st_size)}]}}

    monkeypatch.setattr(media_probe, "run_mediainfo_json", _mediainfo_sin_pistas)
    monkeypatch.setattr(media_info_service, "read_media_info_summary", lambda path: {
        "video_codec": None, "audio_codec": None, "audio_languages": None, "subtitle_languages": None})


@pytest.fixture(autouse=True)
def _procesos_sin_apagado():
    """Apagar la aplicación (lifespan) deja de admitir procesos nuevos; en el
    mismo proceso de pytest hay que volver a admitirlos para el test siguiente."""
    yield
    from emuwarez_uploadrr.services import mkv_remux, upload_execution
    mkv_remux._apagando = False
    upload_execution._apagando = False


@pytest.fixture
def subidas_reales():
    """Pídelo para que encolar una subida arranque de verdad su hilo."""


@pytest.fixture(autouse=True)
def _subidas_sin_hilo(request, monkeypatch):
    """Encolar una subida arranca su hilo al momento. En los tests ese hilo
    correría solo contra la base del test, así que se queda sin lanzar salvo
    que el test pida `subidas_reales` (o llame a _run_queued_job él mismo)."""
    if "subidas_reales" in request.fixturenames:
        return
    from emuwarez_uploadrr.services import upload_queue
    monkeypatch.setattr(upload_queue, "_lanzar_trabajo", lambda job_id: None)


@pytest.fixture(autouse=True)
def _login_sin_memoria():
    """El bloqueo del login y el apunte de uso de las sesiones viven en memoria: que no pasen de un test a otro."""
    from emuwarez_uploadrr.web.services import auth_service
    auth_service._fallos.clear()
    auth_service._apuntadas.clear()
    auth_service._ultima_poda = float("-inf")
    yield


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point CONFIG_DIR to a per-test temp dir so each test starts with a fresh DB."""
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    yield tmp_path


@pytest.fixture(autouse=True)
def _default_instance_connection_ok(monkeypatch):
    """The create-instance endpoint (POST /api/instances) now verifies the
    Radarr/Sonarr connection before persisting. Test fixtures create instances
    with fake URLs/keys, so default that check to OK here — tests that exercise
    the rejection path patch ``test_connection_params`` themselves (inner patch
    wins). Only affects the create flow; per-instance /test endpoints mock the
    real *arr client separately."""
    try:
        import emuwarez_uploadrr.services.instances as _inst
    except Exception:
        return
    monkeypatch.setattr(
        _inst, "test_connection_params",
        lambda *a, **k: {"ok": True, "version": "test"}, raising=False,
    )


@pytest.fixture
def client(isolated_db):
    """TestClient with a freshly created app (DB is already isolated)."""
    from emuwarez_uploadrr.web.app import create_app
    return TestClient(create_app())


@pytest.fixture
def admin_token(client):
    """Create admin user and return a valid session token."""
    resp = client.post("/api/setup/admin", json={
        "username": "testadmin",
        "password": "TestPass1!secret",
    })
    assert resp.status_code == 201, resp.text
    resp = client.post("/api/auth/login", json={
        "username": "testadmin",
        "password": "TestPass1!secret",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


@pytest.fixture
def auth_headers(admin_token):
    """Authorization headers for authenticated requests."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def fake_uploadrr_emu_dir(tmp_path):
    """A fake Uploadrr-EMU install directory for real-subprocess tests.

    <dir>/upload.py is a copy of tests/fixtures/fake_uploadrr_emu.py — a
    test-only CLI that accepts the real Uploadrr-EMU flags, never touches
    the network, and never uploads anything real (see that file's docstring).
    <dir>/data/config.yaml is a minimal placeholder config so config-staging
    tests (Phase 10F) have something to back up/stage/restore.

    Never points at a real Uploadrr-EMU installation.
    """
    uploadrr_dir = tmp_path / "FakeUploadrrEMU"
    uploadrr_dir.mkdir()
    shutil.copy(FAKE_UPLOADRR_EMU_SCRIPT, uploadrr_dir / "upload.py")
    data_dir = uploadrr_dir / "data"
    data_dir.mkdir()
    (data_dir / "config.yaml").write_text(
        "DEFAULT:\n"
        "  tmdb: PLACEHOLDER_TMDB_KEY\n"
        "  default_torrent_client: qbit\n"
        "\n"
        "TRACKERS:\n"
        "  EMU:\n"
        "    api_key: PLACEHOLDER_EMU_KEY\n"
        "    anon: false\n",
        encoding="utf-8",
    )
    return uploadrr_dir


@pytest.fixture
def fake_uploadrr_python_path():
    """python_path to use with fake_uploadrr_emu_dir — the current interpreter."""
    return sys.executable
