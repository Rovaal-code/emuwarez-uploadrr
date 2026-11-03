"""Preparación y restauración del config.yaml de Uploadrr-EMU, compartido entre subidas en paralelo."""
from __future__ import annotations

import threading
from pathlib import Path

from ...database import get_setting_canonical
from ..settings import leer_ajuste
from ..image_hosts import fallback_order, get_host_key
from ..uploadrr_config_staging import (
    SCREENS_API_KEY_HOSTS,
    backup_config,
    default_uploadrr_config_path,
    read_baseline_lines,
    restore_config_from_backup,
    restore_stale_config,
    stage_add_logo,
    stage_blu_api_off,
    stage_emu_config,
    stage_image_hosts,
    stage_per_episode_screens,
    stage_qbittorrent_config,
    stage_tmdb_key,
    staged_config_text,
    write_staged_config,
)
from ..uploadrr_contract import get_runtime_settings
from .comun import _get_db_conn, logger
from .registro import append_upload_log


class ConfigNoPreparada(RuntimeError):
    """El config.yaml de Uploadrr no se pudo preparar: lanzarlo así lo haría fallar con las claves sin poner."""


def _stage_uploadrr_config(job_id: int, cwd: str) -> Path | None:
    """Staging of DEFAULT.tmdb / TRACKERS.EMU.api_key into config.yaml.

    Returns the config_path if staging happened (so the caller knows to
    restore it later), or None if there was nothing to stage (config.yaml
    missing, or no secrets configured) — in that case there is nothing to
    restore either. Si preparar el config falla lanza ConfigNoPreparada: el
    job termina fallido sin lanzar Uploadrr.
    """
    config_path = default_uploadrr_config_path(cwd)
    if not config_path.exists():
        append_upload_log(
            job_id, "warning",
            f"config.yaml no encontrado en {config_path}; no se stagean credenciales.",
            stream="system",
        )
        return None

    conn = _get_db_conn()
    try:
        tmdb_key = get_setting_canonical(conn, "tmdb.api_key")
        emu_key = get_setting_canonical(conn, "emu.api_key")
        img_hosts = fallback_order(conn)
        img_api_keys = {
            host_id: key for host_id in SCREENS_API_KEY_HOSTS
            if (key := get_host_key(conn, host_id))
        }
        qbit_url = get_setting_canonical(conn, "qbit.url")
        qbit_tag = get_setting_canonical(conn, "qbit.tag")
        # El logo va en la descripción salvo que se haya apagado a mano.
        add_logo = leer_ajuste(conn, "emu_add_logo")
        # Las capturas de un pack, solo del primer capítulo salvo que se pidan todas.
        per_episode_screens = leer_ajuste(conn, "emu_per_episode_screens")
        qbit_username = get_setting_canonical(conn, "qbit.username")
        qbit_password = get_setting_canonical(conn, "qbit.password")
        qbit_qui = get_setting_canonical(conn, "qbit.qui_proxy_url")
    finally:
        conn.close()

    try:
        # Del config de verdad (.bak), no del config.yaml de ahora: puede ser el
        # que dejó stageado una subida que murió, o el de otra que sigue en curso.
        lines = read_baseline_lines(config_path)
        changed = False
        if tmdb_key:
            lines, _msg = stage_tmdb_key(lines, tmdb_key)
            changed = True
        if emu_key:
            lines, _msg = stage_emu_config(lines, api_key=emu_key)
            changed = True
        lines, _msg = stage_add_logo(lines, add_logo)
        lines, _msg = stage_per_episode_screens(lines, per_episode_screens)
        lines, _msg = stage_blu_api_off(lines)
        changed = True
        if img_hosts:
            # Always staged (imgbox is always in fallback_order()'s result,
            # even with nothing else enabled) — this is what makes the
            # configured preference (e.g. Pixhost) actually reach Uploadrr-EMU
            # instead of it silently defaulting to its own img_hosts order.
            lines, _msg = stage_image_hosts(lines, img_hosts=img_hosts, api_keys=img_api_keys)
            changed = True
        if (qbit_url and qbit_username and qbit_password) or qbit_qui:
            # Without this, Uploadrr-EMU falls back to whatever
            # DEFAULT.default_torrent_client its own config.yaml ships with
            # (confirmed: "watch", not "qbit") — the job finishes
            # "successfully" but silently never touches qBittorrent's API.
            lines, _msg = stage_qbittorrent_config(
                lines, url=qbit_url or "", username=qbit_username or "", password=qbit_password or "", tag=qbit_tag,
                base_dir=cwd, qui_proxy_url=qbit_qui,
            )
            changed = True
        if not changed:
            append_upload_log(
                job_id, "warning",
                "Sin tmdb.api_key/emu.api_key configuradas; config.yaml no se modifica.",
                stream="system",
            )
            return None
        backup_config(config_path)
        if config_path.read_text(encoding="utf-8", errors="ignore") == staged_config_text(lines):
            return config_path  # ya está así: no se reescribe bajo una subida en curso
        write_staged_config(config_path, lines)
        append_upload_log(
            job_id, "info",
            "config.yaml stageado (DEFAULT.tmdb / TRACKERS.EMU.api_key / SCREENS.img_hosts / TORRENT_CLIENTS.qbit). Backup creado.",
            stream="system",
        )
        return config_path
    except Exception as exc:
        raise ConfigNoPreparada(
            f"No se pudo preparar el config.yaml de Uploadrr ({exc}). No se lanza la subida: con el config sin preparar fallaría."
        ) from exc


def _restore_uploadrr_config(job_id: int, config_path: Path | None) -> None:
    if config_path is None:
        return
    try:
        restored = restore_config_from_backup(config_path)
        if restored:
            append_upload_log(job_id, "info", "config.yaml restaurado desde backup.", stream="system")
        else:
            append_upload_log(job_id, "warning", "No había backup de config.yaml que restaurar.", stream="system")
    except Exception as exc:
        append_upload_log(job_id, "error", f"Fallo al restaurar config.yaml: {exc}", stream="system")


# The staged config.yaml (TMDb/EMU keys) is a SHARED resource: every job stages
# the exact same secrets from settings. To let uploads run in PARALLEL without
# clobbering each other's config (or restoring it out from under a still-running
# job), we reference-count it: the first concurrent job stages it, the last one
# to finish restores it. All overlapping jobs read the same correct config.
_config_stage_lock = threading.Lock()
_config_stage_refcount: dict[str, int] = {}


def _acquire_staged_config(job_id: int, cwd: str) -> Path | None:
    """Stage the config for this job, sharing a single staged file across
    concurrent uploads. Returns the config_path to release later, or None if
    nothing was staged."""
    config_path = default_uploadrr_config_path(cwd)
    key = str(config_path)
    with _config_stage_lock:
        if _config_stage_refcount.get(key, 0) > 0:
            # Ya lo stageó otra subida en curso. Se vuelve a calcular por si Ajustes
            # cambió desde entonces: solo reescribe si el resultado es otro.
            _stage_uploadrr_config(job_id, cwd)
            append_upload_log(job_id, "info", "config.yaml ya stageado por otra subida en curso; se reutiliza.", stream="system")
            _config_stage_refcount[key] += 1
            return config_path
        # Sin subidas en curso config.yaml debería ser el .bak: si no, es el
        # stageado de una que murió a medias.
        try:
            if restore_stale_config(config_path):
                append_upload_log(
                    job_id, "warning",
                    "config.yaml seguía stageado por una subida interrumpida; restaurado desde el backup.",
                    stream="system",
                )
        except OSError as exc:
            logger.warning("No se pudo restaurar el config.yaml interrumpido (%s): %s", config_path, exc)
        staged = _stage_uploadrr_config(job_id, cwd)
        if staged is None:
            return None
        _config_stage_refcount[key] = 1
        return staged


def restaurar_config_interrumpida() -> bool:
    """Al arrancar no hay ninguna subida viva: si config.yaml sigue stageado es
    el de una que murió sin restaurarlo, con las claves reales dentro."""
    conn = _get_db_conn()
    try:
        uploadrr_path = get_runtime_settings(conn)["uploadrr_path"]
    finally:
        conn.close()
    return bool(uploadrr_path) and restore_stale_config(default_uploadrr_config_path(uploadrr_path))


def _release_staged_config(job_id: int, config_path: Path | None) -> None:
    """Drop this job's reference; restore the config only when the last
    concurrent upload finishes."""
    if config_path is None:
        return
    key = str(config_path)
    with _config_stage_lock:
        n = _config_stage_refcount.get(key, 0)
        if n <= 1:
            _config_stage_refcount.pop(key, None)
            _restore_uploadrr_config(job_id, config_path)
        else:
            _config_stage_refcount[key] = n - 1
            append_upload_log(job_id, "info", "config.yaml sigue en uso por otra subida; no se restaura todavía.", stream="system")
