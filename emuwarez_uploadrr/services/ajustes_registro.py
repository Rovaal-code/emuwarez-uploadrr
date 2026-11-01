"""Registro declarativo de ajustes: qué es cada clave de la tabla `settings`.

Cada ajuste dice su clave, su tipo, su valor por defecto, los valores que
admite y si guarda un secreto. Lo leen `services/settings.py` (qué se enmascara,
cómo se lee un sí/no) y la API de ajustes (cómo se lee y se escribe), en vez de
repetir ese conocimiento en cada sitio. Añadir un ajuste de sí/no es una línea
aquí, sin tocar la lectura ni la escritura.

No lee la base: solo describe. La puerta a la tabla sigue siendo
`services/settings.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

BOOL = "bool"
TEXTO = "texto"
ENTERO = "entero"
JSON = "json"


@dataclass(frozen=True)
class Ajuste:
    clave: str
    tipo: str = TEXTO
    defecto: object = None
    permitidos: Optional[tuple] = None
    secreto: bool = False


def _bool(clave: str, defecto: bool) -> Ajuste:
    return Ajuste(clave, BOOL, defecto)


def _secreto(clave: str) -> Ajuste:
    return Ajuste(clave, TEXTO, None, secreto=True)


_AJUSTES: tuple[Ajuste, ...] = (
    # Los sí/no: `defecto` es lo que vale mientras nadie lo ha guardado.
    _bool("tmdb.localize_series_titles", True),
    _bool("notify.discord.enabled", False),
    _bool("notify.telegram.enabled", False),
    _bool("series.ignore_specials", True),
    _bool("source_engine.enabled", False),
    _bool("emu.add_logo", True),
    _bool("emu.per_episode_screens", False),
    _bool("remux.no_reflink_copies", False),
    # Las claves. Los alias antiguos y la contraseña de qBittorrent también lo
    # son aunque no salgan en el estado de la configuración.
    _secreto("tmdb.api_key"), _secreto("emu.api_key"), _secreto("emu.endpoint_url"),
    _secreto("notify.discord.webhook_url"), _secreto("notify.telegram.bot_token"),
    _secreto("tmdb_api_key"), _secreto("emu_api_key"),
    _secreto("qbit.password"), _secreto("qbit.qui_proxy_url"),
)

REGISTRO: dict[str, Ajuste] = {a.clave: a for a in _AJUSTES}

# Una clave por host de imágenes (imghost.key.<id>): no se puede listar de antemano.
PREFIJOS_SECRETOS: tuple[str, ...] = ("imghost.key.",)


def ajuste(clave: str) -> Optional[Ajuste]:
    return REGISTRO.get(clave)


def es_secreto(clave: str) -> bool:
    a = REGISTRO.get(clave)
    return bool(a and a.secreto) or clave.startswith(PREFIJOS_SECRETOS)


def claves_secretas() -> frozenset[str]:
    return frozenset(a.clave for a in _AJUSTES if a.secreto)


def bool_de(clave: str, guardado: Optional[str]) -> bool:
    """El sí/no de un ajuste a partir de lo guardado (None o vacío = el defecto)."""
    a = REGISTRO[clave]
    if a.tipo != BOOL:
        raise ValueError(f"{clave} no es un ajuste de sí/no")
    if guardado is None or guardado == "":
        return bool(a.defecto)
    return guardado != "false" if a.defecto else guardado == "true"


def texto_de_bool(valor: bool) -> str:
    return "true" if valor else "false"
