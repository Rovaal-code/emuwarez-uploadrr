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


def _test_hardlink(path: str, hardlink_base: Optional[str]) -> tuple[bool, str]:
    target_dir = hardlink_base or os.path.dirname(path)
    if not target_dir or not os.path.isdir(target_dir):
        return False, f"El directorio de hardlinks no existe: {target_dir or '(sin ruta)'}"
    if not os.access(target_dir, os.W_OK):
        return False, f"Sin permiso de escritura en {target_dir}"
    link = os.path.join(target_dir, f".emuwarez_hltest_{os.getpid()}")
    try:
        if os.path.exists(link):
            os.remove(link)
        os.link(path, link)
        os.remove(link)
        return True, f"Se puede crear un hardlink en {target_dir}"
    except OSError as exc:
        try:
            os.remove(link)
        except OSError:
            pass
        return False, f"No se pudo crear el hardlink en {target_dir}: {exc}"


def probe_hardlink_dir(base_dir: Optional[str]) -> tuple[bool, str]:
    """Settings-time hardlink test: verify a directory can hold hardlinks by
    creating a temp file there and hardlinking it (same-filesystem + writable).
    Cleans up both files. Used by the 'Probar hardlink' button in Ajustes."""
    if not base_dir or not base_dir.strip():
        return False, "No has indicado ninguna ruta base para hardlinks"
    base = base_dir.strip()
    if not os.path.isdir(base):
        return False, f"El directorio no existe: {base}"
    if not os.access(base, os.W_OK):
        return False, f"Sin permiso de escritura en {base}"
    src = os.path.join(base, f".emuwarez_hlsrc_{os.getpid()}")
    link = os.path.join(base, f".emuwarez_hltest_{os.getpid()}")
    try:
        with open(src, "wb") as fh:
            fh.write(b"emuwarez hardlink test")
        os.link(src, link)
        ok = os.path.exists(link)
        return ok, (f"Hardlinks funcionan en {base}" if ok
                    else f"No se pudo crear el hardlink en {base}")
    except OSError as exc:
        return False, f"No se pudo crear el hardlink en {base}: {exc}"
    finally:
        for p in (link, src):
            try:
                os.remove(p)
            except OSError:
                pass


def probe_hardlink_for_library(base_dir: Optional[str], conn) -> tuple[bool, str]:
    """Settings-time gate for ENABLING hardlinks: the base must support hardlinks
    (probe_hardlink_dir) AND live on the same filesystem as the media, because a
    hardlink can't cross filesystems. Samples a real library file and compares
    st_dev — catches the common case of media on an SSHFS/NFS mount with a
    hardlink_base on the local disk."""
    ok, msg = probe_hardlink_dir(base_dir)
    if not ok or not base_dir:
        return ok, msg
    try:
        from .path_mapping import resolve_local_path
        row = conn.execute(
            "SELECT path FROM library_items WHERE path IS NOT NULL AND path <> '' "
            "AND local_status = 'Disponible' AND item_type IN ('movie', 'episode') LIMIT 1"
        ).fetchone()
        raw = row["path"] if row else None
        if raw:
            media_local = resolve_local_path(raw, conn=conn) or raw
            media_dir = os.path.dirname(media_local)
            if os.path.isdir(media_dir):
                if os.stat(base_dir.strip()).st_dev != os.stat(media_dir).st_dev:
                    return False, (
                        "La ruta de hardlinks está en un sistema de ficheros distinto al de tu "
                        f"biblioteca ({media_dir}). Los hardlinks no pueden cruzar sistemas de "
                        "ficheros: elige una carpeta dentro de la misma unidad que tu media, o "
                        "desactiva los hardlinks (se renombrará el archivo original)."
                    )
    except Exception:
        # Best-effort: if we can't sample the media, fall back to the base probe.
        pass
    return True, msg


def run_upload_checks(conn: sqlite3.Connection, item_id: int) -> dict:
    from .library import get_library_item
    from .integration_tests import test_qbit_connection, test_emuwarez_connection
    from .image_hosts import fallback_order, get_host_key, test_image_host, host_meta
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
        # generic single-file "renameable"/"hardlink" checks below don't
        # apply. build_season_pack_plan() already covers everything relevant
        # here in one pass — completeness, per-episode consistency, and
        # whether a shared pack folder is achievable (hardlink into a new
        # folder, or rename in place when hardlinks are off and episodes
        # already share one folder) — so it's reused as the single season
        # check instead of re-deriving pieces of it.
        from .season_pack import build_season_pack_plan
        plan = build_season_pack_plan(item_id, conn=conn)
        ok = plan["status"] == "valid"
        msg = "; ".join(plan["errors"]) if not ok else (
            f"Pack listo: {len(plan['episodes'])} episodio(s) → {plan.get('hardlink_folder')}"
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

        # 2. Hardlink — only when hardlinks are configured; otherwise skipped (yellow).
        use_hardlinks = (get_setting_canonical(conn, "nomenclature.use_hardlinks") or "true") != "false"
        hl_base = get_setting_canonical(conn, "hardlink_base")
        if not use_hardlinks:
            add_skip("hardlink", "Hardlinks desactivados (se omite)", "Actívalos en Ajustes si quieres usarlos")
        elif not (hl_base and hl_base.strip()):
            add_skip("hardlink", "Hardlinks sin configurar (se omite)", "Configura la ruta base en Ajustes")
        else:
            ok, msg = _test_hardlink(local_path, hl_base)
            if not add("hardlink", "Se puede crear el hardlink", "No se puede crear el hardlink", ok, msg):
                return done()

    # 3. Output directory writable — where Uploadrr stages the .torrent + images.
    out_dir = get_setting_canonical(conn, "uploadrr.path")
    if not add("output", "Directorio de salida escribible", "Directorio de salida no escribible",
               bool(out_dir) and os.path.isdir(out_dir) and os.access(out_dir, os.W_OK),
               out_dir or "uploadrr.path no configurado"):
        return done()

    # 4. qBittorrent — WebUI login; skipped (yellow) when it isn't configured.
    qbit_url = get_setting_canonical(conn, "qbit.url")
    if not (qbit_url and qbit_url.strip()):
        add_skip("qbittorrent", "qBittorrent sin configurar (se omite)",
                 "Configúralo en Ajustes para sembrar automáticamente tras subir")
    else:
        r = test_qbit_connection(conn=conn)
        if not add("qbittorrent", "qBittorrent conectado", "qBittorrent no conectado",
                   bool(r.get("ok")), r.get("message", "")):
            return done()

    # 5. Image hosts — at least one reachable (imgbox tried last).
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

    # 6. eMuwarez — last, so we don't hit it unless everything else passed.
    r = test_emuwarez_connection(conn=conn)
    add("emuwarez", "eMuwarez disponible", "eMuwarez no disponible", bool(r.get("ok")), r.get("message", ""))
    return done()
