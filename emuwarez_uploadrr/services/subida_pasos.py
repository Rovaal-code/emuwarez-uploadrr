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
(upload_queue._preparacion_reutilizable decide si sigue valiendo en disco). Si
se paró antes, o se pide empezar de cero, rehace todo como siempre.

No importa nada del paquete: lo usan la cola y la API.
"""
from __future__ import annotations

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


def pasos_de_subida(status: Optional[str], stage: Optional[str], etapa_parada: Optional[str]) -> list[dict]:
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
        pasos.append({"clave": clave, "nombre": nombre, "estado": estado})
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
    "indice_de_fase", "pasos_de_subida", "reanudar_desde",
]
