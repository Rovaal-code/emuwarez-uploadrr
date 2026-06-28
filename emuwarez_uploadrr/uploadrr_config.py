"""Line-based editor for Uploadrr/data/config.yaml."""
from .legacy import (
    read_yaml_lines, write_yaml_lines, find_top_block, get_block_key, set_block_key,
    yaml_scalar, python_literal_scalar, render_inline_mapping, find_child_block,
    set_child_inline_mapping, get_emu_api_key, get_emu_anon, set_emu_api_key,
    set_emu_config, get_torrent_client, get_watch_folder, set_watch_folder,
    set_qbit_config, tmdb_api_key, emu_api_key, get_screen_api_key,
    set_screen_api_key, get_screen_api_keys, set_screen_api_keys,
    get_imgbb_api_key, set_imgbb_api_key, imgbb_api_key, get_img_hosts,
    build_img_hosts_order, set_img_hosts, uploadrr_config_backup,
    ensure_config_backup_exists, restore_uploadrr_config_from_backup,
    inject_app_config_into_uploadrr, register_config_restore_handlers,
)
