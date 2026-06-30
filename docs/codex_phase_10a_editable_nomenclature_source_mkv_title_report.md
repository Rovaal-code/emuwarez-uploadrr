# Phase 10A — Nomenclatura editable, Source Assistant y título interno MKV

## Objetivo

Permitir al usuario editar manualmente cada campo de la nomenclatura EMU antes de aplicarla, con asistencia automática de fuente/proveedor desde TMDb, y controlar el título interno del fichero MKV.

---

## Fórmula EMU

```
[Título][Año][Resolución][Fuente][Códec][Audios+Canales][SUBS] - [Uploader]
```

Para fuentes con proveedor (solo WEB-DL):
```
AMZN WEB-DL | NF WEB-DL | DSNP WEB-DL …
```

Regla: `PROVIDER_SOURCES = frozenset({"WEB-DL"})` — únicamente WEB-DL acepta prefijo de proveedor.

---

## Componentes implementados

### Backend Python

| Fichero | Descripción |
|---------|-------------|
| `emuwarez_uploadrr/services/source_assistant.py` | Lista de fuentes/proveedores EMU, sugerencia via TMDb, build/preview de campos editables |
| `emuwarez_uploadrr/services/mkv_title.py` | Control del título interno MKV con mkvpropedit (`shell=False`) |
| `emuwarez_uploadrr/integrations/tmdb.py` | Watch Providers API de TMDb (no bloquea si falla) |

### API REST (nuevos endpoints)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/nomenclature/sources` | Lista de fuentes EMU |
| GET | `/api/nomenclature/providers` | Lista de proveedores EMU |
| GET | `/api/library/{id}/nomenclature/fields` | Campos editables actuales |
| POST | `/api/library/{id}/nomenclature/preview-fields` | Preview con campos editados |
| POST | `/api/library/{id}/nomenclature/save-fields` | Guarda campos y crea propuesta |
| GET | `/api/library/{id}/mkv-title/preview` | Preview del título MKV a aplicar |
| POST | `/api/library/{id}/mkv-title/apply` | Aplica título MKV (requiere token) |

Todos los endpoints requieren Bearer token (401 sin autenticación).

### CLI (nuevos subcomandos)

```
emuwarez nomenclature sources
emuwarez nomenclature providers
emuwarez nomenclature fields <id>
emuwarez nomenclature preview-fields <id> --fields-json '{"title":"...","source":"WEB-DL",...}'
emuwarez mkv-title preview <id>
emuwarez mkv-title apply <id> [--apply --confirm APLICAR_TITULO_MKV]
```

### Frontend

| Fichero | Descripción |
|---------|-------------|
| `frontend/src/components/NomenclatureFieldsModal.tsx` | Modal de edición de campos + sección MKV |
| `frontend/src/api/nomenclature.ts` | Funciones API Phase 10A añadidas |

---

## Base de datos

`SCHEMA_VERSION` bumpeado de 11 a 12.

Nuevas columnas en `nomenclature_proposals`:

- `fields_json` — campos editables guardados como JSON
- `source_final` — fuente final seleccionada
- `provider_final` — proveedor final seleccionado
- `provider_options_json` — opciones de proveedor con disponibilidad TMDb
- `tmdb_available_providers_json` — proveedores disponibles en TMDb para este ítem
- `internal_mkv_title` — título interno MKV calculado
- `internal_title_status` — estado de aplicación del título MKV
- `internal_title_applied_at` — timestamp de aplicación
- `internal_title_error` — error si la aplicación falló

Nuevas entradas en `settings`:

- `default_release_tag` = `"EMUWAREZ"`
- `provider_priority_order` = `'["AMZN","NF","DSNP","MAX","ATVP"]'`
- `tmdb_watch_region` = `"ES"`

---

## Seguridad y restricciones

- `mkvpropedit` solo se ejecuta con `shell=False` (sin interpolación de shell)
- Requiere token `APLICAR_TITULO_MKV` para ejecución real
- Solo aplica a ficheros `.mkv` en `prepared_path` (nunca `source_path`)
- TMDb Watch Providers es opcional y no bloquea si falla
- No se ejecuta Uploadrr real
- No se modifican ficheros dentro de `Uploadrr/`

---

## Tests (783 passing)

| Fichero | Tests |
|---------|-------|
| `tests/test_nomenclature_compliance.py` | 13 tests — fórmula EMU, fuentes, proveedores |
| `tests/test_source_assistant.py` | 15 tests — source_assistant service |
| `tests/test_mkv_title.py` | 13 tests — mkv_title service, sin ejecución real |
| `tests/test_nomenclature_fields_api.py` | 10 tests — endpoints API fields |
| `tests/test_mkv_title_api.py` | 10 tests — endpoints API mkv-title |
| `tests/test_nomenclature_cli.py` | 10 tests — subcomandos CLI |
