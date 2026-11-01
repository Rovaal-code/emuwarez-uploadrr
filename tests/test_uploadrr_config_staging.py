"""Tests for Uploadrr-EMU data/config.yaml staging (Phase 10E).

Every test operates exclusively under tmp_path — this module (and these
tests) never touch a real Uploadrr/ installation.
"""
from __future__ import annotations

import pytest

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


def test_stage_qbittorrent_config_treats_an_unreadable_storage_dir_as_missing(monkeypatch):
    """Si comprobar la carpeta da error (sin permisos), se trata como que no
    está en vez de tumbar el staging entero."""
    llamadas = []

    def sin_permiso(*args, **kwargs):
        llamadas.append(args)
        raise PermissionError("denegado")

    monkeypatch.setattr("os.stat", sin_permiso)
    lines = [
        "TORRENT_CLIENTS:",
        "  qbit: {'torrent_client': 'qbit', 'enable_search': True, 'torrent_storage_dir': '/protegida/BT_backup'}",
    ]
    staged, _ = stage_qbittorrent_config(lines, url="http://x:8080", username="u", password="p")
    mapping = get_child_inline_mapping(staged, "TORRENT_CLIENTS", QBIT_CLIENT_KEY)
    assert "torrent_storage_dir" not in mapping
    assert mapping["enable_search"] is False
    # Que de verdad se llegó a mirar la carpeta, no que se saltó la comprobación.
    assert llamadas


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


def test_stage_per_episode_screens_leaves_only_the_first_episode_by_default():
    """SCREENS.per_episode a 0 es lo que hace que el fork solo capture el primer
    capítulo de un pack; con todos se respeta el valor del config."""
    from emuwarez_uploadrr.services.uploadrr_config_staging import stage_per_episode_screens
    from emuwarez_uploadrr.services.uploadrr_yaml import get_block_key
    lines = ["SCREENS:", "  per_episode: 3 # for tv will take x screens for every episode"]
    staged, _ = stage_per_episode_screens(lines, False)
    assert get_block_key(staged, "SCREENS", "per_episode") == "0"
    staged, _ = stage_per_episode_screens(lines, True)
    assert staged == lines


def test_stage_uploadrr_config_screenshots_only_the_first_episode_unless_asked(tmp_path, monkeypatch):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.upload_execution import config as ue
    from emuwarez_uploadrr.services.settings import set_setting
    from emuwarez_uploadrr.services.uploadrr_yaml import get_block_key
    config = tmp_path / "Uploadrr" / "data" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("DEFAULT:\n  tmdb: ''\nSCREENS:\n  per_episode: 3\n", encoding="utf-8")
    monkeypatch.setattr(ue, "append_upload_log", lambda *a, **k: None)

    assert ue._stage_uploadrr_config(1, str(tmp_path / "Uploadrr")) == config
    assert get_block_key(read_config_lines(config), "SCREENS", "per_episode") == "0"

    restore_config_from_backup(config)
    conn = connect()
    init_db(conn)
    set_setting(conn, "emu.per_episode_screens", "true")
    conn.commit()
    conn.close()
    ue._stage_uploadrr_config(1, str(tmp_path / "Uploadrr"))
    assert get_block_key(read_config_lines(config), "SCREENS", "per_episode") == "3"


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


def test_stage_qbittorrent_config_with_qui_only():
    """Con el proxy de qui no hacen falta url ni credenciales: Uploadrr-EMU habla por qui."""
    lines = ["DEFAULT:", "  default_torrent_client: watch"]
    staged, _ = stage_qbittorrent_config(lines, qui_proxy_url=" http://qui:7476/proxy/clave ")
    mapping = get_child_inline_mapping(staged, "TORRENT_CLIENTS", QBIT_CLIENT_KEY)
    assert mapping["qui_proxy_url"] == "http://qui:7476/proxy/clave"
    assert "qbit_url" not in mapping and "qbit_pass" not in mapping
    assert "default_torrent_client: 'qbit'" in "\n".join(staged)


def test_stage_qbittorrent_config_without_qui_drops_a_previous_one():
    lines = ["TORRENT_CLIENTS:", "  qbit: {'torrent_client': 'qbit', 'qui_proxy_url': 'http://qui/proxy/vieja'}"]
    staged, _ = stage_qbittorrent_config(lines, url="http://x:8080", username="u", password="p")
    assert "qui_proxy_url" not in get_child_inline_mapping(staged, "TORRENT_CLIENTS", QBIT_CLIENT_KEY)


# --- EJEC-1: contraseñas y claves con caracteres que YAML trata aparte --------

_VALORES_DIFICILES = [
    "a\\b", "\\", "\\\\", "it's \"q\"", "'", "''", "tab\taqui", "con # almohadilla",
    "con: dos puntos", "llaves } { y , comas [ ]", "ñandú", "  con espacios  ", "true", "123",
    "dos\nlineas", "retorno\r\ny tab\t", "control\x01", "\x7f", "nel\x85", "separador\u2028", "mezcla \"q\" \n \\ '",
]


@pytest.mark.parametrize("valor", _VALORES_DIFICILES, ids=repr)
def test_la_contrasena_de_qbittorrent_se_lee_igual_que_se_escribio(valor):
    """repr() de Python escapaba con la barra invertida (que YAML no entiende
    entre comillas simples): una contraseña con ella se leía mal, y con las dos
    comillas el config.yaml no se podía leer."""
    yaml = pytest.importorskip("yaml")
    staged, _ = stage_qbittorrent_config([], url="http://x:8080", username=valor, password=valor)

    cargado = yaml.safe_load("\n".join(staged))["TORRENT_CLIENTS"][QBIT_CLIENT_KEY]
    assert cargado["qbit_pass"] == valor
    assert cargado["qbit_user"] == valor
    assert cargado["enable_search"] is False
    mapa = get_child_inline_mapping(staged, "TORRENT_CLIENTS", QBIT_CLIENT_KEY)
    assert mapa["qbit_pass"] == valor and mapa["qbit_user"] == valor


@pytest.mark.parametrize("valor", _VALORES_DIFICILES, ids=repr)
def test_la_clave_de_un_host_de_imagenes_se_lee_igual_que_se_escribio(valor):
    yaml = pytest.importorskip("yaml")
    staged, _ = stage_image_hosts([], api_keys={"imgbb": valor, "ptpimg": "otra"})

    assert yaml.safe_load("\n".join(staged))["SCREENS"]["API_KEYS"] == {"imgbb": valor, "ptpimg": "otra"}


def test_las_listas_de_un_cliente_sobreviven_al_staging():
    """Uploadrr acepta una lista en automatic_management_paths: perderla (o
    convertirla en una cadena) se llevaba por delante el resto de la entrada."""
    yaml = pytest.importorskip("yaml")
    lines = [
        "TORRENT_CLIENTS:",
        "  qbit: {'torrent_client': 'qbit', 'automatic_management_paths': ['/data/tv', '/data/mo vies', 'it''s'], "
        "'content_layout': 'Original'}",
    ]
    staged, _ = stage_qbittorrent_config(lines, url="http://x:8080", username="u", password="p")

    cargado = yaml.safe_load("\n".join(staged))["TORRENT_CLIENTS"][QBIT_CLIENT_KEY]
    assert cargado["automatic_management_paths"] == ["/data/tv", "/data/mo vies", "it's"]
    assert cargado["content_layout"] == "Original"
    assert cargado["qbit_pass"] == "p"
    assert get_child_inline_mapping(staged, "TORRENT_CLIENTS", QBIT_CLIENT_KEY)["automatic_management_paths"] == [
        "/data/tv", "/data/mo vies", "it's"]


def test_las_palabras_booleanas_de_yaml_11_se_leen_como_booleanos():
    """PyYAML (el que lee Uploadrr) toma `no` como False: guardarlo como la
    cadena 'no' dejaba la verificación del certificado activa."""
    lines = ["TORRENT_CLIENTS:", "  qbit: {VERIFY_WEBUI_CERTIFICATE: no, enable_search: Yes, other: off, on: 'no'}"]
    mapa = get_child_inline_mapping(lines, "TORRENT_CLIENTS", QBIT_CLIENT_KEY)
    assert mapa == {"VERIFY_WEBUI_CERTIFICATE": False, "enable_search": True, "other": False, "on": "no"}


def test_lo_que_pyyaml_lee_de_una_entrada_existente_es_lo_que_se_reescribe():
    """Escapes de comillas dobles de YAML que no son los de Python (la barra
    escapada, el guion bajo) y enteros con ceros delante (`08` es una cadena,
    `7` un entero): el valor y su tipo tienen que ser los mismos que ve Uploadrr
    al releer el config."""
    yaml = pytest.importorskip("yaml")
    lines = [
        "TORRENT_CLIENTS:",
        '  qbit: {automatic_management_paths: ["\\/data\\/tv", "a\\_b\\Nc", \'/data/it\'\'s\'], '
        "qbit_port: 8080, ceros: [08, 7, 0, -3], decimal: 1.5, texto: 08, nulos: [none, None, null, Null, ~], otra: none}",
    ]
    original = yaml.safe_load("\n".join(lines))["TORRENT_CLIENTS"][QBIT_CLIENT_KEY]

    staged, _ = stage_qbittorrent_config(lines, url="http://x:8080", username="u", password="p")

    cargado = yaml.safe_load("\n".join(staged))["TORRENT_CLIENTS"][QBIT_CLIENT_KEY]
    for clave in ("automatic_management_paths", "ceros", "decimal", "texto", "nulos", "otra"):
        assert cargado[clave] == original[clave], clave
        assert type(cargado[clave]) is type(original[clave]), clave
    assert cargado["ceros"] == ["08", 7, 0, -3]
    assert cargado["nulos"] == ["none", "None", None, None, None]  # `none` es una cadena, no null
    assert cargado["automatic_management_paths"][0] == "/data/tv"


def test_el_config_de_ejemplo_del_fork_se_sigue_leyendo():
    lines = [
        "TORRENT_CLIENTS:",
        "  qbit: {'torrent_client': 'qbit', 'enable_search': True, 'qbit_url': 'http://127.0.0.1', "
        "'qbit_port': '8080', 'content_layout': 'Original', 'VERIFY_WEBUI_CERTIFICATE': False} # un comentario",
    ]
    assert get_child_inline_mapping(lines, "TORRENT_CLIENTS", "qbit") == {
        "torrent_client": "qbit", "enable_search": True, "qbit_url": "http://127.0.0.1",
        "qbit_port": "8080", "content_layout": "Original", "VERIFY_WEBUI_CERTIFICATE": False,
    }


# --- EJEC-4: el config de verdad es el .bak, no lo que dejó una subida muerta -

def _config_falso(tmp_path):
    config = tmp_path / "Uploadrr" / "data" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("DEFAULT:\n  tmdb: ''\nSCREENS:\n  per_episode: 3\n", encoding="utf-8")
    return config


def _poner_ajuste(clave, valor):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services.settings import set_setting
    conn = connect()
    init_db(conn)
    set_setting(conn, clave, valor)
    conn.commit()
    conn.close()


def _per_episode(config):
    from emuwarez_uploadrr.services.uploadrr_yaml import get_block_key
    return get_block_key(read_config_lines(config), "SCREENS", "per_episode")


def test_tras_un_corte_la_siguiente_subida_parte_del_backup(tmp_path, monkeypatch):
    """Una subida muerta dejaba el config stageado (per_episode: 0), y la
    siguiente, que quería todos los capítulos, «dejaba el valor del config»: el suyo."""
    from emuwarez_uploadrr.services.upload_execution import config as ue
    config = _config_falso(tmp_path)
    monkeypatch.setattr(ue, "append_upload_log", lambda *a, **k: None)
    cwd = str(tmp_path / "Uploadrr")

    ue._stage_uploadrr_config(1, cwd)
    assert _per_episode(config) == "0"  # y la subida muere sin restaurar

    _poner_ajuste("emu.per_episode_screens", "true")
    ue._stage_uploadrr_config(2, cwd)

    assert _per_episode(config) == "3"


def test_restore_stale_config_solo_restaura_si_difiere(tmp_path):
    from emuwarez_uploadrr.services.uploadrr_config_staging import restore_stale_config
    config = _config_falso(tmp_path)
    assert restore_stale_config(config) is False  # sin .bak

    backup_config(config)
    assert restore_stale_config(config) is False  # igual que el .bak

    config.write_text("stageado", encoding="utf-8")
    assert restore_stale_config(config) is True
    assert config.read_bytes() == config.with_suffix(".yaml.bak").read_bytes()


def test_escribir_y_restaurar_no_dejan_ficheros_temporales(tmp_path):
    config = _config_falso(tmp_path)
    write_staged_config(config, ["DEFAULT:", "  tmdb: 'x'"])
    restore_config_from_backup(config)

    assert sorted(p.name for p in config.parent.iterdir()) == ["config.yaml", "config.yaml.bak"]


def test_al_arrancar_se_restaura_el_config_que_dejo_una_subida_muerta(tmp_path):
    from emuwarez_uploadrr.services.upload_execution import config as ue
    config = _config_falso(tmp_path)
    backup_config(config)
    original = config.read_bytes()
    config.write_text("DEFAULT:\n  tmdb: 'CLAVE_REAL'\n", encoding="utf-8")
    _poner_ajuste("uploadrr.path", str(tmp_path / "Uploadrr"))

    assert ue.restaurar_config_interrumpida() is True
    assert config.read_bytes() == original
    assert ue.restaurar_config_interrumpida() is False


def test_la_siguiente_subida_restaura_el_config_aunque_no_pueda_stagear(tmp_path, monkeypatch):
    from emuwarez_uploadrr.services.upload_execution import config as ue
    config = _config_falso(tmp_path)
    backup_config(config)
    original = config.read_bytes()
    config.write_text("DEFAULT:\n  tmdb: 'CLAVE_REAL'\n", encoding="utf-8")
    monkeypatch.setattr(ue, "append_upload_log", lambda *a, **k: None)
    monkeypatch.setattr(ue, "_stage_uploadrr_config", lambda job_id, cwd: None)
    ue._config_stage_refcount.clear()

    assert ue._acquire_staged_config(1, str(tmp_path / "Uploadrr")) is None
    assert config.read_bytes() == original


# --- EJEC-5: una subida que se une a otra ya en curso relee Ajustes ------------

def test_una_subida_que_se_une_a_otra_recoge_los_ajustes_nuevos(tmp_path, monkeypatch):
    from emuwarez_uploadrr.services.upload_execution import config as ue
    config = _config_falso(tmp_path)
    original = config.read_bytes()
    monkeypatch.setattr(ue, "append_upload_log", lambda *a, **k: None)
    ue._config_stage_refcount.clear()
    cwd = str(tmp_path / "Uploadrr")

    primera = ue._acquire_staged_config(1, cwd)
    assert _per_episode(config) == "0"
    _poner_ajuste("emu.per_episode_screens", "true")  # Ajustes cambia con una subida en curso
    segunda = ue._acquire_staged_config(2, cwd)

    assert _per_episode(config) == "3"
    ue._release_staged_config(1, primera)
    assert _per_episode(config) == "3"  # sigue stageado para la segunda
    ue._release_staged_config(2, segunda)
    assert config.read_bytes() == original


def test_una_subida_que_se_une_no_reescribe_si_los_ajustes_no_cambiaron(tmp_path, monkeypatch):
    from emuwarez_uploadrr.services.upload_execution import config as ue
    _config_falso(tmp_path)
    monkeypatch.setattr(ue, "append_upload_log", lambda *a, **k: None)
    ue._config_stage_refcount.clear()
    escrituras = []
    real = ue.write_staged_config
    monkeypatch.setattr(ue, "write_staged_config", lambda *a, **k: escrituras.append(1) or real(*a, **k))
    cwd = str(tmp_path / "Uploadrr")

    primera = ue._acquire_staged_config(1, cwd)
    segunda = ue._acquire_staged_config(2, cwd)

    assert len(escrituras) == 1
    ue._release_staged_config(1, primera)
    ue._release_staged_config(2, segunda)


# --- La imagen trae config.yaml y config.yaml.bak como enlaces a /config -----------

def _config_con_enlaces(tmp_path):
    """Como la imagen: data/ con enlaces hacia otro directorio. El .bak empieza roto."""
    estado = tmp_path / "estado"
    estado.mkdir()
    (estado / "config.yaml").write_text("DEFAULT:\n  tmdb: ''\nSCREENS:\n  per_episode: 3\n", encoding="utf-8")
    data = tmp_path / "Uploadrr" / "data"
    data.mkdir(parents=True)
    (data / "config.yaml").symlink_to(estado / "config.yaml")
    (data / "config.yaml.bak").symlink_to(estado / "config.yaml.bak")
    return data / "config.yaml", estado


def test_preparar_y_restaurar_el_config_escribe_en_el_destino_del_enlace(tmp_path):
    """Sustituir el enlace con os.replace falla con EPERM para un usuario normal
    (directorio con sticky, enlace de root): se escribe en el fichero real."""
    config, estado = _config_con_enlaces(tmp_path)
    original = (estado / "config.yaml").read_bytes()

    write_staged_config(config, ["DEFAULT:", "  tmdb: 'CLAVE'"])

    assert config.is_symlink() and config.with_suffix(".yaml.bak").is_symlink()
    assert b"CLAVE" in (estado / "config.yaml").read_bytes()
    assert (estado / "config.yaml.bak").read_bytes() == original

    assert restore_config_from_backup(config) is True

    assert config.is_symlink()
    assert (estado / "config.yaml").read_bytes() == original
    assert sorted(p.name for p in estado.iterdir()) == ["config.yaml", "config.yaml.bak"]
    assert sorted(p.name for p in config.parent.iterdir()) == ["config.yaml", "config.yaml.bak"]


def test_restaurar_lo_que_dejo_una_subida_muerta_tambien_respeta_el_enlace(tmp_path):
    config, estado = _config_con_enlaces(tmp_path)
    backup_config(config)
    original = (estado / "config.yaml").read_bytes()
    (estado / "config.yaml").write_text("DEFAULT:\n  tmdb: 'CLAVE_REAL'\n", encoding="utf-8")

    from emuwarez_uploadrr.services.uploadrr_config_staging import restore_stale_config
    assert restore_stale_config(config) is True

    assert config.is_symlink()
    assert (estado / "config.yaml").read_bytes() == original


def test_si_no_se_puede_sustituir_el_config_no_queda_el_temporal(tmp_path, monkeypatch):
    import os
    config, estado = _config_con_enlaces(tmp_path)

    def sin_permiso(origen, destino):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "replace", sin_permiso)
    with pytest.raises(PermissionError):
        write_staged_config(config, ["DEFAULT:", "  tmdb: 'x'"])

    assert not any(p.name.endswith(".tmp") for p in estado.iterdir())


def test_escribir_el_config_conserva_su_modo_y_lo_crea_privado(tmp_path):
    """os.replace no conserva el modo: un config.yaml con 0600 acababa con el
    que dejara la umask, legible por otros usuarios del volumen."""
    import os
    config, estado = _config_con_enlaces(tmp_path)
    anterior = os.umask(0o022)
    try:
        (estado / "config.yaml").chmod(0o600)
        write_staged_config(config, ["DEFAULT:", "  tmdb: 'x'"])
        restore_config_from_backup(config)

        assert (estado / "config.yaml").stat().st_mode & 0o777 == 0o600
        assert (estado / "config.yaml.bak").stat().st_mode & 0o777 == 0o600  # nuevo: privado

        (estado / "config.yaml").chmod(0o640)
        write_staged_config(config, ["DEFAULT:", "  tmdb: 'y'"])
        assert (estado / "config.yaml").stat().st_mode & 0o777 == 0o640
    finally:
        os.umask(anterior)
