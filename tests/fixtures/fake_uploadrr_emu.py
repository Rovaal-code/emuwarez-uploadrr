#!/usr/bin/env python3
"""Fake Uploadrr-EMU CLI for Phase 10F controlled-execution testing.

TEST-ONLY. Accepts the real Uploadrr-EMU flag contract (-tk/-mt/-tmdb/-ua/
-c/-res/-season/-episode) so it can be invoked with the exact argv built by
emuwarez_uploadrr/services/uploadrr_contract.py::build_uploadrr_emu_command.

Safety:
- Never connects to eMuwarez or any network host (no urllib/requests/socket).
- Never reads real API keys or Uploadrr-EMU's config.yaml.
- Never creates a real torrent or uploads anything.
- Only prints deterministic log lines to stdout/stderr and returns an exit code.

Failure/slowness simulation (for exercising cancel/timeout/failed paths):
  --fake-fail                 exit 1 after printing an error line
  --fake-sleep SECONDS        sleep between each log line
  FAKE_UPLOADRR_FAIL=1        same as --fake-fail (env fallback)
  FAKE_UPLOADRR_SLEEP=N       same as --fake-sleep (env fallback)
  FAKE_UPLOADRR_LINES=N       print N more stdout lines (enough to fill the pipe)
"""
from __future__ import annotations

import argparse
import os
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("path")
    parser.add_argument("-tk", "--trackers", dest="trackers", default=None)
    parser.add_argument("-mt", dest="title", default=None)
    parser.add_argument("-tmdb", dest="tmdb_id", default=None)
    parser.add_argument("-ua", dest="unattended", action="store_true")
    parser.add_argument("-c", dest="category", default=None)
    parser.add_argument("-res", dest="resolution", default=None)
    parser.add_argument("-season", dest="season", default=None)
    parser.add_argument("-episode", dest="episode", default=None)
    parser.add_argument("-t", dest="release_type", default=None)
    parser.add_argument("--fake-fail", dest="fake_fail", action="store_true")
    parser.add_argument("--fake-sleep", dest="fake_sleep", type=float, default=None)
    args, _unknown = parser.parse_known_args(argv)

    fail = args.fake_fail or os.environ.get("FAKE_UPLOADRR_FAIL") == "1"
    sleep_s = args.fake_sleep
    if sleep_s is None:
        try:
            sleep_s = float(os.environ.get("FAKE_UPLOADRR_SLEEP", "0") or 0)
        except ValueError:
            sleep_s = 0.0

    def emit(line: str) -> None:
        print(line, flush=True)
        if sleep_s:
            time.sleep(sleep_s)

    emit("[EMU] Preparando subida")
    emit(f"[EMU] Archivo: {args.path}")
    emit(f"[EMU] Tracker: {args.trackers or 'EMU'}  Categoria: {args.category or '-'}  Resolucion: {args.resolution or '-'}")
    emit("[EMU] Validando archivo")
    emit("[EMU] Generando torrent")
    emit("[EMU] Generando descripcion")
    emit("[EMU] Subiendo a tracker")
    for i in range(int(os.environ.get("FAKE_UPLOADRR_LINES", "0") or 0)):
        print(f"[EMU] hashing {i:06d} " + "." * 80)

    if fail:
        print("[EMU] ERROR: fallo simulado durante la subida (--fake-fail)", file=sys.stderr, flush=True)
        return 1

    emit("[EMU] Torrent creado correctamente")
    print("[EMU] URL: https://fake-emu.invalid.test/torrents/999999", flush=True)
    print("[EMU] Torrent ID: 999999", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
