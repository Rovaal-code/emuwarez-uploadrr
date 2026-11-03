#!/usr/bin/env python3
"""Baja los iconos de los sitios que enseña la interfaz a `frontend/src/assets/iconos/<dominio>.<ext>`.

Los logos no cambian y la lista de sitios es cerrada, así que los iconos van dentro del proyecto: el navegador no
pide nada a nadie de fuera. Se vuelve a correr solo al añadir un proveedor (o un sitio de fichas) nuevo:

    python scripts/descargar_iconos.py            # baja los que faltan
    python scripts/descargar_iconos.py --forzar   # vuelve a bajarlos todos

Para cada dominio prueba, en orden: el icono que declara el propio sitio (`favicon` de `image_hosts`, resuelto a
mano), `https://<dominio>/favicon.ico` y, como último recurso, el servicio de iconos de Google. Si Google devuelve el
mismo icono para varios dominios es su globo genérico (no conoce el sitio): se descarta y la interfaz enseña el icono
de reserva de siempre. Mira el resultado antes de commitear: un icono mal elegido se cambia a mano en esa carpeta,
y uno que pese más de 20 KB (se pinta a 16 px) se reduce a un PNG de 64 px; un test vigila las dos cosas.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from emuwarez_uploadrr.constants import EMU_BASE_URL  # noqa: E402
from emuwarez_uploadrr.integrations import http_cliente  # noqa: E402
from emuwarez_uploadrr.services.image_hosts import IMAGE_HOSTS  # noqa: E402
from emuwarez_uploadrr.services.source_assistant import PROVIDER_DOMAINS  # noqa: E402

CARPETA = RAIZ / "frontend" / "src" / "assets" / "iconos"

# Las webs a las que enlazan las fichas (TMDb, IMDb, TVDB, MAL, TVmaze): `idVerifyUrl` en `utils/libraryItem.ts` y
# `RequestFormModal.tsx`. Un test comprueba que no falte ninguna.
WEBS_DE_FICHAS = ("www.themoviedb.org", "www.imdb.com", "thetvdb.com", "myanimelist.net", "www.tvmaze.com")

_LIMITE = 300_000
# sha256 del icono genérico (el globo, 649 bytes) que Google devuelve a 64 px para un sitio que no conoce. Con esto se
# descarta aunque sea el único de la tanda; repetido entre varios dominios también se descarta (otro tamaño u otro globo).
HUELLAS_GENERICAS = frozenset({"beaa2f87e130b8b83363dc30f9143c3712094be82f61d2c4037b91fceff86b85"})
_AGENTE = "Mozilla/5.0 (compatible; emuwarez-uploadrr/iconos)"
_FIRMAS = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"\x00\x00\x01\x00", "ico"),
)


def _host(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def dominios_con_icono() -> list[str]:
    """Los dominios cuyo icono enseña la interfaz: proveedores de imágenes y de vídeo, eMuwarez y las fichas."""
    dominios = {_host(h["url"]) for h in IMAGE_HOSTS}
    dominios |= set(PROVIDER_DOMAINS.values())
    dominios.add(_host(EMU_BASE_URL))
    dominios |= set(WEBS_DE_FICHAS)
    return sorted(d for d in dominios if d)


def extension_de(datos: bytes) -> Optional[str]:
    """La extensión por los primeros bytes, o None si no es una imagen que se sirva (SVG incluido)."""
    for firma, ext in _FIRMAS:
        if datos.startswith(firma) and len(datos) > len(firma):
            return ext
    if len(datos) > 12 and datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "webp"
    return None


def _candidatas(dominio: str) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    for h in IMAGE_HOSTS:
        if _host(h["url"]) == dominio and h.get("favicon"):
            urls.append(("sitio", h["favicon"]))
    raiz = f"https://{dominio}/favicon.ico"
    if raiz not in [u for _, u in urls]:
        urls.append(("sitio", raiz))
    urls.append(("google", "https://www.google.com/s2/favicons?" + urllib.parse.urlencode({"sz": 64, "domain": dominio})))
    return urls


def _bajar(url: str) -> Optional[bytes]:
    for intento in range(3):  # un DNS que falla un momento no debe dejar un sitio sin icono
        try:
            r = http_cliente.pedir("GET", url, cabeceras={"User-Agent": _AGENTE, "Accept": "image/*"},
                                   timeout=10, limite=_LIMITE + 1)
        except http_cliente.ErrorHTTP:
            return None  # el sitio contesta que no hay: no se insiste
        except http_cliente.ErrorConexion:
            time.sleep(1 + intento)
            continue
        return r.content if len(r.content) <= _LIMITE else None
    return None


def buscar(dominio: str) -> Optional[tuple[str, str, bytes]]:
    """(origen, extensión, bytes) del primer icono válido, o None."""
    for origen, url in _candidatas(dominio):
        datos = _bajar(url)
        ext = extension_de(datos) if datos else None
        if ext:
            return origen, ext, datos  # type: ignore[return-value]
    return None


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--forzar", action="store_true", help="vuelve a bajar también los que ya están")
    args = ap.parse_args(argv)

    CARPETA.mkdir(parents=True, exist_ok=True)
    tenidos = {p.name.rsplit(".", 1)[0]: p for p in CARPETA.iterdir() if p.is_file()}
    hallados: dict[str, tuple[str, str, bytes]] = {}
    for d in dominios_con_icono():
        if d in tenidos and not args.forzar:
            continue
        r = buscar(d)
        if r:
            hallados[d] = r
        else:
            print(f"  sin icono   {d}")

    # El globo genérico de Google es el mismo fichero para todo sitio que no conoce: repetido, se descarta.
    huellas: dict[str, list[str]] = {}
    for d, (origen, _, datos) in hallados.items():
        if origen == "google":
            huellas.setdefault(hashlib.sha256(datos).hexdigest(), []).append(d)
    genericos = {d for h, ds in huellas.items() if len(ds) > 1 or h in HUELLAS_GENERICAS for d in ds}

    for d, (origen, ext, datos) in sorted(hallados.items()):
        if d in genericos:
            print(f"  genérico    {d} (Google no lo conoce)")
            continue
        for viejo in CARPETA.glob(f"{d}.*"):
            viejo.unlink()
        (CARPETA / f"{d}.{ext}").write_bytes(datos)
        print(f"  {origen:9}   {d}.{ext}  {len(datos)} bytes")

    faltan = [d for d in dominios_con_icono() if not any(CARPETA.glob(f"{d}.*"))]
    if faltan:
        print(f"\nSin icono (saldrá el de reserva): {', '.join(faltan)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
