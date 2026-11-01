"""El registro de ajustes: qué es cada ajuste que expone Configuración.

Antes cada ajuste estaba escrito en cuatro o cinco sitios: la clave en
`services/settings.py`, el valor por defecto y la conversión desde texto a mano
en el GET de `web/api/settings.py`, la validación y la escritura en su PUT, y si
era un secreto, otra vez en `es_secreto`. Añadir `remux.no_reflink_copies` tocó
todos. Aquí se declara una vez: el nombre que tiene en el API, la clave en la
tabla, el tipo, el valor por defecto, los valores que admite y si es un secreto.

De aquí salen los valores por defecto, la conversión (texto guardado → valor
del API y al revés), la validación de lo que llega en un PUT y qué claves son
secretos. Leer y escribir sigue siendo cosa de `services/settings.py`, la única
puerta a la tabla: este módulo no la toca y no importa nada que la toque.

Lo que no cabe en un tipo simple se queda fuera y lo trata su propio código:
las listas y estructuras guardadas como JSON (grupos de subida, prioridad de
proveedores, raíces permitidas, rutas remotas, hosts de imágenes, eventos de
cada canal). `web/api/settings.py::FUERA_DEL_REGISTRO` las enumera.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .mkv_remux import MODO_PISTAS_POR_DEFECTO, MODOS_PISTAS
from .uploadrr_contract import DEFAULT_TIMEOUT_SECONDS, RUNTIME_EMU, RUNTIME_GENERIC

BOOL = "bool"
INT = "int"
CHOICE = "choice"
STR = "str"
SECRET = "secret"
TIPOS = (BOOL, INT, CHOICE, STR, SECRET)


@dataclass(frozen=True)
class Ajuste:
    # Cómo se llama en el API (SettingsResponse / SettingsUpdateRequest).
    campo: str
    # La clave en la tabla settings.
    clave: str
    tipo: str
    # Lo que vale si nunca se guardó (o se guardó vacío, que para
    # get_setting_canonical es lo mismo). None: sin valor.
    defecto: Any = None
    # Los únicos valores que admite (INT o CHOICE). Vacío: cualquiera.
    opciones: tuple = ()
    # El mínimo que admite un INT en un PUT.
    minimo: Optional[int] = None
    # Si un valor guardado fuera de `opciones` se lee como `defecto`. Lo apaga
    # quien ya se leía tal cual en el resto del código, para que Configuración
    # enseñe lo mismo que se usa.
    filtra_al_leer: bool = True
    # Solo SECRET: el prefijo de `<x>_configured` / `<x>_masked` en el GET (no
    # se llaman igual que el campo del PUT), si el GET devuelve el valor
    # enmascarado o solo si está puesto, y si un PUT puede quitarlo con `clear`.
    campo_estado: str = ""
    enmascara: bool = True
    borrable: bool = False
    # Texto del error cuando un PUT trae un valor que no vale. {valor} y
    # {opciones} se sustituyen. Vacío: el genérico de `error_de`.
    mensaje: str = ""


# Valores que admite upload_max_concurrent. Viven aquí y upload_execution los
# toma de aquí (el registro no puede importar upload_execution: se cerraría un
# ciclo a través de services/settings.py).
UPLOAD_MAX_CONCURRENT_SETTING_KEY = "uploads.max_concurrent"
UPLOAD_MAX_CONCURRENT_CHOICES = tuple(range(0, 11))  # 0, 1, 2, … 10
UPLOAD_MAX_CONCURRENT_DEFAULT = 1

RECENT_ACTIVITY_CHOICES = (0, 50, 100, 150, 200, 250, 300)  # 0 = sin límite


_REGISTRO: tuple[Ajuste, ...] = (
    # Subida
    Ajuste("default_release_tag", "default_release_tag", STR, "EMUWAREZ"),
    Ajuste("tmdb_watch_region", "tmdb_watch_region", STR, "ES"),
    Ajuste("tmdb_localize_series_titles", "tmdb.localize_series_titles", BOOL, True),
    Ajuste("emu_username", "emu.username", STR),
    Ajuste("emu_add_logo", "emu.add_logo", BOOL, True),
    Ajuste("emu_per_episode_screens", "emu.per_episode_screens", BOOL, False),
    Ajuste("upload_max_concurrent", UPLOAD_MAX_CONCURRENT_SETTING_KEY, INT, UPLOAD_MAX_CONCURRENT_DEFAULT,
           opciones=UPLOAD_MAX_CONCURRENT_CHOICES),
    # Integraciones obligatorias. Sus PUT validan la clave contra el servicio
    # antes de guardar, y eso lo sigue haciendo el endpoint.
    Ajuste("tmdb_api_key", "tmdb.api_key", SECRET, campo_estado="tmdb_api_key"),
    Ajuste("emu_api_key", "emu.api_key", SECRET, campo_estado="emu_api_key"),
    # qBittorrent
    Ajuste("qbit_url", "qbit.url", STR),
    Ajuste("qbit_tag", "qbit.tag", STR),
    Ajuste("qbit_username", "qbit.username", STR),
    Ajuste("qbit_password", "qbit.password", SECRET, campo_estado="qbit_password",
           enmascara=False, borrable=True),
    # El proxy de qui lleva su clave dentro: ni enmascarada se devuelve. Se
    # quita con qbit_qui_proxy_clear, no con `clear`.
    Ajuste("qbit_qui_proxy_url", "qbit.qui_proxy_url", SECRET, campo_estado="qbit_qui", enmascara=False),
    # Uploadrr
    Ajuste("uploadrr_path", "uploadrr.path", STR),
    Ajuste("uploadrr_runtime_type", "uploadrr.runtime_type", CHOICE, RUNTIME_EMU,
           opciones=(RUNTIME_EMU, RUNTIME_GENERIC),
           # uploadrr_contract y upload_preflight lo leen tal cual.
           filtra_al_leer=False,
           mensaje="uploadrr_runtime_type inválido: '{valor}'. Debe ser uno de: {opciones}"),
    Ajuste("uploadrr_python_path", "uploadrr.python_path", STR),
    # uploadrr_contract lo lee sin mirar el mínimo; el mínimo es para el PUT.
    Ajuste("uploadrr_timeout", "uploadrr.timeout", INT, DEFAULT_TIMEOUT_SECONDS, minimo=1),
    # Notificaciones
    Ajuste("notify_ui_enabled", "notify.ui.enabled", BOOL, True),
    Ajuste("notify_discord_enabled", "notify.discord.enabled", BOOL, False),
    Ajuste("notify_discord_webhook_url", "notify.discord.webhook_url", SECRET,
           campo_estado="notify_discord_webhook", borrable=True),
    Ajuste("notify_telegram_enabled", "notify.telegram.enabled", BOOL, False),
    Ajuste("notify_telegram_bot_token", "notify.telegram.bot_token", SECRET,
           campo_estado="notify_telegram_bot_token", borrable=True),
    Ajuste("notify_telegram_chat_id", "notify.telegram.chat_id", STR),
    # Otros
    Ajuste("series_ignore_specials", "series.ignore_specials", BOOL, True),
    Ajuste("source_engine_enabled", "source_engine.enabled", BOOL, False),
    # Se lee con mkv_remux.modo_pistas(), que traduce el ajuste viejo de sí/no,
    # y el PUT escribe también ese ajuste viejo (ver web/api/settings.py).
    Ajuste("remux_track_mode", "remux.track_mode", CHOICE, MODO_PISTAS_POR_DEFECTO, opciones=MODOS_PISTAS),
    Ajuste("remux_no_reflink_copies", "remux.no_reflink_copies", BOOL, False),
    Ajuste("recent_activity_limit", "dashboard.recent_activity_limit", INT, 100, opciones=RECENT_ACTIVITY_CHOICES),
)

AJUSTES: dict[str, Ajuste] = {a.campo: a for a in _REGISTRO}
POR_CLAVE: dict[str, Ajuste] = {a.clave: a for a in _REGISTRO}

assert len(AJUSTES) == len(POR_CLAVE) == len(_REGISTRO), "campo o clave repetidos en el registro de ajustes"
assert all(a.tipo in TIPOS for a in _REGISTRO)

CLAVES_SECRETAS: frozenset[str] = frozenset(a.clave for a in _REGISTRO if a.tipo == SECRET)


def desde_texto(ajuste: Ajuste, crudo: Optional[str]) -> Any:
    """El valor del API para lo que hay guardado. `crudo` es lo que devuelve
    get_setting_canonical: None si no está o está vacío.

    BOOL: solo el contrario escrito tal cual lo cambia ("false" apaga uno que
    viene encendido, "true" enciende uno que viene apagado); cualquier otra
    cosa es el valor por defecto, como hacía cada lectura a mano."""
    if ajuste.tipo == BOOL:
        if ajuste.defecto:
            return crudo != "false"
        return crudo == "true"
    if crudo is None:
        return ajuste.defecto
    if ajuste.tipo == INT:
        try:
            valor: Any = int(crudo)
        except (TypeError, ValueError):
            return ajuste.defecto
    else:
        valor = crudo
    if ajuste.opciones and ajuste.filtra_al_leer and valor not in ajuste.opciones:
        return ajuste.defecto
    return valor


def a_texto(ajuste: Ajuste, valor: Any) -> str:
    """Lo que se guarda para un valor que llega en un PUT (ya validado)."""
    if ajuste.tipo == BOOL:
        return "true" if valor else "false"
    if ajuste.tipo == INT:
        return str(valor)
    if ajuste.tipo == CHOICE:
        return valor
    return str(valor).strip()


def error_de(ajuste: Ajuste, valor: Any) -> Optional[str]:
    """Por qué no vale `valor` para este ajuste, o None si vale."""
    fuera = bool(ajuste.opciones) and valor not in ajuste.opciones
    bajo = ajuste.minimo is not None and valor < ajuste.minimo
    if not (fuera or bajo):
        return None
    if ajuste.mensaje:
        opciones = ", ".join(sorted(str(o) for o in ajuste.opciones))
        return ajuste.mensaje.format(valor=valor, opciones=opciones)
    if bajo:
        if ajuste.minimo == 1:
            return f"{ajuste.campo} debe ser un entero positivo"
        return f"{ajuste.campo} debe ser un entero mayor o igual que {ajuste.minimo}"
    opciones = ajuste.opciones if ajuste.tipo == INT else list(ajuste.opciones)
    return f"{ajuste.campo} debe ser uno de {opciones}"
