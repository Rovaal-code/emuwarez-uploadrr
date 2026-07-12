"""Pre-upload checks for the "Subida a eMuwarez" step.

Runs a sequence of checks and STOPS at the first failure (fail-fast) so the
network services — especially eMuwarez, which goes last — are never hit until
everything local passes. Returns each check's result for a styled checklist,
plus a `ready` flag that's only true when every check passed.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Optional


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


def run_upload_checks(conn: sqlite3.Connection, item_id: int) -> dict:
    from .library import get_library_item
    from .media_info_service import mediainfo_available, read_media_info_summary
    from .integration_tests import test_qbit_connection, test_emuwarez_connection
    from .image_hosts import fallback_order, get_host_key, test_image_host, host_meta
    from ..database import get_setting_canonical

    checks: list[dict] = []

    # The label states the outcome: the positive phrase when the check passes,
    # the negative one when it fails (e.g. "Contenido accesible" / "Contenido no
    # accesible").
    def add(cid: str, ok_label: str, fail_label: str, ok: bool, message: str = "") -> bool:
        checks.append({"id": cid, "label": ok_label if ok else fail_label,
                       "status": "ok" if ok else "fail", "message": message})
        return ok

    def done() -> dict:
        ready = bool(checks) and all(c["status"] == "ok" for c in checks) and checks[-1]["id"] == "emuwarez"
        return {"checks": checks, "ready": ready}

    item = get_library_item(conn, item_id)
    if not item:
        add("accessible", "Contenido accesible", "Contenido no accesible", False, "Elemento no encontrado")
        return done()
    path = item.get("path")

    # 1. Accessible — the file exists on disk.
    if not add("accessible", "Contenido accesible", "Contenido no accesible",
               bool(path) and os.path.isfile(path),
               path or "El elemento no tiene ruta de archivo"):
        return done()

    # 2. Renameable — write permission on the file's directory.
    parent = os.path.dirname(path)
    if not add("renameable", "Se puede renombrar", "No se puede renombrar",
               os.access(parent, os.W_OK), parent):
        return done()

    # 3. Integrity — non-empty and MediaInfo can read it (light corruption check).
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    if size == 0:
        add("integrity", "Fichero íntegro", "Fichero no íntegro", False, "El fichero está vacío (0 bytes)")
        return done()
    if mediainfo_available():
        info = read_media_info_summary(path)
        if not add("integrity", "Fichero íntegro", "Fichero no íntegro", bool(info),
                   "MediaInfo lo lee correctamente" if info else "MediaInfo no pudo leer el fichero (posible corrupción)"):
            return done()
    else:
        add("integrity", "Fichero íntegro", "Fichero no íntegro", True, "mediainfo no disponible: no verificado")

    # 4. Hardlink — only when hardlinks are enabled.
    use_hardlinks = (get_setting_canonical(conn, "nomenclature.use_hardlinks") or "true") != "false"
    if use_hardlinks:
        hl_base = get_setting_canonical(conn, "hardlink_base")
        ok, msg = _test_hardlink(path, hl_base)
        if not add("hardlink", "Se puede crear el hardlink", "No se puede crear el hardlink", ok, msg):
            return done()

    # 5. Output directory writable — where Uploadrr stages the .torrent + images.
    out_dir = get_setting_canonical(conn, "uploadrr.path")
    if not add("output", "Directorio de salida escribible", "Directorio de salida no escribible",
               bool(out_dir) and os.path.isdir(out_dir) and os.access(out_dir, os.W_OK),
               out_dir or "uploadrr.path no configurado"):
        return done()

    # 6. qBittorrent — WebUI login.
    r = test_qbit_connection(conn=conn)
    if not add("qbittorrent", "qBittorrent conectado", "qBittorrent no conectado",
               bool(r.get("ok")), r.get("message", "")):
        return done()

    # 7. Image hosts — at least one reachable (imgbox tried last).
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

    # 8. eMuwarez — last, so we don't hit it unless everything else passed.
    r = test_emuwarez_connection(conn=conn)
    add("emuwarez", "eMuwarez disponible", "eMuwarez no disponible", bool(r.get("ok")), r.get("message", ""))
    return done()
