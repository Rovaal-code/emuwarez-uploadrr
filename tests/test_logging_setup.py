"""Los logs de la app también salen por stdout, que es lo que lee `docker logs`."""
from __future__ import annotations

import logging

from emuwarez_uploadrr.web import logging_setup


def test_los_logs_de_la_app_salen_por_stdout_sin_duplicar_uvicorn(monkeypatch, tmp_path, capsys):
    root = logging.getLogger()
    uvicorn = logging.getLogger("uvicorn")
    monkeypatch.setattr(logging_setup, "_configured", False)
    monkeypatch.setattr(logging_setup, "get_config_dir", lambda: str(tmp_path))
    monkeypatch.setattr(root, "handlers", [h for h in root.handlers if not isinstance(h, logging_setup._StdoutHandler)])
    # Lo que deja el dictConfig de uvicorn antes de importar la app.
    monkeypatch.setattr(uvicorn, "handlers", [logging.StreamHandler()])
    monkeypatch.setattr(uvicorn, "propagate", False)

    logging_setup.setup_app_logging()
    logging.getLogger("emuwarez.prueba").info("sincronización terminada")
    logging.getLogger("uvicorn.error").info("Started server process")

    out, err = capsys.readouterr()
    assert "emuwarez.prueba: sincronización terminada" in out
    assert out.count("Started server process") == 1
    assert "Started server process" not in err
