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

import ast
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


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    value = str(value)
    return "'" + value.replace("'", "''") + "'"


def python_literal_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    return repr(str(value))


def render_inline_mapping(mapping: dict[str, Any]) -> str:
    return "{" + ", ".join(f"{repr(k)}: {python_literal_scalar(v)}" for k, v in mapping.items()) + "}"


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
    """Parse an existing `child: {...}` inline mapping (Python-literal dict
    syntax, as written by render_inline_mapping) back into a dict. Returns {}
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
    try:
        value = ast.literal_eval(m.group(1))
    except (ValueError, SyntaxError):
        return {}
    return value if isinstance(value, dict) else {}


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
