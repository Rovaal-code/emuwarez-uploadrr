"""Tests for the pre-upload checks (services/upload_checks)."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import upload_checks as uc


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


# Defaults to Castilian audio: the checks now require Castilian one way or the
# other (upload_checks' "spanish" check), so a film without it isn't a normal
# uploadable film any more. The Castilian tests pass their own values.
def _movie_with_path(conn, path: str, *, audio_languages: str | None = "spa",
                     subtitle_languages: str | None = None) -> int:
    conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status,
            path, size_bytes, audio_languages, subtitle_languages, updated_at)
           VALUES ('movie', 'X', 'Disponible', 'Sin petición', 'N/A', ?, 100, ?, ?, CURRENT_TIMESTAMP)""",
        (path, audio_languages, subtitle_languages),
    )
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def test_stops_at_unrenameable_when_path_missing(db_conn):
    # Accessibility/integrity are no longer checked here — they're checked for
    # real once the upload is queued (upload_queue.py's "integrity" stage).
    # A nonexistent path still fails fast, but now at "renameable": its parent
    # directory doesn't exist either, so it's not writable.
    iid = _movie_with_path(db_conn, "/nope/does/not/exist.mkv")
    r = uc.run_upload_checks(db_conn, iid)
    assert r["ready"] is False
    assert len(r["checks"]) == 1
    assert r["checks"][0]["id"] == "renameable" and r["checks"][0]["status"] == "fail"


def test_output_check_falls_back_to_bundled_uploadrr_path(db_conn, tmp_path, monkeypatch):
    """Regression: the bundled runtime (RUNTIME_EMU, the default) needs no
    configuration at all — DEFAULT_UPLOADRR_PATH (/opt/Uploadrr, or
    UPLOADRR_PATH) must be used when `uploadrr.path` was never set by hand,
    the same way uploadrr_contract.py::get_runtime_settings() already does
    for the actual upload command. Previously this check read the setting
    directly with no fallback, so it failed with "no configurado" even
    though the runtime it validates for doesn't require configuring it."""
    from emuwarez_uploadrr.services import uploadrr_contract as ctr
    monkeypatch.setattr(ctr, "DEFAULT_UPLOADRR_PATH", str(tmp_path))
    (tmp_path / "tmp").mkdir()  # Uploadrr-EMU stages output under <path>/tmp, not the root

    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 2048)
    iid = _movie_with_path(db_conn, str(f))
    r = uc.run_upload_checks(db_conn, iid)
    output_check = next(c for c in r["checks"] if c["id"] == "output")
    assert output_check["status"] == "ok"


def test_all_green_when_everything_passes(db_conn, tmp_path, monkeypatch):
    from emuwarez_uploadrr.services.settings import set_setting
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 2048)
    (tmp_path / "tmp").mkdir()  # Uploadrr-EMU stages output under <path>/tmp, not the root
    set_setting(db_conn, "qbit.url", "http://localhost:8080")     # so qBittorrent runs
    set_setting(db_conn, "uploadrr.path", str(tmp_path))           # writable output dir

    # Network checks all OK.
    import emuwarez_uploadrr.services.integration_tests as it
    monkeypatch.setattr(it, "test_qbit_connection", lambda **k: {"ok": True, "message": "ok"})
    monkeypatch.setattr(it, "test_emuwarez_connection", lambda **k: {"ok": True, "message": "ok"})
    import emuwarez_uploadrr.services.image_hosts as ih
    monkeypatch.setattr(ih, "test_image_host", lambda hid, key=None, **k: {"ok": True})

    iid = _movie_with_path(db_conn, str(f))
    r = uc.run_upload_checks(db_conn, iid)
    ids = [c["id"] for c in r["checks"]]
    assert ids == ["renameable", "spanish", "output", "qbittorrent", "imghosts", "emuwarez"]
    assert all(c["status"] == "ok" for c in r["checks"])
    assert r["ready"] is True


def test_emuwarez_check_does_not_enforce_rate_limit(db_conn, tmp_path, monkeypatch):
    """Regression: two uploads (manual or automático) queued within the same
    minute must not make the second one's "eMuwarez disponible" check fail
    with the 1/minute "Probar conexión" throttle — that throttle exists for
    the user-facing Settings button, not for this automated precondition."""
    from emuwarez_uploadrr.services.settings import set_setting
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 2048)
    (tmp_path / "tmp").mkdir()
    set_setting(db_conn, "qbit.url", "http://localhost:8080")
    set_setting(db_conn, "uploadrr.path", str(tmp_path))

    import emuwarez_uploadrr.services.integration_tests as it
    monkeypatch.setattr(it, "test_qbit_connection", lambda **k: {"ok": True, "message": "ok"})
    calls = []

    def _spy(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "message": "ok"}
    monkeypatch.setattr(it, "test_emuwarez_connection", _spy)
    import emuwarez_uploadrr.services.image_hosts as ih
    monkeypatch.setattr(ih, "test_image_host", lambda hid, key=None, **k: {"ok": True})

    iid = _movie_with_path(db_conn, str(f))
    uc.run_upload_checks(db_conn, iid)
    assert len(calls) == 1
    assert calls[0].get("enforce_rate_limit") is False


def test_skips_unconfigured_qbit(db_conn, tmp_path, monkeypatch):
    """qBittorrent not configured → yellow 'skip', non-blocking: the upload
    is still ready."""
    from emuwarez_uploadrr.services.settings import set_setting
    f = tmp_path / "movie.mkv"; f.write_bytes(b"x" * 2048)
    (tmp_path / "tmp").mkdir()  # Uploadrr-EMU stages output under <path>/tmp, not the root
    set_setting(db_conn, "uploadrr.path", str(tmp_path))
    # qbit.url intentionally not set → qbittorrent skip
    import emuwarez_uploadrr.services.integration_tests as it
    monkeypatch.setattr(it, "test_emuwarez_connection", lambda **k: {"ok": True, "message": "ok"})
    import emuwarez_uploadrr.services.image_hosts as ih
    monkeypatch.setattr(ih, "test_image_host", lambda hid, key=None, **k: {"ok": True})

    iid = _movie_with_path(db_conn, str(f))
    r = uc.run_upload_checks(db_conn, iid)
    by_id = {c["id"]: c for c in r["checks"]}
    assert by_id["qbittorrent"]["status"] == "skip"
    assert r["ready"] is True  # skips don't block


def test_stops_at_qbit_before_emuwarez(db_conn, tmp_path, monkeypatch):
    from emuwarez_uploadrr.services.settings import set_setting
    f = tmp_path / "m.mkv"; f.write_bytes(b"x" * 2048)
    (tmp_path / "tmp").mkdir()  # Uploadrr-EMU stages output under <path>/tmp, not the root
    set_setting(db_conn, "qbit.url", "http://localhost:8080")   # configured → qbit runs
    set_setting(db_conn, "uploadrr.path", str(tmp_path))
    import emuwarez_uploadrr.services.integration_tests as it
    monkeypatch.setattr(it, "test_qbit_connection", lambda **k: {"ok": False, "message": "caído"})
    # eMuwarez must NOT be reached — make it explode if called.
    monkeypatch.setattr(it, "test_emuwarez_connection", lambda **k: (_ for _ in ()).throw(AssertionError("no debe llamarse")))

    iid = _movie_with_path(db_conn, str(f))
    r = uc.run_upload_checks(db_conn, iid)
    ids = [c["id"] for c in r["checks"]]
    assert ids[-1] == "qbittorrent" and r["checks"][-1]["status"] == "fail"
    assert "emuwarez" not in ids
    assert r["ready"] is False


# ---------------------------------------------------------------------------
# Castilian: present in the audio OR in the subtitles
# ---------------------------------------------------------------------------

def _spanish_check(conn, item_id):
    return next(c for c in uc.run_upload_checks(conn, item_id)["checks"] if c["id"] == "spanish")


def test_castilian_audio_needs_no_subtitles(db_conn, tmp_path):
    f = tmp_path / "peli.mkv"; f.write_bytes(b"x")
    iid = _movie_with_path(db_conn, str(f), audio_languages="spa", subtitle_languages=None)
    assert _spanish_check(db_conn, iid)["status"] == "ok"


def test_castilian_subtitles_are_enough_without_castilian_audio(db_conn, tmp_path):
    f = tmp_path / "peli.mkv"; f.write_bytes(b"x")
    iid = _movie_with_path(db_conn, str(f), audio_languages="eng", subtitle_languages="spa / eng")
    assert _spanish_check(db_conn, iid)["status"] == "ok"


def test_blocked_when_neither_audio_nor_subtitles_are_castilian(db_conn, tmp_path):
    f = tmp_path / "peli.mkv"; f.write_bytes(b"x")
    iid = _movie_with_path(db_conn, str(f), audio_languages="eng", subtitle_languages="eng")
    r = uc.run_upload_checks(db_conn, iid)
    assert r["ready"] is False
    check = next(c for c in r["checks"] if c["id"] == "spanish")
    assert check["status"] == "fail"
    # Says what it actually found, so it's obvious what to fix.
    assert "eng" in check["message"]


def test_latin_only_audio_without_castilian_subtitles_is_blocked(db_conn, tmp_path):
    f = tmp_path / "peli.mkv"; f.write_bytes(b"x")
    iid = _movie_with_path(db_conn, str(f), audio_languages="es-419", subtitle_languages="es-419")
    assert _spanish_check(db_conn, iid)["status"] == "fail"


def test_unknown_languages_block_instead_of_passing(db_conn, tmp_path):
    """"We never read this file" is not evidence that it meets the rule."""
    f = tmp_path / "peli.mkv"; f.write_bytes(b"x")
    iid = _movie_with_path(db_conn, str(f), audio_languages=None, subtitle_languages=None)
    assert _spanish_check(db_conn, iid)["status"] == "fail"


def test_the_rule_is_the_same_for_a_single_episode(db_conn, tmp_path):
    f = tmp_path / "cap.mkv"; f.write_bytes(b"x")
    db_conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status,
            nomenclature_status, path, size_bytes, audio_languages, subtitle_languages, updated_at)
           VALUES ('episode', 'Serie S01E01', 'Disponible', 'Sin petición', 'N/A', ?, 100,
                   'spa', NULL, CURRENT_TIMESTAMP)""",
        (str(f),),
    )
    db_conn.commit()
    iid = db_conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]
    assert _spanish_check(db_conn, iid)["status"] == "ok"


# ---------------------------------------------------------------------------
# Reparto en dos grupos: lo del elemento va una vez por elemento, lo del
# entorno una sola vez para toda la tanda
# ---------------------------------------------------------------------------

def test_content_scope_only_runs_the_per_item_checks(db_conn, tmp_path):
    """Con 30 capítulos elegidos, estas sí van 30 veces: dependen del fichero."""
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 2048)
    iid = _movie_with_path(db_conn, str(f))
    r = uc.run_upload_checks(db_conn, iid, scope="content")
    ids = {c["id"] for c in r["checks"]}
    assert ids <= set(uc.CONTENT_CHECK_IDS), ids
    assert not (ids & set(uc.ENVIRONMENT_CHECK_IDS))


def test_environment_scope_never_touches_the_item(db_conn, tmp_path):
    """Y estas van una sola vez: preguntarle a eMuwarez 30 veces si está vivo
    no aporta nada y multiplica por 30 la espera. Con un item_id que no existe
    tienen que salir igual, porque no dependen de él."""
    r = uc.run_upload_checks(db_conn, 999999, scope="environment")
    ids = {c["id"] for c in r["checks"]}
    assert ids <= set(uc.ENVIRONMENT_CHECK_IDS), ids
    assert not (ids & set(uc.CONTENT_CHECK_IDS))
    # Y no se cuela el "Elemento no encontrado" del camino normal.
    assert not any(c.get("message") == "Elemento no encontrado" for c in r["checks"])


def test_the_two_scopes_together_cover_exactly_the_full_run(db_conn, tmp_path, monkeypatch):
    """Partir no puede perder ni duplicar comprobaciones: contenido + entorno
    tiene que dar lo mismo que la pasada completa de siempre."""
    from emuwarez_uploadrr.services import uploadrr_contract as ctr
    monkeypatch.setattr(ctr, "DEFAULT_UPLOADRR_PATH", str(tmp_path))
    (tmp_path / "tmp").mkdir()
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 2048)
    iid = _movie_with_path(db_conn, str(f))

    full = [c["id"] for c in uc.run_upload_checks(db_conn, iid)["checks"]]
    content = [c["id"] for c in uc.run_upload_checks(db_conn, iid, scope="content")["checks"]]
    env = [c["id"] for c in uc.run_upload_checks(db_conn, iid, scope="environment")["checks"]]
    assert content + env == full


def test_a_failed_content_check_is_not_ready(db_conn, tmp_path):
    """Lo que hace que al pulsar Subir se avise de qué elemento no puede ir."""
    iid = _movie_with_path(db_conn, str(tmp_path / "no-existe" / "movie.mkv"))
    r = uc.run_upload_checks(db_conn, iid, scope="content")
    assert r["ready"] is False
    assert any(c["status"] == "fail" for c in r["checks"])
