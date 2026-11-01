"""El vocabulario de estados de una subida, y la única forma de escribirlo.

Antes esto eran literales sueltos dentro de consultas, repetidos por
`upload_queue.py` y `upload_execution.py`, y cinco funciones distintas
escribían `upload_jobs.status` **cada una con su propia política de guardia**
(auditoría, hallazgo 4.1). Tres de esas políticas eran distintas entre sí y una
no existía, y de ahí salió un fallo real: cancelar una subida y que fallara
algo justo después la dejaba en "Fallido", con su aviso de subida fallida
incluido, así que el usuario no veía lo que había hecho.

La idea aquí es que "¿puedo pisar el estado de este trabajo?" se conteste **una
vez**: `escribir_estado()` recibe la guardia declarada por quien llama, y esa
guardia viaja DENTRO del UPDATE. Quien llama declara qué respeta; no
reimplementa cómo se comprueba.

Este módulo casi no importa nada de `services/` a propósito: lo usan los dos
lados del pipeline y tiene que poder estar debajo de ambos. La excepción es
`eventos`, que no importa nada del paquete y por tanto está debajo de todo.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from ..database import connect
from .eventos import EVENTO_SUBIDA_ESTADO, publicar

# Los estados que la interfaz enseña como una subida de verdad.
VISIBLE_STATUSES: frozenset[str] = frozenset({
    "queued", "staging", "preparing", "running", "completed", "failed", "cancelled",
})

# Estados preparatorios: existieron antes de que un trabajo solo naciera al
# pulsar Subir, y quedan filas antiguas con ellos. El frontend los esconde
# (UploadsPage.HIDDEN_STATES).
PREPARATORY_STATUSES: frozenset[str] = frozenset({
    "draft", "preflight", "blocked", "ready", "config_staging",
})

# Todos. OJO: esta lista es documentación, no una barrera. Las guardias se
# escriben con `salvo=`, en negativo, precisamente para que un estado que no
# esté aquí no se quede fuera en silencio — pasó al escribir este módulo:
# faltaba "ready" y las subidas dejaron de completarse.
ALL_STATUSES: frozenset[str] = VISIBLE_STATUSES | PREPARATORY_STATUSES

# Terminados: ya no se mueven solos.
TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})

# En marcha. Con uno de estos vivo no se crea otro trabajo para lo mismo.
ACTIVE_JOB_STATUSES: frozenset[str] = frozenset({"queued", "staging", "preparing", "running"})

# Lo que la interfaz ofrece hacer. Son predicciones de lo que el backend
# aceptará, así que el frontend tiene su copia y un test la vigila
# (tests/test_copias_frontend.py).
CANCELLABLE_STATUSES: frozenset[str] = ACTIVE_JOB_STATUSES
RETRYABLE_STATUSES: frozenset[str] = frozenset({"failed", "cancelled"})
# 'completed' entra: borrar el registro de una subida que salió bien no deshace
# nada, el torrent ya está en eMuwarez y el archivo sigue en su sitio.
DELETABLE_STATUSES: frozenset[str] = TERMINAL_STATUSES





# Las fases en que puede pararse una subida y que cuentan como «el paso que falló»
# (ver subida_pasos.py). Una subida que se cancela o falla estando en otra (en
# cola, ya terminada) no tiene paso al que volver.
ETAPAS_DE_PARADA: tuple[str, ...] = (
    "nomenclature", "remux", "verificacion_presubida", "preflight", "config_staging", "running", "finalizing")


def asignacion_etapa_parada() -> tuple[str, list[str]]:
    """El trozo de UPDATE que apunta dónde se paró una subida: la fase que tenía antes del UPDATE
    (en SQLite la parte derecha lee la fila antigua), sin pisar la ya apuntada. Con sus parámetros."""
    marcas = ",".join("?" * len(ETAPAS_DE_PARADA))
    return (f"etapa_parada = COALESCE(etapa_parada, CASE WHEN stage IN ({marcas}) THEN stage END)",
            list(ETAPAS_DE_PARADA))


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def escribir_estado(
    job_id: int,
    *,
    desde: Optional[Iterable[str]] = None,
    salvo: Iterable[str] = (),
    status: Optional[str] = None,
    stage: Optional[str] = None,
    conn=None,
    **extra,
) -> bool:
    """Escribe estado y/o fase, con la guardia declarada por quien llama.

    `salvo` es la forma normal: "escribe salvo si está cancelado". Se expresa
    en negativo a propósito, porque una lista blanca deja fuera cualquier
    estado que no esté enumerado y eso falla en silencio (al escribir este
    módulo faltaba "ready" y las subidas dejaron de completarse).

    `desde` es la lista blanca, para el único caso que de verdad la quiere:
    avanzar la subfase mientras el trabajo siga en 'staging'.

    Devuelve True si escribió. False significa que el trabajo estaba en un
    estado no permitido — casi siempre porque el usuario lo canceló mientras
    esto trabajaba, y entonces quien llama debe parar, no insistir.

    La comprobación va DENTRO del UPDATE, no como un SELECT previo: hay
    concurrencia real (el subproceso por un lado, el SIGTERM del cancelar por
    otro, dos conexiones sobre la misma fila) y un leer-luego-escribir deja una
    ventana por la que se cuela justo lo que se quiere evitar. SQLite serializa
    los escritores, así que este UPDATE cae entero antes o después del otro,
    nunca entremedias.
    """
    assert desde is not None or salvo is not None, "hay que declarar la guardia"
    campos: dict[str, object] = {"updated_at": _ahora(), **extra}
    if status is not None:
        campos["status"] = status
    if stage is not None:
        campos["stage"] = stage

    propia = conn is None
    conn = conn or connect()
    try:
        asignaciones = ", ".join(f"{k} = ?" for k in campos)
        if status in ("failed", "cancelled"):
            # Dónde se paró (sin pisar la ya apuntada si falla dos veces seguidas).
            trozo, parametros_parada = asignacion_etapa_parada()
            asignaciones += ", " + trozo
        else:
            parametros_parada = []
        if desde is not None:
            estados = sorted(set(desde))
            condicion = f" AND status IN ({','.join('?' * len(estados))})"
        else:
            estados = sorted(set(salvo))
            condicion = (f" AND status NOT IN ({','.join('?' * len(estados))})"
                         if estados else "")
        cur = conn.execute(
            f"UPDATE upload_jobs SET {asignaciones} WHERE id = ?{condicion}",
            [*campos.values(), *parametros_parada, job_id, *estados],
        )
        conn.commit()
        escribio = cur.rowcount > 0
    finally:
        if propia:
            conn.close()

    # Solo si SE ESCRIBIÓ: cuando la guardia rechaza el cambio no ha pasado
    # nada que contar, y avisar haría recargar a la interfaz para enseñar
    # exactamente lo mismo. Este es el único sitio desde el que se escribe el
    # estado de una subida, así que basta con ponerlo aquí.
    if escribio:
        publicar(EVENTO_SUBIDA_ESTADO, {"job_id": job_id, "status": status, "stage": stage})
    return escribio


__all__ = [
    "ALL_STATUSES", "VISIBLE_STATUSES", "PREPARATORY_STATUSES", "TERMINAL_STATUSES",
    "ACTIVE_JOB_STATUSES", "CANCELLABLE_STATUSES", "RETRYABLE_STATUSES",
    "DELETABLE_STATUSES", "ETAPAS_DE_PARADA", "asignacion_etapa_parada", "escribir_estado",
]
