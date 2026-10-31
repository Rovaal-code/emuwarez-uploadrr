"""Un ciclo del planificador que falla deja rastro en el registro (F12 de la revisión de 2026-10-31)."""
from __future__ import annotations

import asyncio
import logging

import pytest


def test_un_ciclo_del_planificador_que_falla_queda_en_el_registro(monkeypatch, caplog):
    from emuwarez_uploadrr.services import scheduler
    from emuwarez_uploadrr.web import app as web_app

    def _falla():
        raise RuntimeError("fallo del ciclo")

    async def _una_vuelta(_segundos):
        raise asyncio.CancelledError

    monkeypatch.setattr(scheduler, "tick_due_tasks", _falla)
    monkeypatch.setattr(web_app.asyncio, "sleep", _una_vuelta)

    with caplog.at_level(logging.ERROR, logger="emuwarez.web"):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(web_app._scheduler_loop())

    registro = [r for r in caplog.records if r.name == "emuwarez.web"]
    assert registro and registro[0].exc_info and "fallo del ciclo" in str(registro[0].exc_info[1])
