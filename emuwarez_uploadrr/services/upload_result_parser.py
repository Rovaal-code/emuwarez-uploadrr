"""Parse and classify Uploadrr stdout/stderr output.

Safety rules:
- Never invent URLs or torrent IDs not explicitly present in the text.
- Never expose secrets. Callers must redact before passing text.
- Does not write to DB; pure functions only.
"""
from __future__ import annotations

import re

# La línea fija que Uploadrr-EMU imprime al subir (src/trackers/UNIT3D.py): la ficha del torrent en eMuwarez.
TORRENT_URL_PATTERN = re.compile(r"^Torrent URL: (\S+)\s*$", re.MULTILINE)
TORRENT_ID_IN_URL = re.compile(r"/torrents/(\d+)")


def extract_torrent_url(text: str) -> str | None:
    """La URL de la línea `Torrent URL:`, o None. Cualquier otra URL de la salida (imágenes, TMDb, qui) no cuenta."""
    m = TORRENT_URL_PATTERN.search(text or "")
    return m.group(1) if m else None


def torrent_id_from_url(url: str | None) -> str | None:
    m = TORRENT_ID_IN_URL.search(url or "")
    return m.group(1) if m else None


# Marcos de las tablas de Rich. Una línea que solo los tiene es decoración.
_MARCO = "│┃┆╭╮╰╯─━┌┐└┘├┤┬┴┼═║╔╗╚╝┏┓┗┛"
_SOLO_MARCO = re.compile(rf"^[\s{_MARCO}]*$")
_TITULO_DE_PANEL = re.compile(rf"^[╭┏┌╔][{_MARCO}\s]*?[─━═]\s+(.+?)\s+[─━═][{_MARCO}\s]*[╮┓┐╗]$")
# RichHandler antepone el nivel y pospone el fichero ("ERROR    mensaje      UNIT3D.py:382").
_NIVEL_ERROR = re.compile(r"^(?:ERROR|CRITICAL)\s+(.*?)(?:\s+\S+\.py:\d+)?$")
_RESUMEN_DE_PANEL = re.compile(r"^(?:Processed \d+ Unique Uploads|Successful Uploads: \d+|Failed Uploads: \d+)$")

# Títulos de panel que no dicen nada: el resumen y el cierre genérico que acompaña a la causa real.
_TITULOS_SIN_MOTIVO = {"Upload Summary", "Pre-upload checks failed"}
# Lo que Uploadrr-EMU imprime al fallar: el rechazo del tracker y su detalle.
_MARCAS_DE_RECHAZO = ("Upload failed:", "Error details:")
_MARCAS_SUELTAS = ("Exact size match",)
_DESPEDIDA = "see you soon"
_MAX_MOTIVOS = 3


def _limpia(linea: str) -> str:
    """La línea sin el marco de la tabla de Rich que la rodee."""
    linea = linea.strip()
    if linea[:1] in _MARCO and linea[-1:] in _MARCO:
        linea = linea.strip(_MARCO + " ")
    return linea


def _es_relleno(linea: str) -> bool:
    return (
        not linea or _SOLO_MARCO.match(linea) is not None or _DESPEDIDA in linea
        or _RESUMEN_DE_PANEL.match(linea) is not None or linea in _TITULOS_SIN_MOTIVO
    )


def _motivos(lineas: list[str]) -> list[str]:
    """Las líneas que dicen por qué falló: el veredicto (rechazo del tracker, título de cada panel de «no subido»)
    manda y, sin él, valen las demás marcas de error."""
    veredicto: list[str] = []
    errores: list[str] = []
    for bruta in lineas:
        crudo = bruta.strip()
        titulo = _TITULO_DE_PANEL.match(crudo)
        if titulo:
            if titulo.group(1) not in _TITULOS_SIN_MOTIVO:
                veredicto.append(titulo.group(1))
            continue
        linea = _limpia(crudo)
        if _es_relleno(linea):
            continue
        if linea.startswith(_MARCAS_DE_RECHAZO):
            veredicto.append(linea)
            continue
        nivel = _NIVEL_ERROR.match(linea)
        if nivel and nivel.group(1):
            errores.append(nivel.group(1))
        elif linea.startswith(_MARCAS_SUELTAS):
            errores.append(linea)
    elegidos = veredicto or errores
    sin_repetir = list(dict.fromkeys(elegidos))
    return sin_repetir[-_MAX_MOTIVOS:]


def build_error_summary(stderr: str, stdout: str, exit_code: int | None) -> str | None:
    """El motivo del fallo. Uploadrr-EMU acaba siempre con el marco del último panel y «see you soon»: se buscan las
    líneas que sí lo dicen por sus marcas y, sin ninguna, las últimas que no sean decoración. Redacted text expected."""
    salida = [ln for ln in (stdout or "").splitlines() if ln.strip()]
    errores = [ln for ln in (stderr or "").splitlines() if ln.strip()]
    lines = _motivos(salida + errores)
    if not lines:
        if errores:
            lines = [ln.strip() for ln in errores[-3:]]
        else:
            utiles = [ln for ln in map(_limpia, salida) if not _es_relleno(ln)]
            lines = utiles[-2:]
    if exit_code is not None and exit_code != 0:
        lines.append(f"Exit code: {exit_code}")
    return "\n".join(lines) if lines else None


SEASON_PACK_PATTERN = re.compile(r"^Incomplete season pack: season (\d+|\?)(?:, missing episodes ([\d, ]+))?", re.MULTILINE)


def season_pack_warning(text: str) -> str | None:
    """Aviso en castellano si Uploadrr-EMU (mkbrr) vio un pack de temporada incompleto; None si no."""
    m = SEASON_PACK_PATTERN.search(text or "")
    if not m:
        return None
    aviso = f"Pack de temporada posiblemente incompleto (temporada {m.group(1)})"
    episodios = [e.strip() for e in (m.group(2) or "").split(",") if e.strip()]
    if len(episodios) == 1:
        aviso += f": falta el episodio {episodios[0]}"
    elif episodios:
        aviso += f": faltan los episodios {', '.join(episodios[:-1])} y {episodios[-1]}"
    return aviso + "."


def classify_upload_result(
    stdout: str,
    stderr: str,
    exit_code: int | None,
) -> dict:
    """Classify the result of an Uploadrr run.

    Returns:
        status: "completed" | "failed"
        result_url: str | None  (la línea `Torrent URL:`)
        torrent_id: str | None  (el id dentro de esa URL)
        error_summary: str | None
        exit_code: int | None
        season_pack_warning: str | None
    """
    result_url = extract_torrent_url(stdout)

    if exit_code == 0:
        status = "completed"
        error_summary = None
    else:
        status = "failed"
        error_summary = build_error_summary(stderr or "", stdout or "", exit_code)

    return {
        "status": status,
        "result_url": result_url,
        "torrent_id": torrent_id_from_url(result_url),
        "error_summary": error_summary,
        "exit_code": exit_code,
        "season_pack_warning": season_pack_warning(stdout or ""),
    }


__all__ = [
    "extract_torrent_url",
    "torrent_id_from_url",
    "build_error_summary",
    "classify_upload_result",
    "season_pack_warning",
]
