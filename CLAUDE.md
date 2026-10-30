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
  or `database.py`; `services/` never imports from `web/`), `test_web_no_habla_sql.py`,
  `test_copias_frontend.py` (frontend copies of backend constants must match), `test_dependencia_legacy.py`
  (`legacy.py` stays deleted).
- `test_media_info_congelado.py` compares the mediainfo report against
  `tests/fixtures/mediainfo_informe_esperado.json`. For an intended change, regenerate it with
  `python -m tests.test_media_info_congelado --regenerar` and review the JSON diff.
- CI (`.github/workflows/ci.yml`) runs pytest, critical ruff rules and the frontend checks on every PR.
- `zizmor.yml` audits the workflows and `dependabot.yml` when `.github/` changes; run `zizmor .` locally before pushing a workflow edit.

## Not obvious

- Push events: call `eventos.publicar` from the one place that writes the data, not from its callers; it
  must never raise. The server stays a single process (no extra uvicorn workers): the event bus is in memory.
  A new `setInterval` in the frontend fails `test_no_han_aparecido_sondeos_nuevos` unless it is listed in
  `SONDEOS_ESPERADOS` or `RELOJES`: push from the server instead of polling.

- Migrations: bump `SCHEMA_VERSION` in `database.py` and add a `_migrate_*` call at the end of the cascade in
  `init_db`. `init_db` runs on every authenticated request and returns early when the version matches.
- Upload pipeline: `upload_queue._run_queued_job` → `carpeta_subida` links the files into
  `UPLOADRR_UPLOADS_DIR` (default `/config/Uploadrr/uploads`) → `upload_execution.start_upload_job` →
  Uploadrr-EMU subprocess. Uploadrr hands that same folder to qBittorrent as the save path, so qBittorrent
  must see it at the same path. `_enlazar` hardlinks and falls back to a symlink across filesystems; keep the
  folder on the media's filesystem (e.g. under `/data`): a symlink only seeds if qBittorrent resolves its target.
- Contract with Uploadrr-EMU, change both repos together: argv in `services/uploadrr_contract.py`;
  `config.yaml` keys staged by `uploadrr_config_staging.py` / `uploadrr_yaml.py` and restored from
  `data/config.yaml.bak` after every job (hand edits to `config.yaml` don't survive, edit the `.bak`);
  progress and result parsing in `uploadrr_progress.py` / `upload_result_parser.py` match its output lines
  verbatim. Uploadrr-EMU exits 0 only if something was uploaded (any other code is a failed job), and after
  a successful upload prints `Torrent URL: …`.
- eMuwarez and TMDb keys travel in the URL query. Never log or return a raw URL: use
  `integrations.base.url_sin_claves`.
- Image: `ghcr.io/kisnov/emuwarez-uploadrr`. `.github/workflows/imagen.yml` builds it on every push to
  `master` as `:<sha>` and `:latest`; a `vX.Y.Z` tag (pushed by `scripts/desplegar.sh` when it publishes a
  version, or from a GitHub release) adds `:X.Y.Z` to that commit's image, and must match `__version__`.
  `desplegar.sh` also builds and pushes `:latest` locally to publish the manifest. Pass
  `--build-arg UPLOADRR_COMMIT=…` or the Uploadrr-EMU clone layer comes from cache.
- Version manifest: the Diagnóstico card compares the image's `APP_COMMIT` with `latest.json` in the public
  repo `Kisnov/uploadrr-version` (a fork of `Rovaal-code/uploadrr-version`); to test against another
  manifest, set `UPLOADRR_VERSION_MANIFEST_URL`. It is separate because this
  repo and the image are private, so the app can't ask GHCR or read a private raw URL without a token.
  `desplegar.sh` publishes it after `docker push` via `scripts/publicar_version.py --repo`; don't edit it by
  hand, run that script (needed after `--sin-publicar`). The file is public: keep `--notas` neutral.
- Building on Windows: the checkout is CRLF (autocrlf), and a CRLF `docker-entrypoint.sh` fails with
  "no such file or directory". Build from `git -c core.autocrlf=false archive HEAD`.

## Plan

The full code review and the phased improvement plan live in `tmp/analisi/` (gitignored, on Gabriel's PC
only): `PLA.md` for the plan, `ESTAT.md` for what is done and what is next.
