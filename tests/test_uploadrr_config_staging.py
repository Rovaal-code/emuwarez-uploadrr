"""Tests for Uploadrr-EMU data/config.yaml staging (Phase 10E).

Every test operates exclusively under tmp_path — this module (and these
tests) never touch a real Uploadrr/ installation.
"""
from __future__ import annotations

from emuwarez_uploadrr.services.uploadrr_yaml import get_child_inline_mapping
from emuwarez_uploadrr.services.uploadrr_config_staging import (
    QBIT_CLIENT_KEY,
    SCREENS_API_KEY_HOSTS,
    backup_config,
    build_redacted_preview,
    diff_staged_changes,
    get_tmdb_key,
    read_config_lines,
    restore_config_from_backup,
    stage_emu_config,
    stage_image_hosts,
    stage_qbittorrent_config,
    stage_tmdb_key,
    write_staged_config,
)


def test_read_config_lines_missing_file_returns_empty(tmp_path):
    assert read_config_lines(tmp_path / "config.yaml") == []


def test_stage_tmdb_key_sets_default_tmdb():
    lines = ["DEFAULT:", "  other: 1"]
    staged, message = stage_tmdb_key(lines, "TMDB_REAL_KEY")
    assert get_tmdb_key(staged) == "TMDB_REAL_KEY"
    assert "creado" in message or "actualizado" in message


def test_stage_tmdb_key_does_not_mutate_original_lines():
    lines = ["DEFAULT:", "  tmdb: 'old'"]
    staged, _ = stage_tmdb_key(lines, "new_key")
    assert get_tmdb_key(lines) == "old"
    assert get_tmdb_key(staged) == "new_key"


def test_stage_emu_config_sets_api_key_and_anon():
    lines: list[str] = []
    staged, message = stage_emu_config(lines, api_key="EMU_REAL_KEY", anon=True)
    text = "\n".join(staged)
    assert "EMU_REAL_KEY" in text
    assert "anon: True" in text or "anon: true" in text.lower()


def test_stage_image_hosts_sets_ordered_img_hosts_list():
    lines = ["SCREENS:", "  img_hosts: [imgbox]"]
    staged, message = stage_image_hosts(lines, img_hosts=["pixhost", "imgbb", "imgbox"])
    text = "\n".join(staged)
    assert "img_hosts: [pixhost, imgbb, imgbox]" in text
    assert "creado" in message or "actualizado" in message


def test_stage_image_hosts_sets_api_keys_inline_mapping():
    lines: list[str] = []
    staged, _ = stage_image_hosts(lines, api_keys={"imgbb": "IMGBB_REAL_KEY", "lensdump": "LENSDUMP_REAL_KEY"})
    text = "\n".join(staged)
    assert "IMGBB_REAL_KEY" in text
    assert "LENSDUMP_REAL_KEY" in text
    assert "API_KEYS" in text


def test_stage_image_hosts_skips_untouched_sections_when_nothing_given():
    lines = ["SCREENS:", "  img_hosts: [imgbox]"]
    staged, message = stage_image_hosts(lines)
    assert staged == lines
    assert message == "SCREENS sin cambios"


def test_stage_image_hosts_only_stages_hosts_that_take_a_key():
    """imghost.dev estaba excluido suponiendo que su clave iba en otro bloque
    del config del fork. Es un CheveretoTemplate como los demás y lee
    SCREENS.API_KEYS, así que sin ella revienta."""
    assert "imghost" in SCREENS_API_KEY_HOSTS
    # Los que no llevan clave no se cuelan.
    assert "imgbox" not in SCREENS_API_KEY_HOSTS


def test_stage_qbittorrent_config_sets_credentials_and_default_client():
    lines: list[str] = []
    staged, message = stage_qbittorrent_config(
        lines, url="http://192.168.1.10:8080", username="admin", password="secret",
    )
    mapping = get_child_inline_mapping(staged, "TORRENT_CLIENTS", QBIT_CLIENT_KEY)
    assert mapping["qbit_url"] == "http://192.168.1.10"
    assert mapping["qbit_port"] == "8080"
    assert mapping["qbit_user"] == "admin"
    assert mapping["qbit_pass"] == "secret"
    assert mapping["torrent_client"] == "qbit"
    text = "\n".join(staged)
    assert "default_torrent_client: 'qbit'" in text
    assert "creado" in message or "actualizado" in message


def test_stage_qbittorrent_config_overrides_stale_default_torrent_client():
    # Confirmed against the fork's own bundled example config.yaml: it ships
    # with "watch", not "qbit" — this is the actual bug that made a job
    # finish "successfully" while silently never touching qBittorrent's API.
    lines = ["DEFAULT:", "  default_torrent_client: watch"]
    staged, _ = stage_qbittorrent_config(lines, url="http://x:8080", username="u", password="p")
    text = "\n".join(staged)
    assert "default_torrent_client: watch" not in text
    assert "default_torrent_client: 'qbit'" in text


def test_stage_qbittorrent_config_preserves_unmanaged_existing_keys(tmp_path):
    # torrent_storage_dir/content_layout/enable_search aren't fields we
    # manage — overwriting the whole inline mapping wholesale would silently
    # wipe out whatever the user (or the fork's own template) already had
    # configured there.
    lines = [
        "TORRENT_CLIENTS:",
        "  qbit: {'torrent_client': 'qbit', 'enable_search': True, 'qbit_url': 'http://old', "
        f"'torrent_storage_dir': '{tmp_path.as_posix()}', 'content_layout': 'Original'}}",
    ]
    staged, _ = stage_qbittorrent_config(lines, url="http://new:9090", username="u2", password="p2")
    mapping = get_child_inline_mapping(staged, "TORRENT_CLIENTS", QBIT_CLIENT_KEY)
    assert mapping["qbit_url"] == "http://new"
    assert mapping["enable_search"] is True
    assert mapping["torrent_storage_dir"] == tmp_path.as_posix()
    assert mapping["content_layout"] == "Original"


def test_stage_qbittorrent_config_drops_a_storage_dir_that_does_not_exist():
    """El config de ejemplo del fork trae una ruta de macOS y cada subida
    acababa con "Invalid torrent_storage_dir path" en rojo. Si la carpeta no
    existe no hay .torrent que reutilizar, y buscar en qBittorrent tampoco
    sirve de nada."""
    lines = [
        "TORRENT_CLIENTS:",
        "  qbit: {'torrent_client': 'qbit', 'enable_search': True, "
        "'torrent_storage_dir': '/Users/example/Library/Application Support/qBittorrent/BT_backup', "
        "'content_layout': 'Original'}",
    ]
    staged, _ = stage_qbittorrent_config(lines, url="http://x:8080", username="u", password="p")
    mapping = get_child_inline_mapping(staged, "TORRENT_CLIENTS", QBIT_CLIENT_KEY)
    assert "torrent_storage_dir" not in mapping
    assert mapping["enable_search"] is False
    assert mapping["content_layout"] == "Original"


def test_stage_qbittorrent_config_resolves_a_relative_storage_dir_against_uploadrr(tmp_path):
    """El fork corre con cwd en su carpeta, así que una ruta relativa se
    comprueba contra ella y no contra la carpeta de la app."""
    (tmp_path / "BT_backup").mkdir()
    lines = [
        "TORRENT_CLIENTS:",
        "  qbit: {'torrent_client': 'qbit', 'enable_search': True, 'torrent_storage_dir': 'BT_backup'}",
    ]
    staged, _ = stage_qbittorrent_config(
        lines, url="http://x:8080", username="u", password="p", base_dir=str(tmp_path),
    )
    mapping = get_child_inline_mapping(staged, "TORRENT_CLIENTS", QBIT_CLIENT_KEY)
    assert mapping["torrent_storage_dir"] == "BT_backup"
    assert mapping["enable_search"] is True


def test_stage_blu_api_off_turns_off_the_blutopia_lookup():
    """Con useAPI activado el fork pregunta a Blutopia por el nombre de cada
    fichero ("Failed to search: HTTP 400" con la clave de ejemplo)."""
    from emuwarez_uploadrr.services.uploadrr_config_staging import stage_blu_api_off
    lines = [
        "TRACKERS:",
        "  BLU:",
        "    useAPI: true",
        "    api_key: \"BLU_API_KEY\"",
        "  EMU:",
        "    useAPI: true",
    ]
    staged, message = stage_blu_api_off(lines)
    assert staged[2] == "    useAPI: false"
    # El resto, incluido el useAPI de otro tracker, no se toca.
    assert staged[3:] == lines[3:]
    assert message == "TRACKERS.BLU.useAPI actualizado"


def test_stage_blu_api_off_leaves_a_config_without_blu_alone():
    from emuwarez_uploadrr.services.uploadrr_config_staging import stage_blu_api_off
    lines = ["TRACKERS:", "  EMU:", "    useAPI: true"]
    staged, message = stage_blu_api_off(lines)
    assert staged == lines
    assert message == "TRACKERS.BLU sin cambios"


def test_get_child_inline_mapping_returns_empty_when_absent():
    assert get_child_inline_mapping([], "TORRENT_CLIENTS", "qbit") == {}


def test_backup_config_creates_bak_file(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("DEFAULT:\n  tmdb: 'k'\n")
    backup_path = backup_config(config_path)
    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.read_text() == config_path.read_text()


def test_backup_config_missing_file_returns_none(tmp_path):
    assert backup_config(tmp_path / "does-not-exist.yaml") is None


def test_backup_config_does_not_overwrite_existing_backup(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("v1")
    backup_config(config_path)
    config_path.write_text("v2")
    backup_config(config_path)  # should NOT overwrite the .bak with v2
    backup_path = config_path.with_suffix(config_path.suffix + ".bak")
    assert backup_path.read_text() == "v1"


def test_write_staged_config_creates_backup_before_overwrite(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("DEFAULT:\n  tmdb: 'old'\n")
    write_staged_config(config_path, ["DEFAULT:", "  tmdb: 'new'"])

    backup_path = config_path.with_suffix(config_path.suffix + ".bak")
    assert backup_path.exists()
    assert "old" in backup_path.read_text()
    assert "new" in config_path.read_text()


def test_write_staged_config_creates_parent_dirs(tmp_path):
    config_path = tmp_path / "nested" / "data" / "config.yaml"
    write_staged_config(config_path, ["DEFAULT:", "  tmdb: 'x'"])
    assert config_path.exists()


def test_restore_config_from_backup(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("original")
    backup_config(config_path)
    config_path.write_text("modified")

    restored = restore_config_from_backup(config_path)
    assert restored is True
    assert config_path.read_text() == "original"


def test_restore_config_from_backup_no_backup_returns_false(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("only version")
    assert restore_config_from_backup(config_path) is False


def test_build_redacted_preview_hides_tmdb_and_api_key():
    lines = ["DEFAULT:", "  tmdb: 'REALTMDBKEY'", "TRACKERS:", "  EMU:", "    api_key: 'REALEMUKEY'"]
    preview = build_redacted_preview(lines)
    text = "\n".join(preview)
    assert "REALTMDBKEY" not in text
    assert "REALEMUKEY" not in text
    assert "***REDACTED:" in text


def test_diff_staged_changes_redacts_secrets():
    old_lines = ["DEFAULT:", "  tmdb: 'OLDKEY'"]
    new_lines, _ = stage_tmdb_key(old_lines, "NEWKEY")
    diff = diff_staged_changes(old_lines, new_lines)
    diff_text = "\n".join(diff)
    assert "OLDKEY" not in diff_text
    assert "NEWKEY" not in diff_text
    assert any(line.startswith(("+", "-")) for line in diff if not line.startswith(("+++", "---")))


def test_never_touches_real_uploadrr_path(tmp_path):
    """Structural guard: config_path is always caller-supplied (tmp_path in
    tests) — nothing in this module hardcodes or defaults to a real
    Uploadrr/ install path."""
    import emuwarez_uploadrr.services.uploadrr_config_staging as mod
    import inspect

    source = inspect.getsource(mod)
    assert "uploadrr_dir(" not in source
    assert "Uploadrr/data/config.yaml" not in source


def test_stage_qbittorrent_splits_the_url_the_way_the_fork_expects():
    """La app guarda una sola url con el puerto dentro; el cliente qBittorrent
    del fork quiere host y puerto en dos claves (src/clients.py:
    host=qbit_url, port=qbit_port)."""
    from emuwarez_uploadrr.services.uploadrr_config_staging import stage_qbittorrent_config
    from emuwarez_uploadrr.services.uploadrr_yaml import get_child_inline_mapping
    lines = ["TORRENT_CLIENTS:", "  qbit: {'torrent_client': 'qbit'}"]
    staged, _ = stage_qbittorrent_config(
        lines, url="http://192.168.0.136:8082", username="u", password="p")
    m = get_child_inline_mapping(staged, "TORRENT_CLIENTS", "qbit")
    assert m["qbit_url"] == "http://192.168.0.136"
    assert m["qbit_port"] == "8082"


def test_stage_qbittorrent_writes_the_tag_the_fork_reads():
    """qbit_tag es la clave que el fork aplica al torrent (clients.py:634)."""
    from emuwarez_uploadrr.services.uploadrr_config_staging import stage_qbittorrent_config
    from emuwarez_uploadrr.services.uploadrr_yaml import get_child_inline_mapping
    lines = ["TORRENT_CLIENTS:", "  qbit: {'torrent_client': 'qbit'}"]
    staged, _ = stage_qbittorrent_config(
        lines, url="http://h:1", username="u", password="p", tag="Subidas")
    assert get_child_inline_mapping(staged, "TORRENT_CLIENTS", "qbit")["qbit_tag"] == "Subidas"


def test_clearing_the_tag_removes_it_from_the_fork_config():
    """Vaciar el campo en Ajustes tiene que quitar la etiqueta de verdad, no
    dejar la anterior puesta para siempre."""
    from emuwarez_uploadrr.services.uploadrr_config_staging import stage_qbittorrent_config
    from emuwarez_uploadrr.services.uploadrr_yaml import get_child_inline_mapping
    lines = ["TORRENT_CLIENTS:", "  qbit: {'torrent_client': 'qbit', 'qbit_tag': 'Vieja'}"]
    for tag in ("", None, "   "):
        staged, _ = stage_qbittorrent_config(
            lines, url="http://h:1", username="u", password="p", tag=tag)
        assert "qbit_tag" not in get_child_inline_mapping(staged, "TORRENT_CLIENTS", "qbit")


def test_stage_add_logo_writes_the_key_the_fork_reads():
    """DEFAULT.add_logo es lo que mira src/utils/descgen.py del fork para
    incrustar el logo en la descripción."""
    from emuwarez_uploadrr.services.uploadrr_config_staging import stage_add_logo
    from emuwarez_uploadrr.services.uploadrr_yaml import get_block_key
    lines = ["DEFAULT:", "  tmdb: xxx", "  add_logo: true"]
    for enabled, expected in ((False, "false"), (True, "true")):
        staged, _ = stage_add_logo(lines, enabled)
        assert get_block_key(staged, "DEFAULT", "add_logo") == expected


def test_stage_add_logo_creates_the_key_when_the_config_lacks_it():
    from emuwarez_uploadrr.services.uploadrr_config_staging import stage_add_logo
    from emuwarez_uploadrr.services.uploadrr_yaml import get_block_key
    staged, _ = stage_add_logo(["DEFAULT:", "  tmdb: xxx"], False)
    assert get_block_key(staged, "DEFAULT", "add_logo") == "false"


def test_every_host_that_needs_a_key_gets_it_staged():
    """La lista de claves que se escriben en el config del fork estaba puesta a
    mano y se quedó en cinco: hamster e imghost.dev también necesitan clave y
    no estaban. Configurabas la suya en Ajustes, se guardaba, y la subida
    fallaba igual porque nunca llegaba allí.

    Derivarla de IMAGE_HOSTS lo arregla; este test es lo que impide que vuelva
    a separarse cuando se añada el octavo proveedor."""
    from emuwarez_uploadrr.services.uploadrr_config_staging import SCREENS_API_KEY_HOSTS
    from emuwarez_uploadrr.services.image_hosts import IMAGE_HOSTS
    esperados = {h["id"] for h in IMAGE_HOSTS if h["needs_key"]}
    assert set(SCREENS_API_KEY_HOSTS) == esperados
    # Y ninguno de los que NO necesitan clave se cuela.
    assert not (set(SCREENS_API_KEY_HOSTS) & {h["id"] for h in IMAGE_HOSTS if not h["needs_key"]})
