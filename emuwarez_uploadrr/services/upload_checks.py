"""Pre-upload checks for the "Subida a eMuwarez" step.

Runs a sequence of checks and STOPS at the first failure (fail-fast) so the
network services — especially eMuwarez, which goes last — are never hit until
everything local passes. Returns each check's result for a styled checklist,
plus a `ready` flag that's only true when every check passed.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Optional

# Live progress of a running checks call, so the UI can reveal each check as
# it completes (some — qBittorrent, image hosts, eMuwarez — are real network
# calls; the whole sequence has been observed taking ~30s) instead of showing
# nothing until the whole POST resolves. Keyed by item_id: only one checks run
# per item makes sense at a time. Single-process app → an in-memory dict is
# enough, same pattern as services/library.py's sync progress.
_CHECKS_LOCK = threading.Lock()
_CHECKS_PROGRESS: dict[int, dict] = {}


def get_checks_progress(item_id: int) -> dict:
    with _CHECKS_LOCK:
        return dict(_CHECKS_PROGRESS.get(item_id, {"checks": [], "done": False, "ready": False}))


def _set_checks_progress(item_id: int, *, checks: list[dict], done: bool = False, ready: bool = False) -> None:
    with _CHECKS_LOCK:
        _CHECKS_PROGRESS[item_id] = {"checks": list(checks), "done": done, "ready": ready}


def run_upload_checks(conn: sqlite3.Connection, item_id: int) -> dict:
    from .library import get_library_item
    from .integration_tests import test_qbit_connection, test_emuwarez_connection
    from .image_hosts import fallback_order, get_host_key, test_image_host, host_meta
    from .uploadrr_contract import get_runtime_settings
    from ..database import get_setting_canonical

    checks: list[dict] = []
    _set_checks_progress(item_id, checks=[])  # reset — a previous run's leftovers shouldn't leak in

    # The label states the outcome: the positive phrase when the check passes,
    # the negative one when it fails (e.g. "Contenido accesible" / "Contenido no
    # accesible"). Published to _CHECKS_PROGRESS immediately after each one, so
    # a concurrent poller sees checks land one at a time as they actually
    # complete (some — qBittorrent/image hosts/eMuwarez — are real network
    # calls, not instant).
    def add(cid: str, ok_label: str, fail_label: str, ok: bool, message: str = "") -> bool:
        checks.append({"id": cid, "label": ok_label if ok else fail_label,
                       "status": "ok" if ok else "fail", "message": message})
        _set_checks_progress(item_id, checks=checks)
        return ok

    # A skipped check (yellow): an optional integration that isn't configured, so
    # it's not blocking — the upload can still go ahead.
    def add_skip(cid: str, label: str, message: str = "") -> None:
        checks.append({"id": cid, "label": label, "status": "skip", "message": message})
        _set_checks_progress(item_id, checks=checks)

    def done() -> dict:
        # Skips don't block: only a real failure (red) does.
        ready = bool(checks) and all(c["status"] in ("ok", "skip") for c in checks) and checks[-1]["id"] == "emuwarez"
        _set_checks_progress(item_id, checks=checks, done=True, ready=ready)
        return {"checks": checks, "ready": ready}

    item = get_library_item(conn, item_id)
    if not item:
        add("renameable", "Se puede renombrar", "No se puede renombrar", False, "Elemento no encontrado")
        return done()

    # Accessibility and integrity (MediaInfo/mkvtoolnix can read the file) are
    # NOT checked here anymore — they're checked for real once the upload is
    # actually queued, as the first stage of the server-side preparation
    # (services/upload_queue.py), which already runs MediaInfo/mkvmerge on
    # each real file for the nomenclature/remux steps. Checking twice would
    # just duplicate that work; a failure there fails the job with a specific
    # reason ("no accesible" / "MediaInfo no pudo leer" / "mkvtoolnix no pudo
    # leer") instead of blocking the wizard's checklist pre-emptively.

    if item.get("item_type") == "season":
        # A season has no `path` of its own — only its episodes do — so the
        # generic single-file "renameable" check below doesn't
        # apply. build_season_pack_plan() already covers everything relevant
        # here in one pass — completeness, per-episode consistency, and
        # whether a shared pack folder is achievable (every available episode
        # must already live in the same folder) — so it's reused as the
        # single season check instead of re-deriving pieces of it.
        from .season_pack import build_season_pack_plan
        plan = build_season_pack_plan(item_id, conn=conn)
        ok = plan["status"] == "valid"
        msg = "; ".join(plan["errors"]) if not ok else (
            f"Pack listo: {len(plan['episodes'])} episodio(s) → {plan.get('pack_folder')}"
        )
        if not add("season_pack", "Se puede preparar el pack de temporada",
                   "No se puede preparar el pack de temporada", ok, msg):
            return done()
        # Falls through to the shared checks below (output dir/qBittorrent/
        # image hosts/eMuwarez) — those don't depend on item_type.
    else:
        path = item.get("path")
        # Translate the Radarr/Sonarr path to where the file is actually
        # reachable (remote path mapping) — same as MediaInfo. Otherwise a
        # remote-mounted library reads fine but the filesystem checks fail on
        # the raw /data path.
        from .path_mapping import resolve_local_path
        local_path = resolve_local_path(path) or path

        # 1. Renameable — write permission on the file's directory.
        parent = os.path.dirname(local_path) if local_path else ""
        if not add("renameable", "Se puede renombrar", "No se puede renombrar",
                   bool(parent) and os.access(parent, os.W_OK),
                   parent or (path or "El elemento no tiene ruta de archivo")):
            return done()

        # 1b. Castilian — eMuwarez wants it present, dubbed or at least
        # subtitled. The audio alone is enough: a film in Castilian needs no
        # subtitles. Without Castilian audio, Castilian subtitles are what
        # makes it acceptable. Same rule a season pack applies per episode
        # (services/season_pack.py::_spanish_errors), which is why it reuses
        # the same predicate.
        #
        # Unknown blocks: an item whose MediaInfo was never read can't be
        # confirmed either way, and "we didn't look" is not evidence that the
        # rule is met.
        from .emu_format import has_castellano
        audio_langs = item.get("audio_languages")
        sub_langs = item.get("subtitle_languages")
        has_audio_es = has_castellano(audio_langs) == 1
        has_subs_es = has_castellano(sub_langs) == 1
        if has_audio_es:
            spanish_msg = "Audio en castellano. No son obligatorios subtítulos en castellano."
        elif has_subs_es:
            spanish_msg = f"Sin audio en castellano ({audio_langs or 'desconocido'}), pero subtítulos sí ({sub_langs})."
        else:
            spanish_msg = (
                f"Ni el audio ({audio_langs or 'sin detectar'}) ni los subtítulos "
                f"({sub_langs or 'sin detectar'}) están en castellano."
            )
        if not add("spanish", "Tiene castellano", "No tiene castellano",
                   has_audio_es or has_subs_es, spanish_msg):
            return done()

    # 2. Output directory writable — where Uploadrr-EMU stages the .torrent +
    # images (torrents/screenshots/descriptions) is <uploadrr_path>/tmp, NOT
    # the top-level uploadrr_path itself: in the documented Docker deployment
    # (docker-compose.yml) the code root is mounted :ro on purpose and only
    # its data/ and tmp/ subdirs are mounted rw. Checking the top-level path
    # here always failed under that exact, recommended setup. Falls back to
    # the bundled runtime's own default (/opt/Uploadrr, or UPLOADRR_PATH) the
    # same way uploadrr_contract.py::get_runtime_settings already does — the
    # bundled runtime needs no configuration at all, so this check must not
    # require `uploadrr.path` to have been set by hand.
    base_dir = get_runtime_settings(conn)["uploadrr_path"]
    out_dir = os.path.join(base_dir, "tmp") if base_dir else None
    if not add("output", "Directorio de salida escribible", "Directorio de salida no escribible",
               bool(out_dir) and os.path.isdir(out_dir) and os.access(out_dir, os.W_OK),
               out_dir or "uploadrr.path no configurado"):
        return done()

    # 3. qBittorrent — WebUI login; skipped (yellow) when it isn't configured.
    qbit_url = get_setting_canonical(conn, "qbit.url")
    if not (qbit_url and qbit_url.strip()):
        add_skip("qbittorrent", "qBittorrent sin configurar (se omite)",
                 "Configúralo en Ajustes para sembrar automáticamente tras subir")
    else:
        r = test_qbit_connection(conn=conn)
        if not add("qbittorrent", "qBittorrent conectado", "qBittorrent no conectado",
                   bool(r.get("ok")), r.get("message", "")):
            return done()

    # 4. Image hosts — at least one reachable (imgbox tried last).
    reachable = None
    for host in fallback_order(conn):
        if test_image_host(host, get_host_key(conn, host)).get("ok"):
            reachable = host
            break
    label = host_meta(reachable)["label"] if reachable else None
    if not add("imghosts", "Repo de imágenes disponible", "Repo de imágenes no disponible",
               reachable is not None,
               f"Responde: {label}" if reachable else "Ningún host de imágenes responde"):
        return done()

    # 5. eMuwarez — last, so we don't hit it unless everything else passed.
    # enforce_rate_limit=False: the 1/minute throttle exists to stop someone
    # mashing Configuración's "Probar conexión" button, not to block this
    # automated per-upload precondition — without it, two uploads (manual or
    # automático) queued within the same minute would always make the second
    # one's "eMuwarez disponible" check fail with "Espera Ns…" even though
    # eMuwarez itself was never actually asked twice in a way it would mind.
    r = test_emuwarez_connection(conn=conn, enforce_rate_limit=False)
    add("emuwarez", "eMuwarez disponible", "eMuwarez no disponible", bool(r.get("ok")), r.get("message", ""))
    return done()
