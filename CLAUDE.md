# emuwarez-uploadrr

Self-hosted web app: FastAPI + SQLite backend (`emuwarez_uploadrr/`) and React + Vite + TypeScript frontend
(`frontend/`, served as static files). It syncs Radarr/Sonarr, cross-checks eMuwarez (UNIT3D tracker,
https://emu-warez.com) requests, renames to eMuwarez nomenclature, links files into an uploads folder and runs
the upload with Uploadrr-EMU (`Kisnov/Uploadrr-EMU`, cloned into the image at `/opt/Uploadrr`).

## Workflow

- Sole maintainer: Gabriel (Kisnov). Main repo `Kisnov/emuwarez-uploadrr`, base `master`. `upstream`
  (Rovaal-code) is abandoned.
- Branch and PR, never commit to `master`. Group related changes: no PR per one-line fix. Open PRs as
  non-draft so CodeRabbit reviews them.
- Code comments, commits and UI text are in Spanish. Conventional Commits with a one-line Spanish summary of
  the user-visible outcome (`fix: la subida usa el enlace de la carpeta de subidas`).
- Don't bump the version in a PR: `scripts/desplegar.sh --version` does it at release.

## Verify

- Backend: run the tests in Linux (hardlinks, mediainfo, mkvtoolnix), e.g. `python:3.12-slim` with
  `pip install -e ".[web,dev]"`, then `python -m pytest tests -q -p no:cacheprovider` (~2180 tests, ~7 min).
  On Windows, copy the tree into the container (`cp -r /src/. /w/`) rather than running on the bind mount.
- Frontend: `cd frontend && npm ci && npx tsc --noEmit && npx vitest run && npx vite build`.
- Architecture guards: `test_una_sola_puerta_a_settings.py` (settings only through `services/settings.py`
  or `database.py`), `test_web_no_habla_sql.py`, `test_copias_frontend.py` (frontend copies of backend
  constants must match).

## Not obvious

- Migrations: bump `SCHEMA_VERSION` in `database.py` and add a `_migrate_*` call at the end of the cascade in
  `init_db`. `init_db` runs on every authenticated request and returns early when the version matches.
- Upload pipeline: `upload_queue._run_queued_job` → `carpeta_subida` links the files into
  `UPLOADRR_UPLOADS_DIR` (default `/config/Uploadrr/uploads`) → `upload_execution.start_upload_job` →
  Uploadrr-EMU subprocess. Uploadrr hands that same folder to qBittorrent as the save path, so the uploads
  folder must live under `/data` at a path qBittorrent sees identically (hardlinks, not symlinks).
- Contract with Uploadrr-EMU, change both repos together: argv in `services/uploadrr_contract.py`;
  `config.yaml` keys staged by `uploadrr_config_staging.py` / `uploadrr_yaml.py` and restored from
  `data/config.yaml.bak` after every job (hand edits to `config.yaml` don't survive, edit the `.bak`);
  progress and result parsing in `uploadrr_progress.py` / `upload_result_parser.py` match its output lines
  verbatim. Uploadrr-EMU exits 1 when nothing was uploaded and prints `Torrent URL: …`.
- eMuwarez and TMDb keys travel in the URL query. Never log or return a raw URL: use
  `integrations.base.url_sin_claves`.
- Image: `ghcr.io/kisnov/emuwarez-uploadrr`, built and published with `scripts/desplegar.sh`. Pass
  `--build-arg UPLOADRR_COMMIT=…` or the Uploadrr-EMU clone layer comes from cache. Version manifest repo:
  `Kisnov/uploadrr-version`.
- Building on Windows: the checkout is CRLF (autocrlf), and a CRLF `docker-entrypoint.sh` fails with
  "no such file or directory". Build from `git -c core.autocrlf=false archive HEAD`.

## Plan

The full code review and the phased improvement plan live in `tmp/analisi/` (gitignored, on Gabriel's PC
only): `PLA.md` for the plan, `ESTAT.md` for what is done and what is next.
