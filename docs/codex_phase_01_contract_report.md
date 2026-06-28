# Reporte de ejecución — Fase 1
## Contrato funcional UI/Backend

**Fecha:** 2026-06-28
**Rama:** feature/ui-phase-01-contract

---

## Rama usada

```
feature/ui-phase-01-contract
```

Creada desde `feature/ui-phase-00-audit` (commit `7769b8f`).

---

## Commits creados en esta fase

| Hash | Mensaje | Descripción |
|---|---|---|
| `c59642f` | `chore: ignore generated files and external Uploadrr runtime` | Higiene Git: `.gitignore` + quitar Uploadrr del índice |
| *(siguiente)* | `docs: define ui backend contract` | Contrato funcional, JSON validado, reporte |

---

## Archivos modificados/creados

### Nuevos

| Archivo | Descripción |
|---|---|
| `.gitignore` | Ignora `__pycache__`, `.venv`, logs, DB locales, `Uploadrr/` |
| `docs/ui_backend_contract.md` | Contrato funcional completo UI/Backend (secciones 4.1–4.13) |
| `docs/ui_backend_contract.json` | Versión estructurada JSON del contrato (validada) |
| `docs/codex_phase_01_contract_report.md` | Este reporte |

### Modificados

| Archivo | Cambio |
|---|---|
| `emuwarez_uploadrr/cli.py` | Función `cmd_web_contract()` actualizada para apuntar a documentos nuevos y resumir estados/equivalencias CLI↔UI |

### Eliminados del índice Git (sin borrar del disco)

| Elemento | Motivo |
|---|---|
| `Uploadrr` (gitlink 160000) | Era un repo git embebido no declarado como submodule. Se eliminó del índice con `git rm --cached -r Uploadrr`. El directorio sigue en disco. |

---

## Higiene Git resuelta

### `Uploadrr/`

**Situación en Fase 0:** Aparecía en `git status` como repo embebido modificado (`160000`).

**Acción realizada:**
```bash
git rm --cached -r Uploadrr
```

**Resultado:** `Uploadrr/` está ignorado por `.gitignore` y eliminado del índice. No aparece en `git status`. El directorio en disco no fue tocado. Verificado con `ls Uploadrr/ | head -5`.

### `__pycache__/`

**Situación en Fase 0:** Cuatro directorios `__pycache__/` generados por los comandos de validación sin rastrear.

**Acción realizada:**
```bash
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
```

**Resultado:** Directorios eliminados. Cubiertos por `.gitignore` (`__pycache__/`). No volverán a aparecer en `git status`.

---

## Validaciones ejecutadas

### py_compile

```bash
python3 -m py_compile emuwarez_uploader.py
find emuwarez_uploadrr -name "*.py" -print0 | xargs -0 python3 -m py_compile
```

**Resultado:** ✓ OK — 0 errores en 35 archivos (1 lanzador + 34 módulos del paquete).

### JSON

```bash
python3 -m json.tool docs/ui_backend_contract.json > /tmp/ui_backend_contract.validated.json
```

**Resultado:** ✓ JSON válido. Estructura verificada con todas las claves requeridas: `product`, `sections`, `statuses`, `recommended_actions`, `compatibility_rules`, `api_endpoints`, `ui_style`, `docker`, `future_stubs`.

### CLI legacy

```bash
python3 emuwarez_uploader.py --help
```

**Resultado:** ✓ Ayuda legacy mostrada correctamente. Modo legacy intacto.

### CLI moderna

```bash
python3 emuwarez_uploader.py db init
```
**Resultado:** `✓ SQLite lista: /home/alvaro/.config/emuwarez-renamer/emuwarez_uploadrr.db`

```bash
python3 emuwarez_uploader.py web-contract
```
**Resultado:** ✓ Nuevo contrato funcional mostrado con secciones, estados, equivalencias CLI↔UI y stubs.

```bash
python3 emuwarez_uploader.py instances list
```
**Resultado:** ✓ Tabla vacía (sin instancias configuradas). Comando funciona correctamente.

---

## Contenido del contrato creado

### docs/ui_backend_contract.md (secciones)

| Sección | Contenido |
|---|---|
| 4.1 | Objetivo del producto y jerarquía de integraciones |
| 4.2 | Secciones de UI con propósito, filtros, columnas, acciones y endpoints por sección |
| 4.3 | Estados definitivos: LocalStatus, RequestStatus, NomenclatureStatus, EmuExistenceStatus, RecommendedAction |
| 4.4 | Reglas de compatibilidad de peticiones EMU: campos, matching por prioridad, tabla de reglas, formato de motivos |
| 4.5 | Flujo seguro de 10 pasos + prechecks antes de "Crear petición EMU" |
| 4.6 | Dashboard: layout ASCII, tarjetas, tabla Actividad reciente, panel subida, paneles de tareas/eventos |
| 4.7 | Pantalla Peticiones: referencia a §4.2 |
| 4.8 | Pantalla Faltantes: referencia a §4.2 |
| 4.9 | Setup wizard: 10 pasos con campos, validaciones y endpoints |
| 4.10 | API backend prevista: 48 endpoints con método, ruta, fase y flag stub |
| 4.11 | Correspondencia CLI↔UI: tabla completa |
| 4.12 | Estilo visual: tema, colores semánticos, grid, iconos Radarr/Sonarr, nombres definitivos |
| 4.13 | Docker: puerto, variables, volúmenes, docker-compose ejemplo, healthcheck |

### docs/ui_backend_contract.json (claves)

```json
{
  "product": { integraciones y roles },
  "sections": [ 9 secciones de UI ],
  "statuses": { 4 enums de estado con etiquetas y colores },
  "recommended_actions": { 10 acciones con condiciones },
  "compatibility_rules": { prioridad de matching, valores de resultado },
  "api_endpoints": [ 48 endpoints con fase, método, ruta y flag stub ],
  "ui_style": { tema, colores, grid, naming_rules, icon_rule },
  "docker": { puerto, variables, volúmenes },
  "future_stubs": [ 2 stubs documentados: create_emu_request, check_emu_existence ]
}
```

---

## Estado de Uploadrr

- `Uploadrr/` ignorado correctamente por `.gitignore`.
- No aparece en `git status`.
- Directorio en disco intacto y funcional (verificado con `ls`).
- No se tocó ningún archivo dentro de `Uploadrr/`.

---

## Estado de `__pycache__`

- Eliminado del disco con `find . -type d -name "__pycache__" -prune -exec rm -rf {} +`.
- Cubierto en `.gitignore`.
- No aparece en `git status`.

---

## Riesgos pendientes identificados en esta fase

### Riesgos heredados de Fase 0 (sin resolver todavía)

| Riesgo | Estado | Fase prevista |
|---|---|---|
| Dependencia de `legacy.py` en casi todos los módulos | Pendiente — no tocar hasta Fase 8 | 8 |
| `CONFIG_DIR` hardcoded a `~/.config/emuwarez-renamer` | Pendiente — necesita env var `CONFIG_DIR` en Docker | 9 |
| Endpoint de listado de peticiones EMU pendiente | Documentado como stub | 5 |
| Endpoint de creación de petición EMU pendiente | Stub explícito, activación en Fase final | Final |
| Schema SQLite v2 incompleto (faltan tablas y campos) | Pendiente Fase 2+ | 2-4 |

### Riesgos nuevos detectados en Fase 1

| Riesgo | Detalle |
|---|---|
| `Uploadrr/` es submodule no declarado | Ahora ignorado. En Docker debe montarse como volumen externo. |
| `DEFAULT_TAG` usado en nomenclatura viene de `legacy.py` | Si legacy cambia el tag, el matching de nomenclatura se rompe. Documentar como dependencia interna. |
| `spanish_title` no existe en schema actual | Necesario para matching completo (Fase 4). Requiere ALTER TABLE + llamada TMDb. |

---

## Siguiente fase recomendada — Fase 2: Backend FastAPI base

**Objetivo:** Crear estructura de backend FastAPI sin romper CLI.

**Tareas principales:**
1. Añadir `emuwarez_uploadrr/api/app.py` con `create_app()`.
2. Añadir routers mínimos: `/api/health`, `/api/setup/status`, `/api/tasks` (readonly), `/api/instances` (readonly).
3. Añadir comando CLI: `python3 emuwarez_uploader.py web serve --port 9494`.
4. Añadir `fastapi` y `uvicorn` a `pyproject.toml`.
5. Pasar `CONFIG_DIR` por variable de entorno para compatibilidad Docker.
6. Actualizar schema SQLite a v3 con campos faltantes en `library_items` y `upload_jobs`.

**Archivos previstos en Fase 2:**
```text
emuwarez_uploadrr/api/__init__.py
emuwarez_uploadrr/api/app.py
emuwarez_uploadrr/api/deps.py
emuwarez_uploadrr/api/routers/__init__.py
emuwarez_uploadrr/api/routers/health.py
emuwarez_uploadrr/api/routers/setup.py
emuwarez_uploadrr/api/routers/instances.py
emuwarez_uploadrr/api/routers/tasks.py
emuwarez_uploadrr/api/routers/logs.py
emuwarez_uploadrr/database.py    (schema_version = 3, ALTER TABLE)
emuwarez_uploadrr/cli.py          (añadir subcomando "web serve")
pyproject.toml                    (añadir fastapi, uvicorn)
```

**Rama:** `feature/ui-phase-02-backend-base`
**Commit final:** `feat: add FastAPI backend base`

---

## Criterios de aceptación de Fase 1

```text
[x] py_compile pasa — 0 errores en 35 archivos
[x] JSON válido — docs/ui_backend_contract.json
[x] CLI legacy funciona — python3 emuwarez_uploader.py --help
[x] CLI moderna funciona — db init, web-contract, instances list
[x] Uploadrr/ ignorado correctamente — no aparece en git status
[x] __pycache__ limpio — no aparece en git status
[x] docs/ui_backend_contract.md creado — secciones 4.1–4.13
[x] docs/ui_backend_contract.json creado y validado
[x] docs/codex_phase_01_contract_report.md creado
[x] emuwarez_uploadrr/cli.py actualizado — cmd_web_contract actualizado
[x] No se modificó lógica funcional del uploader
[x] Uploadrr/ no se tocó (disco intacto)
[x] No se hizo push
[ ] Commit final: docs: define ui backend contract  ← pendiente paso de commit
```
