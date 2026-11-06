"""Image-host configuration for the screenshots Uploadrr uploads with the
torrent. The user picks the hosts (some need an API key) as an ordered
fallback list. On a fresh install the list is just Pixhost (no API key);
after that it is exactly what the user saved: any host can be removed or
replaced, Pixhost included, and none is tried behind the user's back.
(Imgbox used to be the forced last fallback; it has been down for months.)

Config is stored in the app settings:
- imghost.enabled : JSON ordered list of host ids the user enabled.
- imghost.key.<id>: API key per host (only for needs_key hosts).

URLs mirror the endpoints Uploadrr-EMU's own image uploaders use.
"""
from __future__ import annotations

import json
import sqlite3
import urllib.parse
from typing import Any, Optional

from ..integrations import http_cliente
from ..integrations.base import texto_de_error

# id, label, homepage (for the reachability check), needs_key, favicon (the
# real <link rel="icon"> the site itself declares — resolved by hand once,
# 2026-07-20, since Google's s2 favicon proxy returns a wrong/generic icon
# for several of these low-traffic hosts instead of their real one).
IMAGE_HOSTS: list[dict[str, Any]] = [
    {"id": "imgbox",    "label": "Imgbox",     "url": "https://imgbox.com",    "needs_key": False, "favicon": "https://imgbox.com/images/favicon.ico"},
    # pixhost.to stopped resolving (NXDOMAIN, confirmed 2026-07-26) — pixhost.cc
    # is the live domain now.
    {"id": "pixhost",   "label": "Pixhost",    "url": "https://pixhost.cc",    "needs_key": False, "favicon": "https://pixhost.cc/favicon.ico"},
    {"id": "fastpic",   "label": "FastPic",    "url": "https://fastpic.org",   "needs_key": False, "favicon": "https://fastpic.org/favicon-32x32.png"},
    {"id": "imgbb",     "label": "ImgBB",      "url": "https://imgbb.com",     "needs_key": True,  "favicon": "https://simgbb.com/images/favicon.png"},
    # lensdump.com's own <link rel="icon"> points at a blank/broken CDN asset —
    # /favicon.ico at the root domain has the real camera-lens mark instead.
    {"id": "lensdump",  "label": "Lensdump",   "url": "https://lensdump.com",  "needs_key": True,  "favicon": "https://lensdump.com/favicon.ico"},
    {"id": "ptscreens", "label": "PTScreens",  "url": "https://ptscreens.com", "needs_key": True,  "favicon": "https://ptscreens.com/content/images/system/favicon_1725283834396_b75cb0.png"},
    {"id": "onlyimage", "label": "OnlyImage",  "url": "https://onlyimage.org", "needs_key": True,  "favicon": "https://onlyimage.org/content/images/system/favicon_1722402372098_802ccb.png"},
    {"id": "imghost",   "label": "imghost.dev", "url": "https://imghost.dev",  "needs_key": True,  "favicon": "https://imghost.dev/content/images/system/default/favicon.png"},
]

# Retirados: hamster.is dejó de resolver (NXDOMAIN) y ptpimg.me pasó a solo
# lectura, sin aceptar subidas nuevas. Un proveedor que no puede recibir una
# captura no pinta nada en la lista: solo sirve para que alguien lo ponga el
# primero y se le rompan las subidas.
#
# Sus ajustes guardados (imghost.enabled, imghost.key.<id>) se quedan en la
# base pero son inertes: get_enabled_hosts y set_config filtran por _BY_ID,
# así que un id que ya no existe se cae solo.
_BY_ID = {h["id"]: h for h in IMAGE_HOSTS}
# La lista de una instalación nueva, hasta que el usuario guarde la suya.
DEFAULT_HOST = "pixhost"
DEFAULT_ENABLED: tuple[str, ...] = (DEFAULT_HOST,)


def host_meta(host_id: str) -> Optional[dict]:
    return _BY_ID.get(host_id)


def get_enabled_hosts(conn: sqlite3.Connection) -> list[str]:
    """The user's enabled hosts, in fallback order. Never raises.

    Sin ajuste guardado (instalación nueva): DEFAULT_ENABLED. Una lista guardada vacía se respeta: el usuario las
    quitó todas."""
    from ..database import get_setting_canonical
    raw = get_setting_canonical(conn, "imghost.enabled")
    if raw is None:
        return list(DEFAULT_ENABLED)
    try:
        ids = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        ids = []
    return [i for i in ids if i in _BY_ID]


def get_host_key(conn: sqlite3.Connection, host_id: str) -> Optional[str]:
    from ..database import get_setting_canonical
    return get_setting_canonical(conn, f"imghost.key.{host_id}")


def fallback_order(conn: sqlite3.Connection) -> list[str]:
    """Hosts to try when uploading images: the enabled ones, in order and
    deduplicated. Empty if the user removed them all (the pre-upload check
    then says so instead of uploading without screenshots)."""
    return list(dict.fromkeys(get_enabled_hosts(conn)))


def set_config(conn: sqlite3.Connection, enabled: list[str], keys: Optional[dict[str, str]] = None) -> None:
    from .settings import set_setting
    clean = [i for i in (enabled or []) if i in _BY_ID]
    set_setting(conn, "imghost.enabled", json.dumps(clean, ensure_ascii=False))
    for host_id, key in (keys or {}).items():
        if host_id in _BY_ID and key is not None and str(key).strip():
            set_setting(conn, f"imghost.key.{host_id}", str(key).strip())


# Endpoint de subida de cada proveedor con clave, y cómo viaja la clave.
# Los cinco son Chevereto (imgbb incluido, que corre sobre él), y los cinco
# COMPRUEBAN LA CLAVE ANTES QUE LA IMAGEN. Eso permite validarla de verdad sin
# subir nada: se manda la petición sin imagen y se mira si se queja de la clave.
#
#   clave mala  -> {"error": {"message": "Invalid API key.", "code": 100}}
#   clave buena -> se queja de que falta la imagen, con otro código
#
# Comprobado contra las APIs reales el 2026-08-01. imgbb autentica por el
# parámetro ?key= (su API v1 no lee ninguna cabecera, ver el arreglo del fork
# en Uploadrr-EMU 5b5bd47); el resto por la cabecera X-API-Key de Chevereto.
_KEY_CHECK: dict[str, dict[str, str]] = {
    "imgbb":     {"url": "https://api.imgbb.com/1/upload", "auth": "query"},
    "lensdump":  {"url": "https://lensdump.com/api/1/upload", "auth": "header"},
    "ptscreens": {"url": "https://ptscreens.com/api/1/upload", "auth": "header"},
    "onlyimage": {"url": "https://onlyimage.org/api/1/upload", "auth": "header"},
    "imghost":   {"url": "https://imghost.dev/api/1/upload", "auth": "header"},
}

# El código que Chevereto devuelve para "esta clave no vale".
_INVALID_KEY_CODE = 100


def validate_image_host_key(host_id: str, api_key: str, *, timeout: int = 10) -> dict:
    """¿Es válida esta API key? {"ok": bool, "error": str|None, "checked": bool}.

    `checked=False` significa "no se ha podido comprobar" (proveedor sin
    endpoint conocido, o la red falló). NO se traduce a "clave mala": no poder
    preguntar no es lo mismo que una respuesta negativa, y tratarlo igual haría
    que un corte de red te marcara en rojo una clave perfectamente buena.

    No sube ninguna imagen: la petición va sin ella a propósito, porque estos
    proveedores validan la clave antes de mirar el fichero.
    """
    check = _KEY_CHECK.get(host_id)
    if not check or not (api_key or "").strip():
        return {"ok": False, "error": None, "checked": False}

    url = check["url"]
    headers = {"User-Agent": "emuwarez-uploadrr/2"}
    if check["auth"] == "query":
        url = f"{url}?key={urllib.parse.quote(api_key.strip(), safe='')}"
    else:
        headers["X-API-Key"] = api_key.strip()

    try:
        resp = http_cliente.pedir("POST", url, cabeceras=headers, contenido=b"", timeout=timeout, limite=4096)
        body = http_cliente.texto(resp.content, 4096)
        status = resp.status_code
    except http_cliente.ErrorHTTP as exc:          # 400 es lo NORMAL aquí
        body = exc.texto(4096)
        status = exc.status
    except Exception as exc:                        # noqa: BLE001 — red, DNS, timeout
        return {"ok": False, "error": f"No se pudo comprobar: {texto_de_error(exc, api_key)}", "checked": False}

    try:
        data = json.loads(body)
    except ValueError:
        return {"ok": False, "error": f"Respuesta inesperada (HTTP {status})", "checked": False}

    error = (data.get("error") or {}) if isinstance(data, dict) else {}
    if error.get("code") == _INVALID_KEY_CODE:
        return {"ok": False, "error": error.get("message") or "API key no válida", "checked": True}
    # Un 400 que se queja de otra cosa (falta la imagen) significa que la clave
    # pasó la autenticación. Cualquier otra respuesta (límite de peticiones,
    # error del servidor) no dice nada de la clave.
    if status == 400 and error:
        return {"ok": True, "error": None, "checked": True}
    return {"ok": False, "error": f"No se pudo comprobar (HTTP {status})", "checked": False}


def test_image_host(host_id: str, api_key: Optional[str] = None, *, timeout: int = 8) -> dict:
    """¿Responde el proveedor y, si lleva clave, vale esa clave?

    Antes esto solo hacía un GET a la web y comprobaba que el campo de la clave
    no estuviera vacío, así que decía OK con una clave inventada. Eso es lo que
    hizo que imgbb diera "conectado" en Ajustes mientras fallaba en cada subida.

    Ahora la clave se valida de verdad contra la API del proveedor, sin subir
    ninguna imagen (validate_image_host_key). Si no se puede comprobar —red
    caída, proveedor sin endpoint conocido— se dice así en vez de darla por
    buena o por mala. Never raises."""
    meta = _BY_ID.get(host_id)
    if not meta:
        return {"ok": False, "error": f"Host desconocido: {host_id}"}
    if meta["needs_key"] and not (api_key and api_key.strip()):
        return {"ok": False, "error": f"{meta['label']} necesita una API key"}
    if meta["needs_key"]:
        check = validate_image_host_key(host_id, api_key or "", timeout=timeout)
        if check["checked"]:
            return ({"ok": True, "key_checked": True} if check["ok"]
                    else {"ok": False, "key_checked": True,
                          "error": f"API key no válida: {check['error']}"})
        # No se pudo comprobar la clave: se cae al ping de siempre, avisando de
        # que la clave se queda sin verificar en vez de fingir que está bien.
        motivo = check.get("error")
    else:
        motivo = None
    try:
        resp = http_cliente.pedir("GET", meta["url"], cabeceras={"User-Agent": "emuwarez-uploadrr/2"},
                                  timeout=timeout)
        if 200 <= resp.status_code < 400:
            return {"ok": True, "key_checked": not meta["needs_key"], "key_error": motivo}
        return {"ok": False, "error": f"HTTP {resp.status_code}"}
    except http_cliente.ErrorHTTP as exc:
        # Un 403/429 de Cloudflare a la portada: el servidor está, y subir funciona.
        if exc.status < 500:
            return {"ok": True, "key_checked": not meta["needs_key"], "key_error": motivo}
        return {"ok": False, "error": f"HTTP {exc.status}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"No responde: {texto_de_error(exc)}"}
