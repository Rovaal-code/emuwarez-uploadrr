# emuwarez-uploadrr

Self-hosted web app: FastAPI + SQLite backend (`emuwarez_uploadrr/`) and React + Vite + TypeScript frontend
(`frontend/`, served as static files). It syncs Radarr/Sonarr, cross-checks eMuwarez (UNIT3D tracker,
https://emu-warez.com) requests, renames to eMuwarez nomenclature, links files into an uploads folder and runs
the upload with Uploadrr-EMU (`Kisnov/Uploadrr-EMU`, cloned into the image at `/opt/Uploadrr`).

## Workflow

- Sole maintainer: Gabriel (Kisnov). Main repo `Kisnov/emuwarez-uploadrr`, base `master`. `upstream`
  (Rovaal-code) is abandoned.
- Branch and PR, never commit to `master`. Group related changes: no PR per one-line fix. Open PRs as
  non-draft so CodeRabbit reviews them; its standing rules per path live in `.coderabbit.yaml`.
- UI text is in Spanish (the users are Spanish speakers), and so are the README and docs. Code comments and commits
  may be in Spanish or English; most of the code is in Spanish, so Spanish keeps it consistent, but don't translate
  existing comments just to change their language. Conventional Commits with a one-line summary of the user-visible
  outcome (`fix: la subida usa el enlace de la carpeta de subidas`).
- Don't bump the version in a PR: `scripts/desplegar.sh --version` does it at release.
- Commit identity is whatever the environment sets up; AI attribution in commits or comments is fine.

## Saving review and CI budget

- Run the full backend suite locally only when code changed or a merge conflict was resolved. A clean merge of
  `master` into a PR branch is left to CI.
- CodeRabbit allows 10 reviews per hour, and every push to an open PR costs one. Fix real Major/Critical findings
  right away. A Minor, nitpick or trivial finding gets a reply on its thread (fix it or say why not), and its fix
  rides on the next push that is happening anyway, not on a push of its own.
- Don't fight CodeRabbit's auto-pause on busy branches: post `@coderabbitai review` (alone in the comment) only
  once the PR is otherwise ready (CI green, every thread answered).

## Verify

- Backend: run the tests in Linux (hardlinks, mediainfo, mkvtoolnix), e.g. `python:3.12-slim` with
  `pip install -c constraints.txt -e ".[web,dev]"`, then `python -m pytest tests -q -p no:cacheprovider` (~2180 tests, ~7 min).
  On Windows, copy the tree into the container (`cp -r /src/. /w/`) rather than running on the bind mount.
- Frontend: `cd frontend && npm ci && npx tsc --noEmit && npm run lint && npx vitest run && npx vite build`.
- Architecture guards: `test_una_sola_puerta_a_settings.py` (settings only through `services/settings.py`
  or `database.py`; `services/` never imports from `web/`), `test_web_no_habla_sql.py`,
  `test_copias_frontend.py` (frontend copies of backend constants must match), `test_dependencia_legacy.py`
  (`legacy.py` stays deleted).
- `test_media_info_congelado.py` compares the mediainfo report against
  `tests/fixtures/mediainfo_informe_esperado.json`. For an intended change, regenerate it with
  `python -m tests.test_media_info_congelado --regenerar` and review the JSON diff.
- CI (`.github/workflows/ci.yml`) runs pytest, ruff (`--select E9,F`: syntax errors and pyflakes, so no unused imports or variables) and the frontend checks on every PR, and from
  `publicar.yml` before a release; it uploads coverage, test results and the frontend bundle size to Codecov
  (`codecov.yml`: the changed `emuwarez_uploadrr/` lines of a PR need 70 % coverage or `codecov/patch` fails; the
  frontend is not measured; the total is informational;
  needs the `CODECOV_TOKEN` secret). Master has no CI of its own: `bundle.yml`
  only builds the frontend on each push that touches `frontend/` (~40 s) so PRs have a bundle size to compare against.
- `zizmor.yml` audits the workflows and `dependabot.yml` when `.github/` changes; run `zizmor --gh-token "$(gh auth token)" .` locally (without a token it skips online audits) before pushing a workflow edit.

## Not obvious

- Push events: call `eventos.publicar` from the one place that writes the data, not from its callers; it
  must never raise. The server stays a single process (no extra uvicorn workers): the event bus is in memory.
  A new `setInterval` in the frontend fails `test_no_han_aparecido_sondeos_nuevos` unless it is listed in
  `SONDEOS_ESPERADOS` or `RELOJES`: push from the server instead of polling.
- CI on a PR that only touches `frontend/`, `docs/` or `.md` runs just the test files that contain the word
  `frontend` (`grep -l frontend tests/test_*.py`). A test that reads frontend files must name `frontend` in its own file.

- Migrations: bump `SCHEMA_VERSION` in `database.py` and add a `_migrate_*` call at the end of the cascade in
  `init_db`. `preparar_base()` runs it once at startup (lifespan and `web serve`): it copies the DB to
  `backups/pre-migracion-*.db` first and refuses a DB left by a newer version (`BaseMasNuevaError`); after that
  `init_db` returns at once for that file, until a restore calls `olvidar_esquema()`. Where nobody called
  `preparar_base` (tests, scripts) `init_db` still checks the stored version. Open the DB with `db()` (commits,
  rolls back, closes) or the `get_db` dependency; a DB failure in a request is a 503, never a 401.
- Upload pipeline: `upload_queue._run_queued_job` → `carpeta_subida` links the files into
  `UPLOADRR_UPLOADS_DIR` (default `/config/Uploadrr/uploads`) → `upload_execution.start_upload_job` →
  Uploadrr-EMU subprocess. Uploadrr hands that same folder to qBittorrent as the save path, so qBittorrent
  must see it at the same path. `_enlazar` hardlinks and falls back to a symlink across filesystems; keep the
  folder on the media's filesystem (e.g. under `/data`): a symlink only seeds if qBittorrent resolves its target.
- Contract with Uploadrr-EMU, change both repos together: argv in `services/uploadrr_contract.py`;
  `config.yaml` keys staged by `uploadrr_config_staging.py` / `uploadrr_yaml.py` and restored from
  `data/config.yaml.bak` after every job, and also at startup and before the next job if one died mid-run
  (hand edits to `config.yaml` don't survive, edit the `.bak`);
  progress and result parsing in `uploadrr_progress.py` / `upload_result_parser.py` match its output lines
  verbatim. Uploadrr-EMU exits 0 only if something was uploaded (any other code is a failed job), and after
  a successful upload prints `Torrent URL: …`. Resuming: Uploadrr-EMU prints `Step done: screenshots` / `Step done: torrent` (plain `print`) and
  the app stores them (`upload_jobs.pasos_uploadrr_json`, with `Torrent URL:` as `tracker`); a retry that reuses the
  previous job's prepared files, when that job itself launched Uploadrr-EMU, sets `reanuda_uploadrr` and launches with `--resume` (`subida_pasos.py`). Without
  `--resume`, Uploadrr-EMU wipes its `tmp/<name>` first, so a re-prepared file never meets a stale `BASE.torrent`.
- eMuwarez and TMDb keys travel in the URL query. Never log or return a raw URL: use
  `integrations.base.url_sin_claves`.
- Image: `ghcr.io/kisnov/emuwarez-uploadrr`, built only when a version is published. `publicar.yml` ("Publicar
  versión": by hand, or on odd days of the month when 3+ PRs from `feat/` or `fix/` branches (merge commits, or `feat:`/`fix:` squash
  commits) merged since the last `__version__` change) runs
  the full CI on master's tip, bumps `__version__` (`auto`: minor if any `feat/` PR, else patch), pushes that commit
  and `vX.Y.Z`, builds `:X.Y.Z`, `:<sha>`, `:latest` and `:edge`, publishes the manifest (secret
  `UPLOADRR_VERSION_TOKEN`) and creates the GitHub release with the PRs merged since the previous tag. Release when Gabriel asks: `gh workflow run publicar.yml -f notas="…"`, with a
  neutral public note. `solo_prueba=true` builds `:edge` from master's tip only. `scripts/desplegar.sh` is
  the local fallback (no Actions minutes, no tests) and pushes in the same order; `--solo-prueba` pushes only
  `:edge`. Pass `--build-arg UPLOADRR_COMMIT=…` or
  the Uploadrr-EMU clone layer comes from cache.
- Version manifest: the Diagnóstico card compares the image's `APP_COMMIT` with `latest.json` in the public
  repo `Kisnov/uploadrr-version` (a fork of `Rovaal-code/uploadrr-version`); to test against another
  manifest, set `UPLOADRR_VERSION_MANIFEST_URL`. It is separate because this
  repo and the image are private, so the app can't ask GHCR or read a private raw URL without a token.
  `desplegar.sh` publishes it after `docker push` via `scripts/publicar_version.py --repo`; don't edit it by
  hand, run that script. The file is public: keep `--notas` neutral.
- Image Python deps: `constraints.txt` pins the `web` extra and what it pulls (Uploadrr-EMU pins its own in its
  `requirements.txt`); the Dockerfile and CI install with `-c constraints.txt`. Raising a minimum in the `web` extra
  means updating the pin too (`test_imagen_docker.py` checks they agree); the header of `constraints.txt` says how.
- Uploadrr-EMU's state in the image: `/opt/Uploadrr/data` is real and refreshes with each image; only `config.yaml`,
  `config.yaml.bak`, `cookies/` and `tmp` are symlinks, baked at build into `/config/Uploadrr`. The entrypoint just
  creates the targets, and seeds `config.yaml` from the image's example the first time. Nothing under
  `/opt/Uploadrr` is writable except `data/` (1777), so don't make the entrypoint create links there.
- Building on Windows: `.gitattributes` keeps text files LF, so a new checkout builds with `docker build .`. A checkout
  made before it is still CRLF, and a CRLF `docker-entrypoint.sh` fails with "no such file or directory": build
  from `git -c core.autocrlf=false archive HEAD`.

## Plan

The phased improvement plan, what is done and what comes next live in `docs/PLAN.md`. Read it before starting plan
work and update it in the same PR that finishes a step. The older detailed review notes are in `tmp/analisi/`
(gitignored, on Gabriel's PC only).
