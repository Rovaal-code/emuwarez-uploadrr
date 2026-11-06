"""Plazas de «Subidas en paralelo» compartidas entre procesos (el servidor y el CLI).

Cada plaza es un fichero `plaza-N` en `<CONFIG_DIR>/plazas/` con un `flock` exclusivo mientras alguien la usa. El
núcleo suelta el `flock` cuando el proceso muere (aunque sea con kill -9), así que una plaza no se queda ocupada
por un proceso que ya no existe: no hay PIDs ni latidos que limpiar. Contar las ocupadas es probar cada fichero
sin esperar; el mutex `mutex` hace que contar y tomar sea un solo paso entre procesos (si no, dos podrían ver una
plaza libre a la vez). Solo se mantiene el mutex lo que dura el recorrido.

Aquí no hay cola ni orden: el turno entre las subidas de un mismo proceso lo reparte `concurrencia.py`; entre
procesos gana quien llega primero a una plaza libre en su siguiente vuelta.

Sin `fcntl` (Windows) o si el directorio no se puede usar, `tomar` da una plaza sin fichero y se cuenta solo
dentro del proceso, que es lo que había antes."""
from __future__ import annotations

import os
import time

from ...database import db_path
from .comun import logger

try:
    import fcntl
except ImportError:  # Windows: solo hay límite dentro del proceso
    fcntl = None  # type: ignore[assignment]

# Plazas que se miran. Un lote encola 50 como mucho y el límite máximo es 10; con «sin límite» sobran.
MAX_PLAZAS = 64
# Cuánto se espera al mutex antes de dejarlo para la vuelta siguiente (otro proceso lo tiene un instante).
_ESPERA_MUTEX = 2.0


class Plaza:
    """Una plaza tomada. `fd` es None cuando no hay cerrojo en fichero (solo cuenta el proceso)."""
    __slots__ = ("_fd",)

    def __init__(self, fd: int | None) -> None:
        self._fd = fd

    @property
    def compartida(self) -> bool:
        return self._fd is not None

    def soltar(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            # LOCK_UN suelta el cerrojo aunque un proceso hijo (fork) tenga duplicado el descriptor.
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass

    def __del__(self) -> None:
        self.soltar()


def _abrir(ruta) -> int:
    fd = os.open(ruta, os.O_RDWR | os.O_CREAT, 0o666)
    try:
        os.fchmod(fd, 0o666)  # que el CLI y el servidor, si corren con usuarios distintos, abran el mismo fichero
    except OSError:
        pass
    return fd


def _cerrar(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    os.close(fd)


def _tomar_mutex(ruta) -> int | None:
    fd = _abrir(ruta)
    limite = time.monotonic() + _ESPERA_MUTEX
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if time.monotonic() >= limite:
                os.close(fd)
                return None
            time.sleep(0.005)
        except OSError:
            os.close(fd)
            raise


def _recorrer(directorio, limite: int) -> tuple[Plaza | None, int]:
    libre: int | None = None
    ocupadas = 0
    try:
        for i in range(MAX_PLAZAS):
            fd = _abrir(directorio / f"plaza-{i}")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                ocupadas += 1
                if limite and ocupadas >= limite:
                    break  # llena: no hace falta seguir contando
                continue
            except OSError:
                os.close(fd)
                raise
            if libre is None:
                libre = fd
                if not limite:
                    break  # sin límite basta la primera libre
            else:
                _cerrar(fd)
    except BaseException:
        # Un fallo a medio recorrido (permisos, EMFILE, ENOSPC) no deja la plaza ya tomada con el cerrojo sin dueño.
        if libre is not None:
            _cerrar(libre)
        raise
    if libre is not None and (not limite or ocupadas < limite):
        return Plaza(libre), ocupadas
    if libre is not None:
        _cerrar(libre)
    if not limite:
        # Sin límite y ninguna de las MAX_PLAZAS libre: se deja pasar sin plaza en fichero.
        logger.warning("Todas las plazas compartidas están ocupadas; esta subida no se cuenta entre procesos")
        return Plaza(None), ocupadas
    return None, ocupadas


def tomar(limite: int) -> tuple[Plaza | None, int]:
    """Toma una plaza si hay menos de `limite` ocupadas en toda la máquina (0 = sin límite).
    Devuelve (plaza, ocupadas vistas); la plaza es None si está lleno o el mutex estaba cogido. No lanza: si el
    cerrojo en fichero no sirve, da una plaza sin fichero y el límite vale solo dentro del proceso."""
    if fcntl is None:
        return Plaza(None), 0
    try:
        directorio = db_path().parent / "plazas"
        directorio.mkdir(parents=True, exist_ok=True)
        mutex = _tomar_mutex(directorio / "mutex")
        if mutex is None:
            return None, 0
        try:
            return _recorrer(directorio, limite)
        finally:
            _cerrar(mutex)
    except Exception:
        logger.warning("No se pudo usar el cerrojo entre procesos; el límite de subidas vale solo en este proceso",
                       exc_info=True)
        return Plaza(None), 0
