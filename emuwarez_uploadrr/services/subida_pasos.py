"""Los pasos con nombre de una subida, y desde cuál se puede reanudar un reintento.

Una subida pasa por cuatro pasos. Cada uno corresponde a una o varias fases
(`upload_jobs.stage`) que ya escribe el pipeline; este módulo solo les pone
nombre y decide en cuál estaba una subida y cuál toca rehacer.

    nomenclatura   comprobar el fichero y los requisitos, y poner el nombre de eMuwarez
    preparacion    pistas, título interno y enlace en la carpeta de subidas (lo caro)
    verificacion   comprobar de nuevo ya con el fichero final, y lanzar Uploadrr
    subida         Uploadrr-EMU: capturas, torrent, qBittorrent y el tracker

Un reintento crea siempre un trabajo nuevo. Si el anterior se paró cuando ya
había terminado la preparación de los ficheros, el nuevo puede reutilizarla
(upload_queue._motivo_no_reutilizable decide si sigue valiendo en disco) y lanza
Uploadrr-EMU con `--resume`, que reutiliza las capturas y el torrent que dejó
hechos. Si se paró antes, o se pide empezar de cero, rehace todo como siempre.

Dentro del paso `subida`, Uploadrr-EMU dice qué va terminando con una línea fija
por paso (`Step done: screenshots`, `Step done: torrent`) y la ficha del torrent
(`Torrent URL:`) cierra la subida al tracker. Es el contrato con Uploadrr-EMU:
se cambia en los dos repositorios a la vez.

No importa nada del paquete: lo usan la cola y la API.
"""
from __future__ import annotations

import json
import re
from typing import Optional

NOMENCLATURA = "nomenclatura"
PREPARACION = "preparacion"
VERIFICACION = "verificacion"
SUBIDA = "subida"

# (clave, nombre que ve el usuario, fases del pipeline que cubre), en orden.
PASOS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (NOMENCLATURA, "Comprobar y poner el nombre", ("nomenclature",)),
    (PREPARACION, "Preparar los ficheros", ("remux",)),
    (VERIFICACION, "Verificar antes de subir", ("verificacion_presubida", "preflight")),
    (SUBIDA, "Subir con Uploadrr", ("config_staging", "running", "finalizing")),
)

# Lo que Uploadrr-EMU va dando por hecho dentro del paso `subida`, en orden: (clave, nombre que ve el usuario).
# `screenshots` y `torrent` los dice él con `Step done: <clave>`; `tracker` es su línea `Torrent URL:`.
SUBPASOS: tuple[tuple[str, str], ...] = (
    ("screenshots", "Capturas"),
    ("torrent", "Torrent"),
    ("tracker", "Subida a eMuwarez"),
)
SUBPASOS_NOMBRES = dict(SUBPASOS)
# Los que un reintento puede reutilizar: el tracker no (volver a subir sería un duplicado).
SUBPASOS_REUTILIZABLES = ("screenshots", "torrent")

_LINEA_PASO_HECHO = re.compile(r"^Step done: (screenshots|torrent)\s*$")
_LINEA_FICHA = re.compile(r"^Torrent URL: \S+\s*$")

CLAVES = tuple(clave for clave, _n, _f in PASOS)
NOMBRES = {clave: nombre for clave, nombre, _f in PASOS}

# Estados de cada paso que enseña la interfaz.
HECHO, EN_CURSO, FALLIDO, CANCELADO, PENDIENTE = "hecho", "en_curso", "fallido", "cancelado", "pendiente"


def indice_de_fase(fase: Optional[str]) -> Optional[int]:
    """El paso (su posición en PASOS) al que pertenece una fase del pipeline, o None."""
    for i, (_c, _n, fases) in enumerate(PASOS):
        if fase in fases:
            return i
    return None


def subpaso_de_linea(linea: str) -> Optional[str]:
    """El subpaso (SUBPASOS) que una línea de la salida de Uploadrr-EMU da por terminado, o None."""
    linea = (linea or "").strip()
    m = _LINEA_PASO_HECHO.match(linea)
    if m:
        return m.group(1)
    return "tracker" if _LINEA_FICHA.match(linea) else None


def leer_subpasos(crudo: Optional[str]) -> list[str]:
    """Los subpasos hechos que guarda `upload_jobs.pasos_uploadrr_json`, en el orden de SUBPASOS; [] si no hay o está roto."""
    try:
        valor = json.loads(crudo or "[]")
    except ValueError:
        return []
    if not isinstance(valor, list):
        return []
    return [clave for clave, _n in SUBPASOS if clave in valor]


def subpasos_de_subida(status: Optional[str], crudo: Optional[str]) -> list[dict]:
    """Los subpasos de «Subir con Uploadrr» con su estado, o [] si no hay nada que enseñar.

    Una subida completada los tiene todos hechos (exit 0 solo si se subió algo). Las demás,
    los que Uploadrr-EMU dijo que terminó; sin ninguno apuntado (subidas de antes, o que
    no llegaron a lanzarlo) no se enseña nada."""
    hechos = [c for c, _n in SUBPASOS] if status == "completed" else leer_subpasos(crudo)
    if not hechos:
        return []
    return [{"clave": c, "nombre": n, "hecho": c in hechos} for c, n in SUBPASOS]


def subpasos_que_reutilizaria(status: Optional[str], etapa_parada: Optional[str], crudo: Optional[str]) -> list[str]:
    """Los nombres de lo que un reintento de esta subida no repetiría dentro de Uploadrr-EMU (capturas, torrent),
    o [] si el reintento no puede reanudar o no había nada hecho."""
    if reanudar_desde(status, etapa_parada) is None:
        return []
    hechos = leer_subpasos(crudo)
    # Con la ficha ya en eMuwarez no se reanuda nada: reintentar chocaría con el duplicado.
    if "tracker" in hechos:
        return []
    return [SUBPASOS_NOMBRES[c] for c in SUBPASOS_REUTILIZABLES if c in hechos]


def pasos_de_subida(status: Optional[str], stage: Optional[str], etapa_parada: Optional[str],
                    pasos_uploadrr: Optional[str] = None) -> list[dict]:
    """La lista de pasos con su estado, para enseñar en el detalle de una subida.

    - completada: todos hechos.
    - fallida o cancelada: los anteriores al paso donde se paró, hechos; ese, fallido o
      cancelado; el resto, pendientes. Si no se sabe dónde (subidas de antes de que se
      apuntara, o paradas antes de empezar) todos quedan pendientes.
    - en marcha: según la fase actual.
    """
    if status == "completed":
        posicion, estado_actual = len(PASOS), None
    elif status in ("failed", "cancelled"):
        i = indice_de_fase(etapa_parada)
        posicion, estado_actual = (i if i is not None else -1), (FALLIDO if status == "failed" else CANCELADO)
    # `ready` es el trabajo en la verificación previa: _populate_ready lo deja así justo antes de lanzar Uploadrr.
    elif status in ("ready", "staging", "preparing", "running"):
        i = indice_de_fase(stage)
        posicion, estado_actual = (i if i is not None else -1), EN_CURSO
    else:
        posicion, estado_actual = -1, None

    pasos = []
    for i, (clave, nombre, _f) in enumerate(PASOS):
        if i < posicion:
            estado = HECHO
        elif i == posicion and estado_actual:
            estado = estado_actual
        else:
            estado = PENDIENTE
        paso = {"clave": clave, "nombre": nombre, "estado": estado}
        if clave == SUBIDA:
            paso["subpasos"] = subpasos_de_subida(status, pasos_uploadrr)
        pasos.append(paso)
    return pasos


def reanudar_desde(status: Optional[str], etapa_parada: Optional[str]) -> Optional[str]:
    """Desde qué paso reintentaría una subida fallida o cancelada, o None si no se puede
    reanudar (volvería a empezar por el principio).

    Solo se reanuda si la preparación de los ficheros ya estaba hecha: la cosa cara que
    no merece repetirse. Desde ahí, el reintento arranca en la verificación previa.
    """
    if status not in ("failed", "cancelled"):
        return None
    i = indice_de_fase(etapa_parada)
    if i is not None and i > CLAVES.index(PREPARACION):
        return VERIFICACION
    return None


__all__ = [
    "PASOS", "CLAVES", "NOMBRES", "NOMENCLATURA", "PREPARACION", "VERIFICACION", "SUBIDA",
    "HECHO", "EN_CURSO", "FALLIDO", "CANCELADO", "PENDIENTE",
    "SUBPASOS", "SUBPASOS_NOMBRES", "SUBPASOS_REUTILIZABLES",
    "indice_de_fase", "pasos_de_subida", "reanudar_desde",
    "subpaso_de_linea", "leer_subpasos", "subpasos_de_subida", "subpasos_que_reutilizaria",
]
