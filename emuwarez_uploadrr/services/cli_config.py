"""Lectura del fichero de configuración del CLI antiguo.

La aplicación tiene DOS sitios donde vive la configuración: la tabla
`settings` (lo que escribe la interfaz, y la fuente buena) y el fichero JSON
que dejó el CLI. Este módulo existe para leer el segundo **sin arrastrar
`legacy.py`** hasta los servicios, y sobre todo sin sus modales:

`legacy.load_app_config()` puede, cuando la configuración está cifrada y no se
le da contraseña, llamar a `die()` -> `SystemExit`, o pedir la contraseña por
teclado. Eso vale en una terminal y es inaceptable en un servicio web:
comprobado el 2026-08-01, `services/requests.py` levantaba `SystemExit` desde
el hilo del servidor solo por existir un `config.enc.json` sin clave en la BD.

Aquí no se descifra nada a propósito. Ninguno de los sitios que leían esa
configuración pasó jamás una contraseña (todas las llamadas usaban el valor por
defecto `None`), así que la rama cifrada nunca podía acertar: solo podía morir
o bloquearse. Si hay configuración cifrada, esto devuelve None y quien la
quiera que la ponga en la interfaz.

Esto es un puente hacia atrás, no una fuente de verdad. Cuando nadie tenga ya
configuración del CLI antiguo, el módulo entero desaparece.
"""
from __future__ import annotations

import json
from typing import Optional

from ..constants import CONFIG_ENC_FILE, CONFIG_FILE


def _leer_config_plana() -> dict:
    """El JSON del CLI, o un diccionario vacío. Nunca lanza."""
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        # Un fichero corrupto o ilegible no puede tumbar una sincronización:
        # es un respaldo, no la fuente.
        pass
    return {}


def hay_config_cifrada() -> bool:
    """True si existe configuración cifrada del CLI, que aquí no se lee."""
    try:
        return CONFIG_ENC_FILE.exists()
    except Exception:
        return False


def emu_api_key() -> Optional[str]:
    """La API key de eMuwarez del CLI antiguo, si la hay. None en cualquier
    otro caso, incluida la configuración cifrada."""
    valor = _leer_config_plana().get("emu_api_key")
    valor = (valor or "").strip() if isinstance(valor, str) else ""
    return valor or None
