"""Subprocesos de Uploadrr-EMU en marcha: registro, señales y parada ordenada."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading


# Los Uploadrr en marcha de ESTE proceso, por trabajo: Cancelar los señala.
_PROCESOS: dict[int, subprocess.Popen] = {}
_PROCESOS_LOCK = threading.Lock()
# True una vez que la aplicación se apaga: no se admiten procesos nuevos. Otros módulos la leen como procesos._apagando.
_apagando = False
# Segundos entre SIGTERM y SIGKILL.
_GRACIA_SIGKILL = 10


def _senalar_grupo(proc: subprocess.Popen, sig: int) -> bool:
    """Manda la señal al grupo del proceso (start_new_session hace pgid == pid)."""
    try:
        os.killpg(proc.pid, sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _detener_proceso(proc: subprocess.Popen) -> bool:
    """SIGTERM al grupo y, si Uploadrr sigue vivo pasado el plazo, SIGKILL.
    Sin bloquear: lo usa Cancelar, que responde a una petición web."""
    enviada = _senalar_grupo(proc, signal.SIGTERM)
    if enviada:
        def _rematar() -> None:
            if proc.poll() is None:
                _senalar_grupo(proc, signal.SIGKILL)
        timer = threading.Timer(_GRACIA_SIGKILL, _rematar)
        timer.daemon = True
        timer.start()
    return enviada


def detener_procesos_en_marcha() -> None:
    """Al apagar el servidor: Uploadrr va en su propia sesión y ya no cae con él.
    Desde aquí no se lanza ninguno más."""
    global _apagando
    with _PROCESOS_LOCK:
        _apagando = True
        procesos = list(_PROCESOS.values())
    for proc in procesos:
        _detener_proceso(proc)


def _pid_es_de_este_job(pid: int, job: dict) -> bool:
    """El PID guardado es de otro proceso si Uploadrr ya terminó (los PID se
    reutilizan): solo se señala si su línea de comandos es la de este job."""
    try:
        import psutil
        cmdline = psutil.Process(pid).cmdline()
        ruta = json.loads(job.get("safe_command_json") or "{}").get("source_path")
    except Exception:  # sin psutil (CLI sin extras), proceso ya muerto o JSON ilegible
        return False
    return bool(ruta) and ruta in cmdline and any(a.endswith("upload.py") for a in cmdline)


def _terminar_y_esperar(proc: subprocess.Popen) -> int:
    """Lo mismo pero esperando: devuelve el código de salida (-1 si no sale)."""
    _senalar_grupo(proc, signal.SIGTERM)
    try:
        return proc.wait(timeout=_GRACIA_SIGKILL)
    except subprocess.TimeoutExpired:
        _senalar_grupo(proc, signal.SIGKILL)
    try:
        return proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return -1
