"""El registro de ajustes describe las claves; lo que lee de él se comporta como antes."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import ajustes_registro as reg
from emuwarez_uploadrr.services.settings import es_secreto, leer_bool, set_setting


def test_secretos_conocidos_y_prefijo_de_hosts():
    for clave in ("tmdb.api_key", "emu.api_key", "emu.endpoint_url", "tmdb_api_key",
                  "qbit.password", "qbit.qui_proxy_url", "notify.discord.webhook_url",
                  "notify.telegram.bot_token", "imghost.key.imgbb"):
        assert es_secreto(clave), clave
    for clave in ("emu.username", "qbit.url", "emu.add_logo", "uploadrr.path"):
        assert not es_secreto(clave), clave


@pytest.mark.parametrize("clave,defecto", [
    ("tmdb.localize_series_titles", True), ("series.ignore_specials", True), ("emu.add_logo", True),
    ("notify.discord.enabled", False), ("notify.telegram.enabled", False),
    ("source_engine.enabled", False), ("emu.per_episode_screens", False),
    ("remux.no_reflink_copies", False),
])
def test_bool_sin_guardar_o_vacio_vale_el_defecto(clave, defecto):
    assert reg.bool_de(clave, None) is defecto
    assert reg.bool_de(clave, "") is defecto


def test_bool_guardado_manda_sobre_el_defecto():
    assert reg.bool_de("emu.add_logo", "false") is False
    assert reg.bool_de("emu.add_logo", "true") is True
    assert reg.bool_de("source_engine.enabled", "true") is True
    assert reg.bool_de("source_engine.enabled", "false") is False


def test_bool_de_rechaza_lo_que_no_es_si_no():
    with pytest.raises(ValueError):
        reg.bool_de("tmdb.api_key", "true")


def test_leer_bool_desde_la_base(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    from emuwarez_uploadrr.database import connect, init_db, db_path
    conn = connect(db_path())
    init_db(conn)
    assert leer_bool(conn, "emu.add_logo") is True
    set_setting(conn, "emu.add_logo", "false")
    assert leer_bool(conn, "emu.add_logo") is False
    assert leer_bool(conn, "source_engine.enabled") is False
    set_setting(conn, "source_engine.enabled", "true")
    assert leer_bool(conn, "source_engine.enabled") is True
    conn.close()


def test_claves_secretas_son_las_del_registro():
    assert reg.claves_secretas() == frozenset(a.clave for a in reg.REGISTRO.values() if a.secreto)
