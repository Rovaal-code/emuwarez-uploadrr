"""Límite de "Subidas en paralelo": la puerta que reparte plazas entre los trabajos."""
from __future__ import annotations

import threading
import time
from typing import Callable

from ...database import get_setting_canonical
from ..ajustes_registro import (
    UPLOAD_MAX_CONCURRENT_CHOICES,
    UPLOAD_MAX_CONCURRENT_DEFAULT,
    UPLOAD_MAX_CONCURRENT_SETTING_KEY,
)
from ..eventos import EVENTO_SUBIDA_ESTADO, publicar
from .comun import _get_db_conn, logger
from .registro import append_upload_log


# "Subidas en paralelo" (Configuración → Otros): caps how many jobs run their
# actual Uploadrr-EMU subprocess at once — hashing the torrent, generating
# and uploading screenshots, transferring to eMuwarez, the genuinely CPU/
# network-heavy tail — regardless of which entry point queued them (the
# normal "Subir a eMuwarez" flow, a retry, or the legacy direct-start
# endpoints). El trabajo encolado toma la plaza antes de preparar los ficheros
# (upload_queue._run_queued_job) y la pasa al subproceso. 0 = sin límite.
# La clave (UPLOAD_MAX_CONCURRENT_SETTING_KEY), los valores que admite y el de
# por defecto viven en el registro de ajustes (services/ajustes_registro.py).


def get_upload_max_concurrent(conn=None) -> int:
    own = conn is None
    conn = conn or _get_db_conn()
    try:
        raw = get_setting_canonical(conn, UPLOAD_MAX_CONCURRENT_SETTING_KEY)
    finally:
        if own:
            conn.close()
    try:
        val = int(raw) if raw else UPLOAD_MAX_CONCURRENT_DEFAULT
    except (TypeError, ValueError):
        return UPLOAD_MAX_CONCURRENT_DEFAULT
    return val if val in UPLOAD_MAX_CONCURRENT_CHOICES else UPLOAD_MAX_CONCURRENT_DEFAULT


def _limite_de_subidas() -> int:
    try:
        return get_upload_max_concurrent()
    except Exception:
        logger.warning("No se pudo leer %s; se usa %s", UPLOAD_MAX_CONCURRENT_SETTING_KEY,
                       UPLOAD_MAX_CONCURRENT_DEFAULT, exc_info=True)
        return UPLOAD_MAX_CONCURRENT_DEFAULT


class _UploadConcurrencyGate:
    """Re-reads the configured limit on every wait loop instead of capturing
    it once at acquire time — so lowering/raising the setting takes effect
    immediately for whichever job is next in line, with no need to touch
    jobs already past the gate and no need to block changing the setting
    while uploads are running: shrinking the limit just makes new jobs wait
    longer, it never kills or pauses one already running.

    Admission order is by job_id ascending (== creation order), never by
    whichever waiting thread happens to wake up first from notify_all() —
    threading.Condition doesn't guarantee FIFO wakeup order, and the UI's
    puesto en la cola (posiciones(), also ordered by id) would otherwise
    sometimes lie about which job starts next.

    Una subida en espera se puede retirar (Cancelar en «En cola»): deja la cola
    al momento y acquire() devuelve False, sin ocupar plaza."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._active = 0
        self._waiting: set[int] = set()
        self._retirados: set[int] = set()
        self._liberaciones = 0
        # El límite leído hace menos de un segundo (valor, cuándo). Con muchas subidas en espera (un lote)
        # cada vuelta de cada hilo abría una conexión para leer el ajuste, y cada liberación los despierta a
        # todos. Se olvida cuando la cola se vacía: un cambio del ajuste se nota como mucho un segundo tarde.
        self._limite_leido: tuple[int, float] | None = None

    def _limite(self) -> int:
        with self._cond:
            leido = self._limite_leido
        if leido is not None and time.monotonic() - leido[1] < 1.0:
            return leido[0]
        limite = _limite_de_subidas()
        with self._cond:
            self._limite_leido = (limite, time.monotonic())
        return limite

    def acquire(self, job_id: int, *, cancelada: Callable[[], bool] | None = None) -> bool:
        """True con la plaza tomada; False si se retiró mientras esperaba.
        `cancelada` se consulta en cada vuelta de la espera: así una
        cancelación escrita desde otro proceso (el CLI) también la saca.
        No lanza: corre antes del try de quien llama, y un fallo aquí dejaba
        el job en cola para siempre. La base se consulta fuera del candado."""
        with self._cond:
            if job_id in self._retirados:
                self._retirados.discard(job_id)
                return False
            self._waiting.add(job_id)
        announced = False
        try:
            while True:
                if cancelada is not None and _sin_fallos(cancelada):
                    return False
                limit = self._limite()
                with self._cond:
                    if job_id in self._retirados:
                        self._retirados.discard(job_id)
                        return False
                    is_next = job_id == min(self._waiting - self._retirados)
                    if limit == 0 or (self._active < limit and is_next):
                        self._waiting.discard(job_id)
                        self._active += 1
                        return True
                    activas, vistas = self._active, self._liberaciones
                if not announced:
                    announced = True
                    # Ahora sí espera de verdad: la interfaz pasa a enseñar su puesto.
                    publicar(EVENTO_SUBIDA_ESTADO, {"job_id": job_id, "status": "queued", "stage": "queued"})
                    try:
                        append_upload_log(
                            job_id, "info",
                            f"Esperando turno para empezar la subida real: {activas} en curso, límite {limit}.",
                            stream="system",
                        )
                    except Exception:
                        logger.warning("Subida %s: no se pudo registrar la espera de turno", job_id, exc_info=True)
                with self._cond:
                    if self._liberaciones == vistas:
                        self._cond.wait(timeout=3)
        finally:
            with self._cond:
                self._waiting.discard(job_id)
                if not self._waiting:
                    self._limite_leido = None
                # Una retirada que llegó mientras esperaba ya no hace falta,
                # salga como salga (con plaza, retirada o por `cancelada`).
                self._retirados.discard(job_id)
                # Los de detrás suben un puesto: que lo vean ya, sin esperar al siguiente ciclo.
                self._liberaciones += 1
                self._cond.notify_all()
            if announced:
                publicar(EVENTO_SUBIDA_ESTADO, {"job_id": job_id})

    def release(self) -> None:
        with self._cond:
            self._active = max(0, self._active - 1)
            self._liberaciones += 1
            self._cond.notify_all()

    def retirar_si_espera(self, job_id: int) -> None:
        """Como retirar(), pero solo si ya está esperando: quien aún no ha
        llegado a la puerta lo para su `cancelada` al llegar, y así no queda
        una retirada apuntada que nadie recoja."""
        with self._cond:
            if job_id in self._waiting:
                self._retirados.add(job_id)
                self._liberaciones += 1
                self._cond.notify_all()

    def retirar(self, job_id: int) -> None:
        """Saca de la cola una subida cancelada. Si su hilo aún no ha llegado
        a la puerta, al llegar se va sin esperar."""
        with self._cond:
            self._retirados.add(job_id)
            self._liberaciones += 1
            self._cond.notify_all()

    def olvidar(self, job_id: int) -> None:
        """Lo llama el hilo de la subida al terminar: una retirada que llegó
        cuando ya tenía plaza no se queda apuntada para siempre."""
        with self._cond:
            self._retirados.discard(job_id)

    def posiciones(self) -> dict[int, tuple[int, int]]:
        """Puesto (desde 1) y total de cada subida que espera plaza, por id."""
        with self._cond:
            en_cola = sorted(self._waiting - self._retirados)
        return {jid: (i + 1, len(en_cola)) for i, jid in enumerate(en_cola)}


_upload_concurrency_gate = _UploadConcurrencyGate()


def _sin_fallos(pregunta: Callable[[], bool]) -> bool:
    try:
        return bool(pregunta())
    except Exception:
        logger.warning("No se pudo comprobar si la subida se canceló", exc_info=True)
        return False
