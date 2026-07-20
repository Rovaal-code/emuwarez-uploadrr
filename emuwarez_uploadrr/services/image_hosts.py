"""Image-host configuration for the screenshots Uploadrr uploads with the
torrent. imgbox is the always-available default (no API key). The user can
enable others (some need an API key) as an ordered fallback list; imgbox is
always tried last.

Config is stored in the app settings:
- imghost.enabled : JSON ordered list of host ids the user enabled.
- imghost.key.<id>: API key per host (only for needs_key hosts).

URLs mirror the endpoints Uploadrr-EMU's own image uploaders use.
"""
from __future__ import annotations

import json
import sqlite3
import urllib.request
from typing import Any, Optional

# id, label, homepage (for the reachability check), needs_key, favicon (the
# real <link rel="icon"> the site itself declares — resolved by hand once,
# 2026-07-20, since Google's s2 favicon proxy returns a wrong/generic icon
# for several of these low-traffic hosts instead of their real one).
IMAGE_HOSTS: list[dict[str, Any]] = [
    {"id": "imgbox",    "label": "Imgbox",     "url": "https://imgbox.com",    "needs_key": False, "favicon": "https://imgbox.com/images/favicon.ico"},
    {"id": "pixhost",   "label": "Pixhost",    "url": "https://pixhost.to",    "needs_key": False, "favicon": "https://pixhost.to/favicon.ico"},
    {"id": "fastpic",   "label": "FastPic",    "url": "https://fastpic.org",   "needs_key": False, "favicon": "https://fastpic.org/favicon-32x32.png"},
    {"id": "imgbb",     "label": "ImgBB",      "url": "https://imgbb.com",     "needs_key": True,  "favicon": "https://simgbb.com/images/favicon.png"},
    # ptpimg.me: currently returning a Cloudflare 523 (origin unreachable) —
    # couldn't resolve its real favicon; falls back to Google's s2 service.
    {"id": "ptpimg",    "label": "PTPIMG",     "url": "https://ptpimg.me",     "needs_key": True,  "favicon": None},
    # lensdump.com's own <link rel="icon"> points at a blank/broken CDN asset —
    # /favicon.ico at the root domain has the real camera-lens mark instead.
    {"id": "lensdump",  "label": "Lensdump",   "url": "https://lensdump.com",  "needs_key": True,  "favicon": "https://lensdump.com/favicon.ico"},
    {"id": "ptscreens", "label": "PTScreens",  "url": "https://ptscreens.com", "needs_key": True,  "favicon": "https://ptscreens.com/content/images/system/favicon_1725283834396_b75cb0.png"},
    {"id": "onlyimage", "label": "OnlyImage",  "url": "https://onlyimage.org", "needs_key": True,  "favicon": "https://onlyimage.org/content/images/system/favicon_1722402372098_802ccb.png"},
    # hamster.is no longer resolves at all (NXDOMAIN, confirmed against
    # Cloudflare's public resolver) — the domain looks dead. Left as-is
    # pending the real current URL; flagged to the user.
    {"id": "hamster",   "label": "Hamster",    "url": "https://hamster.is",    "needs_key": True,  "favicon": None},
    {"id": "imghost",   "label": "imghost.dev", "url": "https://imghost.dev",  "needs_key": True,  "favicon": "https://imghost.dev/content/images/system/default/favicon.png"},
]

_BY_ID = {h["id"]: h for h in IMAGE_HOSTS}
DEFAULT_HOST = "imgbox"


def host_meta(host_id: str) -> Optional[dict]:
    return _BY_ID.get(host_id)


def get_enabled_hosts(conn: sqlite3.Connection) -> list[str]:
    """The user's enabled hosts, in fallback order. Never raises."""
    from ..database import get_setting_canonical
    raw = get_setting_canonical(conn, "imghost.enabled")
    try:
        ids = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        ids = []
    return [i for i in ids if i in _BY_ID]


def get_host_key(conn: sqlite3.Connection, host_id: str) -> Optional[str]:
    from ..database import get_setting_canonical
    return get_setting_canonical(conn, f"imghost.key.{host_id}")


def fallback_order(conn: sqlite3.Connection) -> list[str]:
    """Hosts to try when uploading images: the enabled ones in order, then
    imgbox last as the no-key fallback (deduplicated)."""
    order = [h for h in get_enabled_hosts(conn) if h != DEFAULT_HOST]
    order.append(DEFAULT_HOST)
    return order


def set_config(conn: sqlite3.Connection, enabled: list[str], keys: Optional[dict[str, str]] = None) -> None:
    from ..web.services.settings_service import set_setting
    clean = [i for i in (enabled or []) if i in _BY_ID]
    set_setting(conn, "imghost.enabled", json.dumps(clean, ensure_ascii=False))
    for host_id, key in (keys or {}).items():
        if host_id in _BY_ID and key is not None and str(key).strip():
            set_setting(conn, f"imghost.key.{host_id}", str(key).strip())


def test_image_host(host_id: str, api_key: Optional[str] = None, *, timeout: int = 8) -> dict:
    """Reachability check for an image host (does the site respond?). For hosts
    that need a key, require the key to be present (we can't validate it without
    uploading an image). Never raises."""
    meta = _BY_ID.get(host_id)
    if not meta:
        return {"ok": False, "error": f"Host desconocido: {host_id}"}
    if meta["needs_key"] and not (api_key and api_key.strip()):
        return {"ok": False, "error": f"{meta['label']} necesita una API key"}
    try:
        req = urllib.request.Request(meta["url"], method="GET", headers={"User-Agent": "emuwarez-uploadrr/2"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 400:
                return {"ok": True}
            return {"ok": False, "error": f"HTTP {resp.status}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"No responde: {exc}"}
