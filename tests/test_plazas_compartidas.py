"""Límite de «Subidas en paralelo» compartido entre procesos (el servidor y el CLI): las plazas son cerrojos de
fichero (services/upload_execution/plazas_compartidas.py) y la puerta de concurrencia.py las toma además de
contar sus hilos. Los «otros procesos» son subprocesos de verdad: la muerte de uno con plaza tomada es lo que
hay que ver."""
from __future__ import annotations

import os
import select
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from emuwarez_uploadrr.services.upload_execution import concurrencia, plazas_compartidas
from emuwarez_uploadrr.services.upload_execution.concurrencia import _UploadConcurrencyGate

RAIZ = Path(__file__).resolve().parents[1]

# Un «proceso» que toma una plaza (directa o por la puerta), avisa y la tiene hasta que se le cierra la entrada.
_HIJO_PLAZA = """
import sys
from emuwarez_uploadrr.services.upload_execution import plazas_compartidas as p
plaza, ocupadas = p.tomar(int(sys.argv[1]))
print("TOMADA" if plaza is not None else "LLENO", ocupadas, flush=True)
if plaza is not None:
    sys.stdin.readline()
"""
_HIJO_PUERTA = """
import sys
from unittest.mock import patch
from emuwarez_uploadrr.services.upload_execution import concurrencia
limite = int(sys.argv[1])
with patch.object(concurrencia, "get_upload_max_concurrent", return_value=limite), \\
        patch.object(concurrencia, "append_upload_log"):
    puerta = concurrencia._UploadConcurrencyGate()
    ok = puerta.acquire(int(sys.argv[2]))
    print("TOMADA" if ok else "NO", flush=True)
    sys.stdin.readline()
"""


class Hijo:
    def __init__(self, codigo: str, tmp_path, *args):
        entorno = {**os.environ, "CONFIG_DIR": str(tmp_path), "PYTHONPATH": str(RAIZ)}
        self.proc = subprocess.Popen(
            [sys.executable, "-c", codigo, *map(str, args)], env=entorno, cwd=str(RAIZ),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )

    def linea(self, timeout: float = 60.0) -> str:
        listo, _, _ = select.select([self.proc.stdout], [], [], timeout)
        assert listo, "el proceso hijo no contestó a tiempo"
        return self.proc.stdout.readline().strip()

    def matar(self) -> None:
        self.proc.kill()
        self.proc.wait(timeout=10)

    def terminar(self) -> None:
        if self.proc.poll() is None:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        self.proc.stdout.close()


@pytest.fixture
def hijos():
    lista: list[Hijo] = []

    def _crear(*a, **k) -> Hijo:
        h = Hijo(*a, **k)
        lista.append(h)
        return h

    yield _crear
    for h in lista:
        h.terminar()


@pytest.fixture(autouse=True)
def _sin_registro_de_espera():
    # La espera apunta en el registro del job; aquí no hay jobs.
    with patch.object(concurrencia, "append_upload_log"):
        yield


def _esperar(condicion, timeout=10.0) -> bool:
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return condicion()


# ---------------------------------------------------------------------------
# Las plazas, sin puerta
# ---------------------------------------------------------------------------

def test_el_limite_cuenta_las_plazas_tomadas():
    a, _ = plazas_compartidas.tomar(2)
    b, _ = plazas_compartidas.tomar(2)
    c, vistas = plazas_compartidas.tomar(2)
    assert a is not None and b is not None and c is None and vistas == 2
    a.soltar()
    d, _ = plazas_compartidas.tomar(2)
    assert d is not None
    b.soltar()
    d.soltar()


def test_limite_cero_es_sin_limite():
    plazas = [plazas_compartidas.tomar(0)[0] for _ in range(12)]
    assert all(p is not None and p.compartida for p in plazas)
    for p in plazas:
        p.soltar()


def test_cambio_de_limite_en_caliente_cuenta_las_que_ya_hay():
    tres = [plazas_compartidas.tomar(3)[0] for _ in range(3)]
    # Bajar el límite no echa a nadie, pero nadie nuevo entra hasta que haya menos de las que dice.
    assert plazas_compartidas.tomar(1)[0] is None
    assert plazas_compartidas.tomar(2)[0] is None
    tres[1].soltar()
    assert plazas_compartidas.tomar(2)[0] is None  # quedan 2 ocupadas (la 0 y la 2)
    tres[0].soltar()
    uno = plazas_compartidas.tomar(2)[0]  # queda 1 ocupada: con límite 2 cabe otra
    assert uno is not None
    # Subir el límite deja entrar al momento.
    assert plazas_compartidas.tomar(0)[0] is not None
    tres[2].soltar()
    uno.soltar()


def test_soltar_dos_veces_no_falla():
    p, _ = plazas_compartidas.tomar(1)
    p.soltar()
    p.soltar()
    q, _ = plazas_compartidas.tomar(1)
    assert q is not None
    q.soltar()


def test_una_plaza_olvidada_se_suelta_sola():
    """Si el dueño la pierde de vista (excepción, test), el descriptor se cierra y la plaza queda libre."""
    p, _ = plazas_compartidas.tomar(1)
    assert p is not None
    del p
    q, _ = plazas_compartidas.tomar(1)
    assert q is not None
    q.soltar()


def test_sin_cerrojo_de_fichero_vale_el_limite_del_proceso(monkeypatch, caplog):
    def sin_permiso(*a, **k):
        raise PermissionError("no")

    monkeypatch.setattr(plazas_compartidas.os, "open", sin_permiso)
    plaza, _ = plazas_compartidas.tomar(1)
    assert plaza is not None and not plaza.compartida
    plaza.soltar()
    assert "No se pudo usar el cerrojo" in caplog.text


def test_sin_fcntl_no_hay_cerrojo(monkeypatch):
    monkeypatch.setattr(plazas_compartidas, "fcntl", None)
    plaza, _ = plazas_compartidas.tomar(1)
    assert plaza is not None and not plaza.compartida


# ---------------------------------------------------------------------------
# Dos procesos contra el mismo límite
# ---------------------------------------------------------------------------

def test_dos_procesos_comparten_el_limite(tmp_path, hijos):
    uno = hijos(_HIJO_PLAZA, tmp_path, 1)
    assert uno.linea().startswith("TOMADA")
    # Otro proceso ve la plaza ocupada...
    otro = hijos(_HIJO_PLAZA, tmp_path, 1)
    assert otro.linea() == "LLENO 1"
    # ...y este también.
    assert plazas_compartidas.tomar(1)[0] is None
    # Con límite 2 sí cabe.
    plaza, vistas = plazas_compartidas.tomar(2)
    assert plaza is not None and vistas == 1
    plaza.soltar()
    # Cuando el primero termina limpiamente, la plaza queda libre.
    uno.terminar()
    plaza, _ = plazas_compartidas.tomar(1)
    assert plaza is not None
    plaza.soltar()


def test_un_proceso_muerto_con_plaza_la_suelta_solo(tmp_path, hijos):
    uno = hijos(_HIJO_PLAZA, tmp_path, 1)
    assert uno.linea().startswith("TOMADA")
    assert plazas_compartidas.tomar(1)[0] is None
    uno.matar()  # kill -9: no ejecuta nada de limpieza
    plaza, vistas = plazas_compartidas.tomar(1)
    assert plaza is not None and vistas == 0
    plaza.soltar()


def test_limite_cero_no_cuenta_a_los_otros_procesos(tmp_path, hijos):
    uno = hijos(_HIJO_PLAZA, tmp_path, 1)
    assert uno.linea().startswith("TOMADA")
    otro = hijos(_HIJO_PLAZA, tmp_path, 0)
    assert otro.linea().startswith("TOMADA")
    plaza, _ = plazas_compartidas.tomar(0)
    assert plaza is not None
    plaza.soltar()


def test_la_puerta_de_un_proceso_cuenta_contra_otro(tmp_path, hijos):
    """Un proceso (el CLI) sube con la plaza tomada: la puerta de este espera y entra cuando el otro muere."""
    cli = hijos(_HIJO_PUERTA, tmp_path, 1, 1)
    assert cli.linea() == "TOMADA"
    puerta = _UploadConcurrencyGate()
    resultado: list[bool] = []
    with patch.object(concurrencia, "get_upload_max_concurrent", return_value=1), \
            patch.object(concurrencia, "_VUELTA_DE_ESPERA", 0.02):
        hilo = threading.Thread(target=lambda: resultado.append(puerta.acquire(2)), daemon=True)
        hilo.start()
        assert _esperar(lambda: 2 in puerta._waiting)
        time.sleep(0.2)  # unas cuantas vueltas
        assert resultado == [] and puerta._active == 0
        cli.matar()
        hilo.join(timeout=10)
    assert resultado == [True] and puerta._active == 1
    puerta.release()


def test_dos_subidas_de_este_proceso_y_una_de_otro_respetan_el_limite_2(tmp_path, hijos):
    cli = hijos(_HIJO_PUERTA, tmp_path, 2, 1)
    assert cli.linea() == "TOMADA"
    puerta = _UploadConcurrencyGate()
    admitidas: list[int] = []
    with patch.object(concurrencia, "get_upload_max_concurrent", return_value=2), \
            patch.object(concurrencia, "_VUELTA_DE_ESPERA", 0.02):
        def sube(jid):
            if puerta.acquire(jid):
                admitidas.append(jid)

        hilos = [threading.Thread(target=sube, args=(j,), daemon=True) for j in (2, 3)]
        for h in hilos:
            h.start()
        assert _esperar(lambda: admitidas == [2])  # solo cabe una más
        time.sleep(0.2)
        assert admitidas == [2] and puerta._active == 1
        puerta.release()  # la 3 entra al soltar la 2
        assert _esperar(lambda: admitidas == [2, 3])
        for h in hilos:
            h.join(timeout=10)
    puerta.release()


def test_la_puerta_con_limite_cero_no_espera_a_otros_procesos(tmp_path, hijos):
    cli = hijos(_HIJO_PUERTA, tmp_path, 1, 1)
    assert cli.linea() == "TOMADA"
    puerta = _UploadConcurrencyGate()
    with patch.object(concurrencia, "get_upload_max_concurrent", return_value=0):
        assert puerta.acquire(2) is True
        assert puerta.acquire(3) is True
    assert puerta._active == 2
    puerta.release()
    puerta.release()


def test_cancelar_mientras_espera_plaza_de_otro_proceso(tmp_path, hijos):
    cli = hijos(_HIJO_PUERTA, tmp_path, 1, 1)
    assert cli.linea() == "TOMADA"
    puerta = _UploadConcurrencyGate()
    cancelada = threading.Event()
    resultado: list[bool] = []
    with patch.object(concurrencia, "get_upload_max_concurrent", return_value=1), \
            patch.object(concurrencia, "_VUELTA_DE_ESPERA", 0.02):
        hilo = threading.Thread(
            target=lambda: resultado.append(puerta.acquire(2, cancelada=cancelada.is_set)), daemon=True)
        hilo.start()
        assert _esperar(lambda: 2 in puerta._waiting)
        cancelada.set()
        hilo.join(timeout=10)
    assert resultado == [False]
    assert puerta._active == 0 and 2 not in puerta._waiting
    # No se quedó con ninguna plaza: al morir el otro proceso entra la siguiente.
    cli.matar()
    plaza, _ = plazas_compartidas.tomar(1)
    assert plaza is not None
    plaza.soltar()


def test_retirar_mientras_espera_plaza_de_otro_proceso(tmp_path, hijos):
    cli = hijos(_HIJO_PUERTA, tmp_path, 1, 1)
    assert cli.linea() == "TOMADA"
    puerta = _UploadConcurrencyGate()
    resultado: list[bool] = []
    with patch.object(concurrencia, "get_upload_max_concurrent", return_value=1), \
            patch.object(concurrencia, "_VUELTA_DE_ESPERA", 0.02):
        hilo = threading.Thread(target=lambda: resultado.append(puerta.acquire(2)), daemon=True)
        hilo.start()
        assert _esperar(lambda: 2 in puerta._waiting)
        puerta.retirar(2)
        hilo.join(timeout=10)
    assert resultado == [False] and puerta._active == 0


def test_release_suelta_la_plaza_en_fichero():
    puerta = _UploadConcurrencyGate()
    with patch.object(concurrencia, "get_upload_max_concurrent", return_value=1):
        assert puerta.acquire(1) is True
        assert plazas_compartidas.tomar(1)[0] is None
        puerta.release()
        plaza, _ = plazas_compartidas.tomar(1)
    assert plaza is not None
    plaza.soltar()


def test_la_puerta_sigue_funcionando_si_falla_el_cerrojo(monkeypatch):
    def sin_permiso(*a, **k):
        raise OSError("sin permiso")

    monkeypatch.setattr(plazas_compartidas.os, "open", sin_permiso)
    puerta = _UploadConcurrencyGate()
    with patch.object(concurrencia, "get_upload_max_concurrent", return_value=1):
        assert puerta.acquire(1) is True
        assert puerta._active == 1
        puerta.release()
    assert puerta._active == 0
