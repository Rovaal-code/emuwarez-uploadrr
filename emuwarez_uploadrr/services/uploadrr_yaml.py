"""Editor por líneas del `data/config.yaml` de Uploadrr-EMU.

Estas funciones NO tocan el disco: reciben y devuelven `lines: list[str]`, la
lista de líneas ya leída. Quien lee y escribe el fichero es quien las llama
(`services/uploadrr_config_staging.py`, que además hace copia de seguridad
antes de sobrescribir).

Por qué por líneas y no con un analizador de YAML: el `config.yaml` de la
herramienta lleva comentarios y un orden que hay que respetar, y volver a
volcarlo con un serializador los perdería.

Vivían en `legacy.py` y se movieron aquí el 2026-08-01, invirtiendo la
dependencia: ahora es `legacy` quien las importa de aquí. El servicio que las
usaba ya documentaba que eran puras, que es justo lo que hizo el traslado
seguro.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional


def clean_optional_secret(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip().strip("\"'")
    if not value or value.lower() in {"null", "none", "~", "api_key", "apitmdb", "emuapikey"}:
        return None
    return value


def find_top_block(lines: list[str], key: str) -> tuple[int, int]:
    start = -1
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}\s*:\s*(?:#.*)?$", line):
            start = i
            break
    if start < 0:
        return -1, -1
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j] and not lines[j].startswith((" ", "\t", "#")) and re.match(r"^[^:#]+\s*:", lines[j]):
            end = j
            break
    return start, end


def get_block_key(lines: list[str], block: str, key: str, indent: int = 2) -> Optional[str]:
    start, end = find_top_block(lines, block)
    if start < 0:
        return None
    pattern = re.compile(rf"^\s{{{indent}}}{re.escape(key)}\s*:\s*(.*?)\s*(?:#.*)?$")
    for line in lines[start + 1 : end]:
        m = pattern.match(line)
        if m:
            return m.group(1).strip().strip("\"'")
    return None


def set_block_key(lines: list[str], block: str, key: str, value: str, indent: int = 2) -> str:
    start, end = find_top_block(lines, block)
    entry = " " * indent + f"{key}: {value}"
    if start < 0:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"{block}:", entry])
        return f"{block}.{key} creado"

    pattern = re.compile(rf"^\s{{{indent}}}{re.escape(key)}\s*:")
    for i in range(start + 1, end):
        if pattern.match(lines[i]):
            lines[i] = entry
            return f"{block}.{key} actualizado"

    lines.insert(start + 1, entry)
    return f"{block}.{key} creado"


# Entre comillas simples YAML pliega los saltos de línea y no admite controles.
_NO_CABE_EN_COMILLAS_SIMPLES = re.compile("[\x00-\x08\x0a-\x1f\x7f-\x9f\u2028\u2029]")


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)  # un número que ya lo era no pasa a cadena al reescribirlo
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(yaml_scalar(v) for v in value) + "]"
    value = str(value)
    if _NO_CABE_EN_COMILLAS_SIMPLES.search(value):
        # Entre dobles y con escapes; los controles C1 y los separadores Unicode
        # (que json deja tal cual) también, o YAML los leería como salto de línea.
        doble = json.dumps(value, ensure_ascii=False)
        return re.sub("[\x7f-\x9f\u2028\u2029]", lambda m: f"\\u{ord(m.group()):04x}", doble)
    return "'" + value.replace("'", "''") + "'"


def render_inline_mapping(mapping: dict[str, Any]) -> str:
    # Escalares YAML: repr() de Python escapa con `\`, que en una cadena entre
    # comillas simples de YAML es literal (una contraseña con `\` se leía mal).
    return "{" + ", ".join(f"{yaml_scalar(k)}: {yaml_scalar(v)}" for k, v in mapping.items()) + "}"


_SIMPLES = r"'(?:[^']|'')*'"
_DOBLES = r'"(?:[^"\\]|\\.)*"'
_LISTA = r"\[(?:" + _SIMPLES + "|" + _DOBLES + r"|[^\]'\"])*\]"
_CLAVE = _SIMPLES + "|" + _DOBLES + r"|[^,{}:'\"]+"
_VALOR = _SIMPLES + "|" + _DOBLES + "|" + _LISTA + r"|[^,{}]*?"
_PAR = re.compile(r"\s*(" + _CLAVE + r")\s*:\s*(" + _VALOR + r")\s*(?:,|$)")
_ITEM = re.compile(r"\s*(" + _SIMPLES + "|" + _DOBLES + r"|[^,'\"]+?)\s*(?:,|$)")


# Los escapes de las comillas dobles de YAML, que no son los de Python (`\/`, `\_`, `\N`…).
_ESCAPES_YAML = {
    "0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v", "f": "\f", "r": "\r",
    "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\", "N": "\x85", "_": "\xa0", "L": "\u2028", "P": "\u2029",
}
_ESCAPE = re.compile(r"\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|.)", re.S)


def _decodificar_escapes(cuerpo: str) -> str:
    def uno(m: re.Match) -> str:
        escape = m.group(1)
        if len(escape) > 1:
            try:
                return chr(int(escape[1:], 16))
            except ValueError:
                return m.group(0)
        return _ESCAPES_YAML.get(escape, m.group(0))
    return _ESCAPE.sub(uno, cuerpo)


def _sin_comillas(texto: str) -> Optional[str]:
    """El contenido de un escalar entre comillas; None si no lo está."""
    if len(texto) >= 2 and texto[0] == texto[-1] == "'":
        return texto[1:-1].replace("''", "'")
    if len(texto) >= 2 and texto[0] == texto[-1] == '"':
        return _decodificar_escapes(texto[1:-1])
    return None


def _leer_escalar(texto: str) -> Any:
    texto = texto.strip()
    entrecomillado = _sin_comillas(texto)
    if entrecomillado is not None:
        return entrecomillado
    if texto[:1] == "[" and texto[-1:] == "]":
        lista = _leer_lista(texto[1:-1])
        return texto if lista is None else lista
    # Las palabras que PyYAML (YAML 1.1) lee como booleano: solo en valores.
    if re.fullmatch(r"yes|Yes|YES|true|True|TRUE|on|On|ON", texto):
        return True
    if re.fullmatch(r"no|No|NO|false|False|FALSE|off|Off|OFF", texto):
        return False
    if texto.lower() in {"", "null", "none", "~"}:
        return None
    # Solo las formas que PyYAML resuelve como entero: `08` es una cadena, y `0` o `5` no.
    if re.fullmatch(r"[-+]?(?:0|[1-9]\d*)", texto):
        return int(texto)
    if re.fullmatch(r"-?\d+\.\d+", texto):
        return float(texto)
    return texto


def _leer_lista(cuerpo: str) -> Optional[list[Any]]:
    """Los elementos de `[a, b]` (sin anidar), p. ej. automatic_management_paths."""
    cuerpo = cuerpo.strip()
    elementos: list[Any] = []
    pos = 0
    while pos < len(cuerpo):
        elemento = _ITEM.match(cuerpo, pos)
        if not elemento:
            return None
        elementos.append(_leer_escalar(elemento.group(1)))
        pos = elemento.end()
    return elementos


def _leer_mapa_en_linea(cuerpo: str) -> Optional[dict[str, Any]]:
    """Lee `k: v, k: v` con escalares YAML (comillas simples o dobles, o sin
    comillas) y listas de ellos, que es lo que escribe render_inline_mapping y
    lo que trae el config de ejemplo del fork. None si algo no encaja."""
    cuerpo = cuerpo.strip()
    resultado: dict[str, Any] = {}
    pos = 0
    while pos < len(cuerpo):
        par = _PAR.match(cuerpo, pos)
        if not par:
            return None
        clave = par.group(1).strip()
        entrecomillada = _sin_comillas(clave)
        resultado[clave if entrecomillada is None else entrecomillada] = _leer_escalar(par.group(2))
        pos = par.end()
    return resultado


def find_child_block(lines: list[str], top_block: str, child: str, indent: int = 2) -> tuple[int, int]:
    start, end = find_top_block(lines, top_block)
    if start < 0:
        return -1, -1
    pattern = re.compile(rf"^\s{{{indent}}}{re.escape(child)}\s*:")
    child_start = -1
    for i in range(start + 1, end):
        if pattern.match(lines[i]):
            child_start = i
            break
    if child_start < 0:
        return -1, -1
    child_end = end
    next_child = re.compile(rf"^\s{{{indent}}}\S[^:]*\s*:")
    for j in range(child_start + 1, end):
        if next_child.match(lines[j]):
            child_end = j
            break
    return child_start, child_end


def get_child_inline_mapping(lines: list[str], top_block: str, child: str, indent: int = 2) -> dict[str, Any]:
    """Parse an existing `child: {...}` inline mapping (YAML flow mapping, as
    written by render_inline_mapping) back into a dict. Returns {}
    if the child is absent or its value isn't a parseable inline mapping —
    callers that only want to ADD/OVERRIDE specific keys without wiping out
    unrelated ones (e.g. torrent_storage_dir, content_layout) read this
    first, update() their own keys, then pass the merged dict to
    set_child_inline_mapping()."""
    start, end = find_child_block(lines, top_block, child, indent=indent)
    if start < 0:
        return {}
    text = " ".join(lines[start:end])
    m = re.match(rf"^\s*{re.escape(child)}\s*:\s*(\{{.*\}})\s*(?:#.*)?$", text)
    if not m:
        return {}
    return _leer_mapa_en_linea(m.group(1)[1:-1]) or {}


def set_child_inline_mapping(lines: list[str], top_block: str, child: str, mapping: dict[str, Any], indent: int = 2) -> str:
    top_start, top_end = find_top_block(lines, top_block)
    entry = " " * indent + f"{child}: {render_inline_mapping(mapping)}"
    if top_start < 0:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"{top_block}:", entry])
        return f"{top_block}.{child} creado"

    child_start, child_end = find_child_block(lines, top_block, child, indent=indent)
    if child_start < 0:
        lines.insert(top_start + 1, entry)
        return f"{top_block}.{child} creado"

    lines[child_start:child_end] = [entry]
    return f"{top_block}.{child} actualizado"


def get_emu_api_key(lines: list[str]) -> Optional[str]:
    start, end = find_child_block(lines, "TRACKERS", "EMU", indent=2)
    if start < 0:
        return None
    for line in lines[start + 1 : end]:
        m = re.match(r"^\s{4}api_key\s*:\s*(.*?)\s*(?:#.*)?$", line)
        if m:
            return clean_optional_secret(m.group(1))
    return None


def get_emu_anon(lines: list[str]) -> Optional[bool]:
    start, end = find_child_block(lines, "TRACKERS", "EMU", indent=2)
    if start < 0:
        return None
    for line in lines[start + 1 : end]:
        m = re.match(r"^\s{4}anon\s*:\s*(.*?)\s*(?:#.*)?$", line)
        if m:
            return m.group(1).strip().strip("\"'").lower() in {"true", "yes", "1", "si", "sí"}
    return None


def set_emu_config(lines: list[str], api_key: Optional[str] = None, anon: Optional[bool] = None) -> str:
    trackers_start, trackers_end = find_top_block(lines, "TRACKERS")
    if trackers_start < 0:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("TRACKERS:")
        trackers_start = len(lines) - 1

    emu_start, emu_end = find_child_block(lines, "TRACKERS", "EMU", indent=2)
    if emu_start < 0:
        insert_at = trackers_start + 1
        block = ["  EMU:"]
        if api_key is not None:
            block.append(f"    api_key: {yaml_scalar(api_key)}")
        block.append(f"    anon: {yaml_scalar(False if anon is None else anon)}")
        lines[insert_at:insert_at] = block
        return "TRACKERS.EMU creado"

    changed = False
    if api_key is not None:
        rendered = f"    api_key: {yaml_scalar(api_key)}"
        for i in range(emu_start + 1, emu_end):
            if re.match(r"^\s{4}api_key\s*:", lines[i]):
                lines[i] = rendered
                changed = True
                break
        if not changed:
            lines.insert(emu_start + 1, rendered)
            emu_end += 1
            changed = True

    if anon is not None:
        rendered = f"    anon: {yaml_scalar(anon)}"
        replaced = False
        for i in range(emu_start + 1, emu_end):
            if re.match(r"^\s{4}anon\s*:", lines[i]):
                lines[i] = rendered
                replaced = True
                break
        if not replaced:
            lines.insert(emu_start + 1, rendered)
        changed = True

    return "TRACKERS.EMU actualizado" if changed else "TRACKERS.EMU sin cambios"
