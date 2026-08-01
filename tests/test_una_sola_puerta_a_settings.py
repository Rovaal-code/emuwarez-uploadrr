"""La tabla `settings` se lee por un solo sitio.

Hallazgo 3.3 de la auditoría: había cuatro formas de leer un ajuste y catorce
consultas sueltas repartidas, y las sueltas se saltaban el mapa de alias de
claves antiguas (database.CANONICAL_SETTING_ALIASES). De ahí salió un fallo
real y reproducido: Diagnóstico decía "Secretos sin configurar" a quien las
tenía puestas, porque preguntaba por la grafía con guion bajo mientras la
interfaz escribe solo la de punto.

Cerrar el agujero no vale de nada si mañana aparece la consulta número quince.
Esto lo impide.
"""
from __future__ import annotations

import ast
import io
import pathlib
import re
import tokenize

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "emuwarez_uploadrr"

# Los únicos que pueden tocar la tabla: la puerta y la capa de base de datos
# (que implementa la resolución de alias sobre la que se apoya la puerta).
PERMITIDOS = {"services/settings.py", "database.py"}


# Una consulta de verdad, no prosa: hace falta un verbo SQL en la misma cadena.
# Sin esto saltaba con un docstring que decía "resolves paths from settings at
# runtime" y con el propio `from ...services.settings import`.
_VERBO_SQL = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b")
_TABLA = re.compile(r"\b(FROM|INTO|UPDATE)\s+settings\b", re.I)


def _cadenas(src: str) -> list[str]:
    """Los literales de texto del fichero, que es donde vive el SQL."""
    try:
        return [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
                if t.type is tokenize.STRING]
    except tokenize.TokenError:
        return [src]


def test_nadie_consulta_la_tabla_settings_por_su_cuenta():
    culpables = []
    for f in sorted(RAIZ.rglob("*.py")):
        rel = str(f.relative_to(RAIZ))
        if rel in PERMITIDOS:
            continue
        if any(_TABLA.search(c) and _VERBO_SQL.search(c) for c in _cadenas(f.read_text())):
            culpables.append(rel)
    assert not culpables, (
        "\nSQL directo contra la tabla settings fuera de services/settings.py:\n  "
        + "\n  ".join(culpables)
        + "\n\nUsa get_setting_canonical (resuelve el alias antiguo con guion bajo)."
          "\nSi de verdad necesitas la clave exacta y ninguna otra, get_setting_raw,"
          "\nque se llama así para que elegirla sea una decisión y no un descuido."
    )


def test_la_puerta_ofrece_lo_que_hace_falta():
    """Si a la puerta le falta una operación, el siguiente la esquivará."""
    from emuwarez_uploadrr.services import settings

    for nombre in ("get_setting_canonical", "get_setting_raw", "set_setting",
                   "set_setting_canonical", "get_configured", "all_settings",
                   "setting_exists", "mask_secret"):
        assert hasattr(settings, nombre), f"falta {nombre} en la puerta"


def test_la_capa_de_dominio_no_importa_de_la_web():
    """Hallazgo 6.1: services/ importaba de web/services/ para leer ajustes.
    Leer un ajuste es del dominio; enmascarar un secreto para una respuesta
    HTTP, de la web."""
    culpables = []
    for f in sorted((RAIZ / "services").rglob("*.py")):
        texto = f.read_text()
        if re.search(r"^\s*from\s+\.\.web[\s.]|^\s*from\s+emuwarez_uploadrr\.web[\s.]", texto, re.M):
            culpables.append(str(f.relative_to(RAIZ)))
    assert not culpables, (
        "\nservices/ importando de web/:\n  " + "\n  ".join(culpables)
    )


def test_el_alias_antiguo_se_sigue_resolviendo(isolated_db):
    """La puerta no puede romper una instalación que venga del CLI: sus claves
    están escritas con guion bajo."""
    from emuwarez_uploadrr.database import connect, db_path, init_db
    from emuwarez_uploadrr.services.settings import get_setting_canonical, get_setting_raw

    conn = connect(db_path()); init_db(conn)
    try:
        conn.execute("INSERT INTO settings (key, value) VALUES ('tmdb_api_key', 'clave-vieja')")
        conn.commit()
        assert get_setting_canonical(conn, "tmdb.api_key") == "clave-vieja"
        # Y la cruda es literal, que para eso se llama así.
        assert get_setting_raw(conn, "tmdb.api_key") is None
        assert get_setting_raw(conn, "tmdb_api_key") == "clave-vieja"
    finally:
        conn.close()
