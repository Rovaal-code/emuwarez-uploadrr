"""Qué versión estoy ejecutando, y si hay una más nueva publicada.

El repositorio y el paquete de imágenes son privados, así que la aplicación no
puede preguntarle al registro si hay algo nuevo (comprobado: el token anónimo
de GHCR no se emite y el manifest devuelve 403). La salida es un **manifiesto
público** aparte: un único JSON con el commit, la fecha, el digest y una nota
del cambio. El código y la imagen siguen privados; lo único público es "qué
versión es la última", que es justo lo que hace falta saber.

Lo propio se sella en la imagen al construirla (ver Dockerfile: APP_COMMIT y
APP_BUILD_DATE). Sin sellar -por ejemplo ejecutando desde el código fuente-
la comparación se desactiva sola y lo dice, en vez de inventarse un estado.

Nada de esto puede tumbar la pestaña de Diagnóstico: si el manifiesto no se
puede leer, se devuelve el motivo y ya.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Optional

from .. import __version__
from ..integrations import http_cliente
from ..integrations.base import texto_de_error

# Dónde vive el manifiesto. Se puede apuntar a otro sitio con una variable de
# entorno, para probar sin tocar el publicado.
URL_MANIFIESTO = os.environ.get(
    "UPLOADRR_VERSION_MANIFEST_URL",
    "https://raw.githubusercontent.com/Kisnov/uploadrr-version/main/latest.json",
)

# Una consulta por hora basta: publicar una versión no es algo que pase cada
# minuto, y el usuario puede forzarla desde el botón de la tarjeta.
_SEGUNDOS_CACHE = 3600
_TIEMPO_ESPERA = 6

_cache: dict[str, Any] = {"cuando": 0.0, "datos": None, "error": None}
_candado = threading.Lock()


def version_local() -> dict[str, Optional[str]]:
    """Lo que sé de mí mismo: versión, commit y fecha de construcción."""
    def _limpio(nombre: str) -> Optional[str]:
        valor = (os.environ.get(nombre) or "").strip()
        # El Dockerfile pone "unknown" cuando se construye sin el build-arg.
        return valor if valor and valor != "unknown" else None

    return {
        "version": __version__,
        "commit": _limpio("APP_COMMIT"),
        "commit_corto": (_limpio("APP_COMMIT") or "")[:7] or None,
        "construida": _limpio("APP_BUILD_DATE"),
    }


def _descargar_manifiesto() -> tuple[Optional[dict], Optional[str]]:
    try:
        r = http_cliente.pedir("GET", URL_MANIFIESTO, cabeceras={"User-Agent": "emuwarez-uploadrr"},
                               timeout=_TIEMPO_ESPERA)
        return json.loads(r.content.decode("utf-8")), None
    except http_cliente.ErrorHTTP as e:
        if e.status == 404:
            return None, "El manifiesto de versiones no existe todavía."
        return None, f"El manifiesto respondió {e.status}."
    except http_cliente.ErrorConexion as e:
        return None, f"No se pudo consultar el manifiesto: {e.motivo}"
    except Exception as e:                      # JSON roto, timeout, lo que sea
        return None, f"No se pudo leer el manifiesto: {texto_de_error(e)}"


def manifiesto(*, forzar: bool = False) -> tuple[Optional[dict], Optional[str]]:
    """El manifiesto publicado, cacheado una hora. (datos, error)."""
    with _candado:
        fresco = (time.time() - _cache["cuando"]) < _SEGUNDOS_CACHE
        if not forzar and fresco and (_cache["datos"] or _cache["error"]):
            return _cache["datos"], _cache["error"]
        datos, error = _descargar_manifiesto()
        _cache.update({"cuando": time.time(), "datos": datos, "error": error})
        return datos, error


def estado_de_version(*, forzar: bool = False) -> dict[str, Any]:
    """Lo que enseña la tarjeta de Diagnóstico.

    `estado` es uno de:
      al_dia        — el commit sellado coincide con el publicado
      hay_novedad   — no coinciden: hay imagen nueva que pullear
      desconocido   — no se puede comparar, y `motivo` dice por qué
    """
    local = version_local()
    datos, error = manifiesto(forzar=forzar)

    remoto = {
        "commit": (datos or {}).get("commit"),
        "commit_corto": ((datos or {}).get("commit") or "")[:7] or None,
        "digest": (datos or {}).get("digest"),
        "publicada": (datos or {}).get("fecha"),
        "notas": (datos or {}).get("notas"),
        "version": (datos or {}).get("version"),
    }

    if error:
        estado, motivo = "desconocido", error
    elif not local["commit"]:
        estado, motivo = "desconocido", (
            "Esta build no lleva sellado el commit, así que no hay con qué comparar "
            "(pasa al ejecutar desde el código fuente en vez de desde la imagen).")
    elif not remoto["commit"]:
        estado, motivo = "desconocido", "El manifiesto no dice qué commit es el último."
    elif local["commit"] == remoto["commit"]:
        estado, motivo = "al_dia", None
    else:
        estado, motivo = "hay_novedad", None

    # El digest solo es TUYO si estás al día: el manifiesto publica el de la
    # última imagen, y decir que es el tuyo cuando vas por detrás sería mentir.
    return {
        **local,
        "digest": remoto["digest"] if estado == "al_dia" else None,
        "estado": estado,
        "motivo": motivo,
        "ultima": remoto,
    }
