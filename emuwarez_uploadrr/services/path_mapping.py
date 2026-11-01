"""Remote path mapping — translate the paths Radarr/Sonarr report into the
paths where the media is actually reachable from where this app runs.

Like Radarr/Sonarr's "Remote Path Mappings": you mount the remote library
anywhere (SSHFS/NFS/SMB) and map the reported prefix to your local mount, so
MediaInfo / verification / upload can read the real file without having to
reproduce the exact `/data/...` layout locally.

Stored as JSON in the setting `library.path_mappings`:
    [{"from": "/data/media", "to": "/home/alvaro/mnt/emu-media"}, ...]
"""
from __future__ import annotations

import json
import os

from ..database import connect, db_path, get_setting_canonical

_SETTING_KEY = "library.path_mappings"


def get_path_mappings(conn=None) -> list[dict]:
    own = conn is None
    conn = conn or connect(db_path())
    try:
        raw = get_setting_canonical(conn, _SETTING_KEY)
        if not raw:
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [{"from": str(m["from"]), "to": str(m["to"])}
                for m in data if isinstance(m, dict) and m.get("from") and m.get("to")]
    except Exception:
        return []
    finally:
        if own:
            conn.close()


def resolve_local_path(path: str | None, conn=None, mappings: list[dict] | None = None) -> str | None:
    """Return `path` with the first matching mapping applied (longest prefix
    wins). Paths with no matching mapping are returned unchanged, so this is a
    no-op when no mappings are configured. `mappings` ya leídas, para no pedirlas
    en cada ruta de un recorrido largo."""
    if not path:
        return path
    if mappings is None:
        mappings = get_path_mappings(conn)
    for m in sorted(mappings, key=lambda x: len(x["from"]), reverse=True):
        frm = m["from"].rstrip("/")
        to = m["to"].rstrip("/")
        if path == m["from"] or path == frm:
            return to or "/"
        if path.startswith(frm + "/"):
            return to + path[len(frm):]
    return path


def ruta_de_lectura(item: dict, conn=None) -> str | None:
    """De qué fichero se lee este elemento: `prepared_path` si SIGUE EXISTIENDO,
    y si no `path`. Devuelve la ruta tal como está guardada, sin mapear.

    Las dos columnas quieren decir cosas distintas. `path` es lo que dice
    Radarr/Sonarr y la sincronización lo refresca en cada pasada. `prepared_path`
    es dónde dejó el fichero la última subida, y NADIE lo refresca: no lo toca la
    sincronización ni se borra al terminar.

    Mientras las dos apuntan al mismo sitio da igual cuál se lea, y por eso el
    `prepared_path or path` de siempre parecía inofensivo. Deja de serlo en
    cuanto el fichero se mueve por fuera:

        el usuario deshace a mano el renombrado de la carpeta que hacía la
        versión vieja, Sonarr vuelve a escanear, `path` queda bien y
        `prepared_path` se queda apuntando a una carpeta que ya no existe.
        Como iba primero, ganaba, y subir contestaba "Archivo no accesible"
        con una ruta que la ficha del contenido enseñaba correcta
        (The Tudors S03, 2026-08-04).

    Igual de roto queda si borras a mano los enlaces de la carpeta de subidas,
    o si el fichero se vuelve a descargar y Sonarr lo deja en otro sitio.

    Preferir el que existe, y no el que se escribió antes, se arregla solo en
    todos esos casos: con la subida a medias `prepared_path` está vivo y manda,
    y en cuanto muere se vuelve solo a la biblioteca, que es lo que la
    sincronización mantiene al día.
    """
    preparada = item.get("prepared_path")
    if preparada:
        local = resolve_local_path(preparada, conn=conn) or preparada
        if os.path.exists(local):
            return preparada
    return item.get("path") or preparada
