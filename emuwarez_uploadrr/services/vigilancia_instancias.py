"""Sincroniza una instancia de Radarr/Sonarr en cuanto vuelve a responder.

Las instancias de subida se encienden solo para subir y están apagadas días: justo al encenderlas se quiere la
biblioteca al día, no dentro de media hora. Cada pocos minutos (tarea programada `vigilar-instancias`) se pregunta a
cada instancia activa lo mismo que la prueba de conexión (`/system/status`), con un plazo corto, y la sincronización
solo sale en el paso de «no respondía» a «responde».

El último estado de cada instancia vive en memoria y no en la base de datos, a propósito: tras reiniciar la aplicación
cada instancia es una primera mirada, que solo apunta cómo está. Guardado en `app_state`, un reinicio con una
instancia apagada la daría por «vuelta» al encenderla y no habría forma de distinguirlo de una caída real; y con
varias, el reinicio lanzaría una sincronización en cadena. Lo que se pierda en el reinicio lo recoge la tarea
periódica de sincronizar bibliotecas.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from ..integrations.arr_base import arr_request, join_api_path
from ..integrations.base import texto_de_error
from ..models import InstanceConfig
from .instances import list_instances
from .settings import leer_ajuste

logger = logging.getLogger("emuwarez.vigilancia")

# Cada comprobación es una llamada barata: si no contesta en esto, la instancia no responde.
PLAZO_COMPROBACION = 5
# Una instancia que se enciende y se apaga sin parar no sincroniza más de una vez en este tiempo.
ENFRIAMIENTO = timedelta(minutes=15)

# Id de instancia -> si respondía en la última mirada. Sin entrada: aún no se ha mirado.
_respondia: dict[int, bool] = {}
# Id de instancia -> cuándo se lanzó su última sincronización por haber vuelto.
_sincronizada: dict[int, datetime] = {}
# Id de instancia -> (si respondió, cuándo se miró) en la última mirada. Es lo que enseña el Panel, aparte de
# `_respondia`, que da por caída a la que respondía pero tenía otra sincronización en marcha.
_mirada: dict[int, tuple[bool, datetime]] = {}
# Una mirada más vieja que tres vueltas de la tarea ya no dice cómo está la instancia (tarea apagada o parada).
VIGENCIA_MIRADA_VUELTAS = 3


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _responde(instance: InstanceConfig) -> bool:
    """La misma llamada que la prueba de conexión de Radarr y Sonarr. Un fallo, sea cual sea (conexión rechazada,
    plazo, 5xx, clave mala), es que no responde."""
    try:
        arr_request("GET", join_api_path(instance.url, "system/status"), instance.api_key, timeout=PLAZO_COMPROBACION)
    except Exception:  # noqa: BLE001 — una URL mal formada tampoco responde y no puede cortar la vigilancia de las demás
        return False
    return True


def vigilar_instancias(conn: sqlite3.Connection) -> tuple[str, str]:
    """Mira cada instancia activa y sincroniza la que acaba de volver. Devuelve (estado, resumen) de la tarea."""
    from .library import SincronizacionParcial, SyncAlreadyRunning, sync_instance_con_candado

    if not leer_ajuste(conn, "sincronizar_al_volver_instancia"):
        return "skipped", "Desactivado en Configuración"
    instancias = list_instances(conn, enabled_only=True)
    # Una instancia que se desactiva o se borra y vuelve después empieza de cero: su primera mirada no sincroniza.
    for id_ in set(_respondia) - {i.id for i in instancias}:
        del _respondia[id_]
    for id_ in set(_mirada) - {i.id for i in instancias}:
        del _mirada[id_]

    sincronizadas: list[str] = []
    fallos: list[str] = []
    caidas = 0
    for instancia in instancias:
        responde = _responde(instancia)
        _mirada[instancia.id] = (responde, _ahora())
        habia_caido = _respondia.get(instancia.id) is False
        _respondia[instancia.id] = responde
        if not responde:
            caidas += 1
            continue
        if not habia_caido:
            continue
        ultima = _sincronizada.get(instancia.id)
        if ultima is not None and _ahora() - ultima < ENFRIAMIENTO:
            continue
        logger.info("%s «%s» vuelve a responder: se sincroniza", instancia.type.capitalize(), instancia.name)
        try:
            sync_instance_con_candado(conn, instancia.id)
        except SyncAlreadyRunning:
            # Con otra sincronización en marcha no se lanza otra; sigue como caída para volver a intentarlo.
            _respondia[instancia.id] = False
            continue
        except SincronizacionParcial:
            sincronizadas.append(instancia.name)  # lo demás sí se sincronizó
        except Exception as exc:  # noqa: BLE001 — se cuenta en el resumen; la tarea periódica lo reintenta
            fallos.append(f"{instancia.name}: {texto_de_error(exc, instancia.api_key)}")
            logger.warning("No se pudo sincronizar «%s» al volver: %s", instancia.name,
                           texto_de_error(exc, instancia.api_key))
        else:
            sincronizadas.append(instancia.name)
        _sincronizada[instancia.id] = _ahora()

    n = len(instancias)
    resumen = f"{n} {'instancia comprobada' if n == 1 else 'instancias comprobadas'}, {caidas} sin responder"
    if sincronizadas:
        resumen += "; sincronizada al volver: " + ", ".join(sincronizadas)
    if fallos:
        return "failed", resumen + "; error: " + "; ".join(fallos)
    return "completed", resumen


def instancias_caidas(conn: sqlite3.Connection) -> list[dict]:
    """Las instancias activas que no respondían en la última mirada de la vigilancia, con cuándo se sincronizó por
    última vez su biblioteca. Solo cuenta lo visto hace poco: sin vigilancia (apagada en Configuración, o la tarea
    parada) no se sabe cómo están y no se afirma nada."""
    if not leer_ajuste(conn, "sincronizar_al_volver_instancia"):
        return []
    from .scheduler import TASK_INSTANCE_WATCH, get_scheduled_task
    tarea = get_scheduled_task(conn, TASK_INSTANCE_WATCH)
    if not tarea["enabled"]:
        return []
    vigencia = timedelta(minutes=tarea["interval_minutes"] * VIGENCIA_MIRADA_VUELTAS)
    caidas = []
    for instancia in list_instances(conn, enabled_only=True):
        mirada = _mirada.get(instancia.id)
        if mirada is None or mirada[0] or _ahora() - mirada[1] > vigencia:
            continue
        visto = conn.execute(
            "SELECT MAX(last_seen_at) AS ultima FROM library_items WHERE instance_id = ?", (instancia.id,),
        ).fetchone()
        caidas.append({
            "id": instancia.id, "nombre": instancia.name, "tipo": instancia.type,
            "ultima_sincronizacion": visto["ultima"],
        })
    return caidas
