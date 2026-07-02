# eMuwarez Uploadrr — Contrato funcional UI/Backend
## Versión 1.0 · Fase 1

**Fecha:** 2026-06-28
**Rama:** feature/ui-phase-01-contract
**Estado:** Contrato de referencia para implementación de backend (Fase 2+) y frontend (Fase 3+).

---

## 4.1 Objetivo del producto

`eMuwarez Uploadrr` es una aplicación web + CLI autoalojada que:

1. Sincroniza biblioteca desde **Radarr/Sonarr** (fuente principal).
2. Lee peticiones activas de **eMuwarez**.
3. Cruza biblioteca vs. peticiones para detectar compatibilidad.
4. Detecta nomenclatura eMuwarez y permite adaptarla.
5. Sube contenido a eMuwarez usando **Uploadrr** como motor de subida.
6. Expone todo como interfaz web y como CLI funcional equivalente.

### Jerarquía de integraciones

| Integración | Rol | Tipo |
|---|---|---|
| **Radarr** | Fuente principal de películas: estado, calidad, IDs, rutas | Obligatoria |
| **Sonarr** | Fuente principal de series/episodios: estado, calidad, IDs, rutas | Obligatoria |
| **TMDb** | Enriquecimiento: título español, matching, IDs externos, pósters | Recomendada |
| **eMuwarez** | Fuente de peticiones + destino de subida | Obligatoria |
| **Uploadrr** | Motor de subida (proceso externo en `./Uploadrr/`) | Obligatoria |
| **Jellyfin** | Verificación opcional de disponibilidad local | Opcional |
| **Seerr** | Contexto de peticiones de usuarios | Opcional |

### Principio arquitectónico

```text
CLI = espejo funcional de la Web
Web = interfaz visual sobre el mismo motor
```

Ambas comparten: motor de subida (legacy), modelos, base de datos SQLite y servicios de integración. La web no duplica lógica; la reutiliza.

---

## 4.2 Secciones de la UI

### Sidebar (orden definitivo)

```text
Dashboard
Biblioteca
Faltantes
Peticiones
Subidas
Tareas
Instancias
Logs
Configuración
```

---

### Dashboard

**Propósito:** Vista general del estado del sistema.

**Datos que muestra:**
- Tarjetas superiores: Biblioteca sincronizada, Faltantes, Disponibles, Subiendo, Completadas
- Tabla `Actividad reciente` (últimos items modificados/sincronizados)
- Panel derecho `Actividad de subida` (jobs activos con progreso)
- Panel `Últimas tareas ejecutadas`
- Panel `Últimos eventos del sistema`

**Filtros:** Ninguno en dashboard (vista resumen).

**Acciones disponibles:**
- Sincronizar biblioteca (llama a `POST /api/instances/{id}/sync` o `POST /api/sync/library`)
- Sincronizar peticiones EMU (`POST /api/requests/sync`)
- Actualizar vista (`GET /api/dashboard/summary`)

**Endpoints backend:**
```text
GET  /api/dashboard/summary
GET  /api/dashboard/activity
GET  /api/dashboard/upload-activity
GET  /api/dashboard/tasks
GET  /api/dashboard/events
POST /api/sync/library
POST /api/requests/sync
```

**Equivalente CLI:**
```bash
emuwarez-uploadrr sync
emuwarez-uploadrr requests sync
emuwarez-uploadrr tasks list
```

---

### Biblioteca

**Propósito:** Mostrar todo el contenido conocido desde las instancias Radarr/Sonarr configuradas.

**Datos que muestra:**
- Películas disponibles y faltantes (Radarr)
- Series, temporadas, episodios disponibles y faltantes (Sonarr)
- Para cada item: título, año, origen, estado local, calidad, resolución, source, ruta, nomenclatura, estado de petición EMU

**Filtros:**
```text
Búsqueda por título
Tipo: Película / Serie / Temporada / Episodio / Todos
Estado: Disponible / Faltante / Subiendo / Todos
Petición: Compatible / Parcial / No compatible / Llena / Sin petición / Todos
Nomenclatura: Correcta / No adaptada / N/A / Todos
Origen: [lista de instancias configuradas] / Todos
```

**Acciones por item:**
- Adaptar nomenclatura (si `nomenclature_status = not_adapted`)
- Subir (si `local_status = available`)
- Abrir en Radarr/Sonarr (enlace a instancia)
- Ver detalle

**Endpoints backend:**
```text
GET  /api/library
GET  /api/library/{id}
POST /api/library/{id}/adapt-nomenclature
POST /api/library/{id}/upload
POST /api/sync/library
```

**Equivalente CLI:**
```bash
emuwarez-uploadrr library list [--status] [--type] [--search]
emuwarez-uploadrr library show <id>
emuwarez-uploadrr prepare <id>
emuwarez-uploadrr upload <id>
emuwarez-uploadrr sync
```

---

### Faltantes

**Propósito:** Mostrar contenido que Radarr/Sonarr tienen monitorizado o añadido pero **no disponible localmente** o con problema de descarga/importación.

**Origen: Radarr/Sonarr** (no eMuwarez).

**Diferencia con Peticiones:** `Faltantes` nace del estado de Radarr/Sonarr. `Peticiones` nace de eMuwarez. No son lo mismo.

**Estados cubiertos:**
- `Faltante` — monitorizado, sin archivo
- `En cola` — en queue de descarga
- `Descargando` — descarga activa
- `Pendiente de importación` — descargado, falta importar
- `Error de importación` — fallo al importar
- `Error de búsqueda` — Radarr/Sonarr no encuentra fuente

**Datos que muestra:**
- Título, origen (instancia), tipo (película/serie/episodio), estado, calidad esperada, último intento, estado queue, comprobación EMU, petición activa, recomendación

**Filtros:**
```text
Origen: [lista instancias] / Todos
Tipo: Película / Serie / Episodio / Todos
Estado: Faltante / En cola / Descargando / Error / Todos
Tiene error: Sí / No / Todos
Existe en EMU: Sí / No / No comprobado / Todos
Tiene petición EMU: Sí / No / Todos
Recomendación: [por tipo de acción]
```

**Acciones por item:**
- Comprobar en EMU
- Abrir en Radarr/Sonarr
- Reintentar búsqueda (via Radarr/Sonarr API)
- Ver historial
- Crear petición en eMuwarez *(futuro — stub hasta capturar endpoint real)*

**Endpoints backend:**
```text
GET  /api/missing
POST /api/missing/{id}/check-emu
POST /api/missing/{id}/create-emu-request   ← STUB — pendiente endpoint real
```

**Equivalente CLI:**
```bash
emuwarez-uploadrr missing list
emuwarez-uploadrr missing create-request <id>  # stub
```

---

### Peticiones

**Propósito:** Mostrar todas las peticiones activas de eMuwarez, ordenadas por capacidad de cubrirlas con la biblioteca local.

**Origen: eMuwarez** (no Radarr/Sonarr).

**Diferencia con Faltantes:** `Peticiones` nace de eMuwarez. `Faltantes` nace de Radarr/Sonarr.

**Datos que muestra:**
- Petición EMU (título, categoría, tipo pedido, resolución, source, estado, puntos)
- Cruce con biblioteca local (contenido coincidente, calidad, nomenclatura)
- Compatibilidad calculada (Compatible/Parcial/No compatible/Llena)
- Motivos de compatibilidad

**Filtros:**
```text
Búsqueda por título
Categoría: Películas / Series / Todas
Estado EMU: Sin llenar / Lleno / Todos
Compatibilidad: Compatible / Parcial / No compatible / Sin match / Llena / Todas
Resolución pedida: Any / 720p / 1080p / 2160p
Source pedido: Any / WEB-DL / BluRay / HDTV / BDRemux / Otro
Origen local: [lista instancias] / Todos
Nomenclatura: Correcta / No adaptada / N/A / Todos
```

**Orden por defecto:**
```text
1. Compatible + disponible + nomenclatura correcta
2. Compatible + disponible + nomenclatura no adaptada
3. Parcial por source (solo un motivo)
4. Parcial por resolución (solo un motivo)
5. Parcial por source y resolución
6. En biblioteca pero no cumple bien (baja confianza)
7. No encontrado en biblioteca
8. Petición llena
```

**Columnas:**
```text
Petición | Categoría | Tipo pedido | Resolución pedida | Estado EMU |
Compatibilidad | Contenido local | Origen local | Calidad local | Nomenclatura |
Puntos | Creada | Acciones
```

**Acciones:**
- Subir
- Adaptar nomenclatura
- Ver detalle (panel/modal)
- Abrir en eMuwarez
- Abrir en Radarr/Sonarr
- Marcar revisado

**Panel de detalle:**
```text
Bloque "Petición eMuwarez"
  - Nombre, categoría, tipo pedido, resolución pedida, estado, puntos, creada
  - TMDb ID, IMDb ID, enlace eMuwarez

Bloque "Contenido local"
  - Título, origen (instancia), estado local, calidad, resolución, source, ruta, nomenclatura

Bloque "Compatibilidad"
  - Resultado: Compatible / Parcial / No compatible / Llena
  - Motivos con íconos: ✓ TMDb coincide · ✓ Resolución compatible · ⚠ Source diferente

Bloque "Acciones"
  - Subir, Adaptar nomenclatura, Abrir en eMuwarez, Abrir en Radarr/Sonarr, Marcar revisado
```

**Endpoints backend:**
```text
GET  /api/requests
POST /api/requests/sync
GET  /api/requests/{id}
POST /api/requests/{id}/match
POST /api/requests/{id}/mark-reviewed

# Phase 8B — Readiness y priorización
POST /api/requests/readiness/refresh
GET  /api/requests/readiness
GET  /api/requests/prioritized
GET  /api/requests/{id}/readiness
POST /api/requests/{id}/readiness/evaluate
GET  /api/requests/{id}/candidates

# Phase 8C — Cola operativa unificada
POST /api/operational-queue/refresh
GET  /api/operational-queue
GET  /api/operational-queue/summary
GET  /api/operational-queue/{id}
POST /api/operational-queue/{id}/resolve
POST /api/operational-queue/{id}/ignore

# Phase 9A — Ejecución guiada desde la cola
GET  /api/operational-queue/{id}/actions
GET  /api/operational-queue/{id}/action-plan
POST /api/operational-queue/{id}/execute-safe-action   body: {"action": str|null}
GET  /api/operational-queue/{id}/action-events         ?limit=50
```

**Equivalente CLI:**
```bash
emuwarez-uploadrr requests list [--search]
emuwarez-uploadrr requests sync [--force]
emuwarez-uploadrr requests show <id>
emuwarez-uploadrr requests match

# Phase 8B
emuwarez-uploadrr requests readiness-refresh
emuwarez-uploadrr requests readiness [<id>]
emuwarez-uploadrr requests prioritized
emuwarez-uploadrr requests candidates <id>

# Phase 8C
emuwarez-uploadrr queue refresh
emuwarez-uploadrr queue summary
emuwarez-uploadrr queue list [--bucket critical|high|medium|low|blocked] [--status ready|waiting|blocked|open]
emuwarez-uploadrr queue show <id>
emuwarez-uploadrr queue resolve <id>
emuwarez-uploadrr queue ignore <id>

# Phase 9A
emuwarez-uploadrr queue actions <id>
emuwarez-uploadrr queue action-plan <id>
emuwarez-uploadrr queue execute-safe <id> [--action verify_file|view_plan|refresh_queue_item]
emuwarez-uploadrr queue events <id> [--limit 20]
```

---

### Subidas

**Propósito:** Gestión y seguimiento de jobs de subida con Uploadrr.

**Datos que muestra:**
- Jobs activos (con progreso en tiempo real)
- Historial de subidas completadas/fallidas
- Estado detallado: etapa actual, porcentaje, velocidad, ETA, transferido

**Columnas:**
```text
Título | Tipo | Estado | Progreso | Tamaño | Iniciada | Finalizada | Acciones
```

**Etapas de subida:**
```text
Validando archivos
Comprimiendo
Subiendo a EMU
Publicado en EMU
```

**Endpoints backend:**
```text
GET  /api/uploads
GET  /api/uploads/{id}
POST /api/uploads/{id}/start    ← dry_run|apply+INICIAR_UPLOADRR, runtime_type=uploadrr_emu obligatorio para apply real
POST /api/uploads/{id}/cancel
GET  /api/uploads/{id}/logs     ← la UI hace polling cada ~2.5s mientras el job está running (Fase 10F, no SSE)
GET  /api/uploads/{id}/stream   ← SSE para progreso en tiempo real (no implementado; se usa polling en su lugar)
```

**Fase 10E — Contrato Uploadrr-EMU en `command_preview` (`POST /api/library/{id}/upload/preflight`):**
```text
runtime_type          "uploadrr_emu" | "uploadrr_generic"
command_args          list[str] — argv real: [-tk, EMU, -mt, <título>, -tmdb, <id>, -ua, -c, movie|tv, -res, <resolución>, ...]
contract_valid        bool — resultado de validate_uploadrr_emu_contract (allowed_roots, python_path, script)
contract_errors       list[str]
contract_warnings     list[str]
can_execute           bool — siempre false en Fase 10E (ejecución real = Fase 10F)
requires_confirmation "INICIAR_UPLOADRR"
safe_to_execute       bool — siempre false en Fase 10E
```
Ver `docs/codex_phase_10e_uploadrr_emu_contract_fix_report.md` para el detalle completo.

**Fase 10F — Ejecución controlada y progreso, campos nuevos en `UploadJobDetail` (`GET /api/uploads/{id}` y `GET /api/uploads`):**
```text
runtime_type    str | null   — runtime_type resuelto en el momento del preflight de este job
command_preview str | null   — comando redactado (prioriza el capturado en ejecución real sobre el de preflight)
progress_phase  str          — "queued"|"preflight"|"config_staging"|"running"|"finalizing"|"succeeded"|"failed"|"cancelled"|"timeout"
                                (mapeo aproximado de status/stage — nunca un porcentaje inventado)
```
`POST /api/uploads/{id}/start` con `apply=true` bloquea con `error="unsupported_runtime"` (HTTP 400) si `uploadrr.runtime_type != "uploadrr_emu"`.
Ver `docs/codex_phase_10f_controlled_uploadrr_emu_execution_report.md` para el detalle completo.

---

### Tareas

**Propósito:** Historial de tareas ejecutadas (sync, match, subidas, comprobaciones).

**Columnas:**
```text
Tarea | Origen | Estado | Inicio | Fin | Resumen | Detalles
```

**Endpoints backend:**
```text
GET  /api/tasks
POST /api/tasks/{name}/run
```

**Equivalente CLI:**
```bash
emuwarez-uploadrr tasks list
```

---

### Instancias

**Propósito:** Gestionar instancias Radarr/Sonarr (y futuras Jellyfin/Seerr).

**Datos:** Nombre, tipo, URL, estado de conexión, última sincronización.

**Acciones:** Añadir, editar, eliminar, probar conexión, sincronizar.

**Endpoints backend:**
```text
GET    /api/instances
POST   /api/instances
PATCH  /api/instances/{id}
DELETE /api/instances/{id}
POST   /api/instances/{id}/test
POST   /api/instances/{id}/sync
```

**Equivalente CLI:**
```bash
emuwarez-uploadrr instances list
emuwarez-uploadrr instances add radarr --name ... --url ... --api-key ...
emuwarez-uploadrr instances test [id]
emuwarez-uploadrr instances remove <id>
```

---

### Logs

**Propósito:** Visualizar logs del sistema (herencia de `legacy.py` + logs propios).

**Endpoints backend:**
```text
GET /api/logs
```

**Equivalente CLI:**
```bash
emuwarez-uploadrr logs [--tail N]
```

---

### Configuración

**Propósito:** Ajustar configuración general, credenciales, Uploadrr, TMDb, eMuwarez.

**Endpoints backend:**
```text
GET  /api/config
POST /api/config/general
POST /api/config/tmdb
POST /api/config/emu
POST /api/config/uploadrr
```

---

## 4.3 Estados definitivos

### LocalStatus

| Valor interno | Etiqueta UI | Color |
|---|---|---|
| `available` | Disponible | Verde |
| `missing` | Faltante | Rojo |
| `queued` | En cola | Azul |
| `downloading` | Descargando | Azul (animado) |
| `pending_import` | Pendiente de importación | Amarillo |
| `import_error` | Error de importación | Rojo |
| `search_error` | Error de búsqueda | Rojo |
| `uploading` | Subiendo | Morado (animado) |
| `uploaded` | Subido | Verde oscuro |
| `error` | Error | Rojo |
| `unknown` | Desconocido | Gris |

**Nota de implementación:** El schema actual (v2) solo implementa `Disponible`, `Faltante`, `Subiendo`, `Subido`, `Error`, `Desconocido`. Los estados `queued`, `downloading`, `pending_import`, `import_error`, `search_error` requieren leer el endpoint `/api/v3/queue` de Radarr/Sonarr (Fase 4).

### RequestStatus

| Valor interno | Etiqueta UI | Color |
|---|---|---|
| `none` | Sin petición | Gris |
| `compatible` | Compatible | Verde |
| `partial` | Parcial | Amarillo |
| `not_compatible` | No compatible | Naranja |
| `filled` | Llena | Gris claro |
| `active_unmatched` | Petición activa sin coincidencia | Azul |
| `unknown` | Desconocida | Gris |

### NomenclatureStatus

| Valor interno | Etiqueta UI | Color |
|---|---|---|
| `correct` | Correcta | Verde |
| `not_adapted` | No adaptada | Amarillo |
| `not_applicable` | N/A | Gris |
| `unknown` | Desconocida | Gris |

**Nota:** Columna siempre se llama **`Nomenclatura`**. Botón siempre se llama **`Adaptar nomenclatura`**. Nunca usar `FormatoEMU` ni `Añadir formatoEMU`.

### EmuExistenceStatus

| Valor interno | Etiqueta UI | Color |
|---|---|---|
| `not_checked` | No comprobado | Gris |
| `exists` | Existe en eMuwarez | Azul |
| `not_exists` | No existe en eMuwarez | Gris claro |
| `possible_duplicate` | Posible duplicado | Amarillo |
| `duplicate_confirmed` | Duplicado confirmado | Naranja |
| `unknown` | Desconocido | Gris |

### RecommendedAction

| Valor interno | Etiqueta UI | Condición |
|---|---|---|
| `none` | Nada que hacer | Estado neutro sin acción pendiente |
| `wait_download` | Esperar descarga | `local_status` es `queued` o `downloading` |
| `review_arr` | Revisar Radarr/Sonarr | `local_status` es `import_error` o `search_error` |
| `check_emu` | Comprobar en EMU | Faltante sin queue ni error conocido |
| `adapt_nomenclature` | Adaptar nomenclatura | Disponible, petición compatible, nomenclatura no adaptada |
| `upload` | Subir | Disponible, petición compatible, nomenclatura correcta |
| `create_emu_request` | Crear petición en eMuwarez | Faltante, sin queue, sin error, no existe en EMU *(stub hasta Fase final)* |
| `open_emu` | Abrir en eMuwarez | Petición activa visible |
| `open_arr` | Abrir en Radarr/Sonarr | Cualquier item con instancia conocida |
| `view_progress` | Ver progreso | `local_status` es `uploading` |

---

## 4.4 Reglas de compatibilidad de peticiones eMuwarez

### Campos de una petición EMU

```text
title               - nombre de la petición
category            - películas / series
requested_source    - tipo de fuente pedido (WEB-DL / BluRay / HDTV / BDRemux / Any)
requested_resolution - resolución pedida (1080p / 2160p / 720p / Any)
emu_status          - estado en eMuwarez (sin llenar / lleno)
created_at          - fecha de creación
points              - puntos ofrecidos
comments            - número de comentarios
tmdb_id             - ID TMDb si disponible en la petición
imdb_id             - ID IMDb si disponible en la petición
emu_url             - enlace a la petición en eMuwarez
author              - autor (oculto si author_visible=false)
```

### Campos locales usados para matching

```text
title               - título en Radarr/Sonarr
original_title      - título original
spanish_title       - título en español (de TMDb, pendiente Fase 4)
year                - año
media_type          - movie / series / season / episode
tmdb_id             - ID TMDb
imdb_id             - ID IMDb
tvdb_id             - ID TVDb (series)
source              - fuente real (WEB-DL / BluRay / HDTV / BDRemux / WEBRip)
resolution          - resolución real (1080p / 2160p / 720p)
quality             - nombre de calidad en Radarr/Sonarr
path                - ruta local del archivo
size_bytes          - tamaño
instance_name       - nombre de la instancia origen
local_status        - estado local
nomenclature_status - estado de nomenclatura eMuwarez
```

### Prioridad de matching (de mayor a menor confianza)

```text
1. TMDb ID exacto         (match_score = 1.0, id_match = true)
2. IMDb ID exacto         (match_score = 0.95, id_match = true)
3. TVDb ID exacto (series)(match_score = 0.95, id_match = true)
4. título español norm. + año  (match_score = 0.80)
5. título original norm. + año (match_score = 0.75)
6. título normalizado sin año  (match_score = 0.60, requiere validación)
7. fuzzy matching              (match_score < 0.60, solo como referencia, no acción automática)
```

Normalización de título: NFKD + casefold + eliminar diacríticos + eliminar signos + colapsar espacios.

### Reglas de compatibilidad

| EMU pide | Local tiene | Resultado | Motivos |
|---|---|---|---|
| 1080p WEB-DL | 1080p WEB-DL | Compatible | ✓ Resolución · ✓ Source |
| 2160p WEB-DL | 1080p WEB-DL | Parcial | ⚠ Resolución diferente |
| 1080p WEB-DL | 1080p BluRay | Parcial | ⚠ Source diferente |
| 2160p WEB-DL | 1080p BluRay | Parcial | ⚠ Resolución diferente · ⚠ Source diferente |
| Any 1080p | 1080p BluRay | Compatible | ✓ Resolución · ✓ Source (Any) |
| Any Any | cualquier calidad | Compatible | ✓ Sin restricciones |
| 1080p WEB-DL | sin archivo | No compatible | ✗ No disponible localmente |
| EMU estado = lleno | cualquier | Llena | — petición ya cubierta |

**Tratamiento de `Any`:** Si `requested_source` o `requested_resolution` es `Any`, `any`, `cualquiera` o vacío, se considera cumplido para ese campo.

**Prioridad de estado:** Si `emu_status` indica "lleno", el resultado es siempre `Llena`, independientemente del matching.

### Formato de motivos (para UI)

```text
✓ TMDb ID coincide
✓ Resolución compatible: 1080p
✓ Source compatible: WEB-DL
⚠ Resolución diferente: EMU pide 2160p y local es 1080p
⚠ Source diferente: EMU pide WEB-DL y local es BluRay
✗ No disponible localmente
✗ Sin match en biblioteca
```

---

## 4.5 Flujo seguro antes de recomendar acciones

### Secuencia obligatoria de sincronización

```text
1. Sincronizar Radarr (GET /api/v3/movie)
   → Capturar: movieFile, quality, tmdbId, imdbId, path, monitored, status
   → local_status = Disponible si movieFile existe; Faltante si no

2. Sincronizar Sonarr (GET /api/v3/series + episodes + episodeFiles)
   → Capturar: por serie, temporada y episodio
   → local_status según has_file y monitored

3. Leer wanted/missing de Radarr/Sonarr
   → GET /api/v3/wanted/missing (Radarr y Sonarr)
   → Confirmar/enriquecer items ya marcados como Faltante

4. Leer queue de Radarr/Sonarr [Fase 4]
   → GET /api/v3/queue
   → Actualizar local_status a queued / downloading / pending_import

5. Leer history/errores de Radarr/Sonarr [Fase 4]
   → GET /api/v3/history?eventType=downloadFailed o importFailed
   → Actualizar local_status a import_error / search_error

6. Sincronizar peticiones eMuwarez
   → GET <endpoint_configurado> con Bearer token
   → Guardar en request_items
   → Throttle: máximo 1 vez por hora (configurable, mínimo 1h)
   → Si endpoint no configurado: mostrar estado sin peticiones

7. Cruzar peticiones vs. biblioteca (match_requests)
   → Por TMDb ID → IMDb ID → título normalizado
   → Generar request_matches con status, confidence, reasons

8. Calcular compatibilidad de resolución/source
   → _classify_match(): Compatible / Parcial / No compatible / Llena
   → Guardar reasons como lista de strings con prefijo ✓/⚠/✗

9. Comprobar existencia en eMuwarez [cuando endpoint disponible]
   → GET <emu_search_endpoint>
   → Actualizar emu_existence_status en library_items

10. Calcular RecommendedAction por item
    → Ver tabla de RecommendedAction en §4.3
```

### Prechecks antes de recomendar `Crear petición en eMuwarez`

No recomendar esta acción si cualquiera de las siguientes condiciones es verdad:

```text
- local_status es queued, downloading o pending_import
- local_status es available (ya está localmente)
- emu_existence_status es exists
- request_status es compatible, partial o filled
- local_status es import_error o search_error (problema en Radarr/Sonarr, no en EMU)
- upload_job activo para este item
```

Solo se puede recomendar crear petición si:
```text
- local_status es missing
- no está en queue de descarga
- no hay error de importación o búsqueda activo
- emu_existence_status es not_exists
- request_status es none o active_unmatched
- endpoint real de creación configurado (o mostrar stub informativo)
```

---

## 4.6 Dashboard

### Layout

```text
┌─────────────────────────────────────────────────────────────────────┐
│ TOPBAR: logo · título instancia · estado sync · usuario             │
├──────────────┬──────────────────────────────────────────────────────┤
│              │  [Biblioteca]  [Faltantes]  [Disponibles]  [Subiendo]│
│   SIDEBAR    │  [Completadas]                                        │
│              ├────────────────────────────────────┬─────────────────┤
│  Dashboard   │  Actividad reciente                │ Actividad subida│
│  Biblioteca  │  (tabla 8 columnas)                │ (panel progreso)│
│  Faltantes   │                                    │                 │
│  Peticiones  ├────────────────────────────────────┴─────────────────┤
│  Subidas     │  Últimas tareas ejecutadas                            │
│  Tareas      ├──────────────────────────────────────────────────────┤
│  Instancias  │  Últimos eventos del sistema                          │
│  Logs        │                                                       │
│  Config      │                                                       │
└──────────────┴──────────────────────────────────────────────────────┘
```

### Tarjetas superiores

| Tarjeta | Dato principal | Desglose |
|---|---|---|
| Biblioteca sincronizada | N total | `[Radarr icon] Radarr: N` · `[Sonarr icon] Sonarr: N` |
| Faltantes | N faltantes | Películas: N · Series: N |
| Disponibles | N disponibles | con archivo local |
| Subiendo | N activos | jobs de subida activos |
| Completadas | N completadas | últimas 24h |

`Completadas` ocupa la misma columna de ancho que el panel derecho `Actividad de subida`.

### Tabla `Actividad reciente`

Columnas:
```text
Título | Origen | Estado | Petición | Nomenclatura | Tamaño | Añadido | Acciones
```

**Reglas de acciones por fila:**

| Condición | Acción mostrada |
|---|---|
| `available` + `compatible` + `correct` | `Subir` |
| `available` + (`compatible`/`partial`) + `not_adapted` | `Adaptar nomenclatura` + `Subir` |
| `missing` | `Comprobar en EMU` |
| `queued` o `downloading` | `Ver estado` (enlace Radarr/Sonarr) |
| `import_error` o `search_error` | `Revisar Radarr/Sonarr` |
| `uploading` | `Ver progreso` |

**Iconos de origen:** El origen de cada fila debe mostrar siempre el icono de Radarr o Sonarr junto al nombre de la instancia. No mostrar solo texto.

### Panel `Actividad de subida`

```text
Título del job
Tamaño total
Tipo: Película / Episodio / Temporada
━━━━━━━━━━━━━━━━━━━━━━━━░░░░ 62%
Etapa: Subiendo a EMU
Velocidad: 14.2 MB/s
Transferido: 6.2 GB / 10 GB
ETA: 4m 32s

Etapas:
  ✓ Validando archivos
  ✓ Comprimiendo
  ● Subiendo a EMU
  ○ Publicado en EMU
```

### Panel `Últimas tareas ejecutadas`

Columnas:
```text
Tarea | Origen | Estado | Detalles | Ejecutado
```

Tareas ejemplo:
```text
Sincronización completa
Análisis de faltantes
Comprobación en EMU
Sincronización de peticiones
Subida automática
```

### Panel `Últimos eventos`

Columnas:
```text
Hora | Evento | Origen
```

---

## 4.7 Pantalla Peticiones

*(Ver §4.2 — Peticiones para detalle completo)*

Pantalla separada de Faltantes. Muestra todas las peticiones de eMuwarez, ordenadas por capacidad de cubrirlas.

Orden, filtros, columnas y panel de detalle definidos en §4.2.

---

## 4.8 Pantalla Faltantes

*(Ver §4.2 — Faltantes para detalle completo)*

Pantalla separada de Peticiones. Muestra contenido que Radarr/Sonarr no pueden proveer en este momento.

---

## 4.9 Setup inicial web

El wizard aparece en la primera visita a `http://IP:9494` si `app_state.initialized` no es `true`.

No se muestra el Dashboard hasta completar el setup.

### Pasos del wizard

#### Paso 1 — Crear admin local

```text
Usuario (obligatorio)
Contraseña (mínimo 12 caracteres)
Confirmar contraseña
```

Validaciones:
- usuario obligatorio, sin espacios
- contraseña mínimo 12 caracteres
- confirmación debe coincidir
- guardar hash bcrypt o argon2, nunca texto claro

Endpoint: `POST /api/setup/admin`

#### Paso 2 — Configuración general

```text
Nombre de instancia (ej: "Mi Uploadrr")
Zona horaria (ej: Europe/Madrid)
Puerto web (default: 9494)
Ruta de configuración (default: /config)
Tag EMU (default: EMUWAREZ)
Hardlink base (ej: /mnt/storage/uploads/emu)
```

Endpoint: `POST /api/setup/general`

#### Paso 3 — Uploadrr

```text
Ruta a upload.py de Uploadrr (ej: ./Uploadrr/upload.py)
Ruta a config.yaml de Uploadrr (ej: ./Uploadrr/data/config.yaml)
Ruta tmp de Uploadrr
Modo torrent client: watch folder / qBittorrent
```

Endpoint: `POST /api/setup/uploadrr`

#### Paso 4 — TMDb

```text
API key TMDb (recomendado)
Idioma preferido (default: es-ES)
Región preferida (default: ES)
```

Endpoint: `POST /api/setup/tmdb`

#### Paso 5 — eMuwarez

```text
API key eMuwarez (obligatoria para test de conexión)
Endpoint de peticiones (opcional ahora, se puede añadir después)
Anon por defecto (sí/no)
Refresco mínimo de peticiones (default: 60 min, no reducible)
```

Botón: Probar conexión → `POST /api/setup/instances/test` con tipo emu

Endpoint: `POST /api/setup/emu`

#### Paso 6 — Radarr

Múltiples instancias. Por instancia:

```text
Nombre (ej: "Radarr principal")
URL (ej: http://192.168.1.100:7878)
API key
Tipo: Normal / 4K / Anime / Otro
Root folder (opcional, se lee de la API)
Quality profile (opcional, se lee de la API)
Habilitada: Sí/No
```

Botones: Probar conexión · Añadir otra instancia · Eliminar

Endpoint: `POST /api/setup/instances` (tipo radarr)

#### Paso 7 — Sonarr

Igual que Radarr pero tipo sonarr.

#### Paso 8 — Jellyfin (opcional)

```text
[Saltar este paso]
URL
API key
Bibliotecas a verificar
```

Endpoint: `POST /api/setup/instances` (tipo jellyfin)

#### Paso 9 — Seerr (opcional)

```text
[Saltar este paso]
URL
API key
```

Endpoint: `POST /api/setup/instances` (tipo seerr)

#### Paso 10 — Resumen y primera sincronización

```text
Resumen de lo configurado
Botón: Completar setup y sincronizar
```

Tareas al completar:
1. `POST /api/setup/complete` → guarda `initialized=true` en app_state
2. `POST /api/sync/library` → primera sincronización Radarr/Sonarr
3. `POST /api/requests/sync` → primera sync de peticiones si endpoint disponible
4. Redirigir a Dashboard

---

## 4.10 API backend prevista

### Endpoints generales

```text
GET  /api/health
  Response: { "status": "ok", "version": "0.2.0", "db": "ok" }

GET  /api/setup/status
  Response: { "initialized": bool, "step": int | null }
```

### Setup

```text
POST /api/setup/admin
  Body: { "username": str, "password": str, "password_confirm": str }
  Response: { "ok": true }

POST /api/setup/general
  Body: { "instance_name": str, "timezone": str, "port": int, "config_dir": str, "emu_tag": str, "hardlink_base": str }

POST /api/setup/uploadrr
  Body: { "upload_py": str, "config_yaml": str, "tmp_dir": str, "torrent_mode": "watch"|"qbit" }

POST /api/setup/tmdb
  Body: { "api_key": str, "language": str, "region": str }

POST /api/setup/emu
  Body: { "api_key": str, "requests_endpoint": str|null, "anon": bool, "refresh_minutes": int }

POST /api/setup/instances
  Body: { "type": "radarr"|"sonarr"|"jellyfin"|"seerr", "name": str, "url": str, "api_key": str, ... }

POST /api/setup/instances/test
  Body: { "type": str, "url": str, "api_key": str }
  Response: { "ok": bool, "version": str|null, "error": str|null }

POST /api/setup/complete
  Response: { "ok": true, "initialized": true }
```

### Auth

```text
POST /api/auth/login
  Body: { "username": str, "password": str }
  Response: { "token": str, "expires_at": str }

POST /api/auth/logout

GET  /api/auth/me
  Response: { "username": str }
```

### Dashboard

```text
GET /api/dashboard/summary
  Response: {
    "library_total": int, "library_radarr": int, "library_sonarr": int,
    "missing_total": int, "available_total": int,
    "uploading_count": int, "completed_today": int,
    "last_sync": str|null
  }

GET /api/dashboard/activity
  Response: lista de items recientes con campos UI

GET /api/dashboard/upload-activity
  Response: lista de upload_jobs activos con progreso

GET /api/dashboard/tasks
  Response: lista de task_runs recientes

GET /api/dashboard/events
  Response: lista de eventos del sistema
```

### Instancias

```text
GET    /api/instances
POST   /api/instances       Body: InstanceConfig
PATCH  /api/instances/{id}  Body: campos parciales
DELETE /api/instances/{id}
POST   /api/instances/{id}/test
POST   /api/instances/{id}/sync
```

### Sync

```text
POST /api/sync/library      Body: { "include_episodes": bool }
POST /api/sync/requests     Body: { "force": bool, "endpoint_url": str|null }
```

### Biblioteca

```text
GET /api/library
  QueryParams: status, request, nomenclature, type, search, limit, offset

GET /api/library/{id}
  Response: LibraryItem completo

POST /api/library/{id}/adapt-nomenclature
  Body: { "dry_run": bool }
  Response: { "preview": str, "applied": bool }

POST /api/library/{id}/upload
  Body: { "dry_run": bool, "yes": bool }
  Response: { "upload_job_id": int }
```

### Faltantes

```text
GET /api/missing
  QueryParams: type, origin_instance, has_error, emu_status, limit, offset

POST /api/missing/{id}/check-emu
  Response: { "emu_status": str, "url": str|null }

POST /api/missing/{id}/create-emu-request
  ⚠ STUB — responde con:
  { "ok": false, "stub": true,
    "message": "Endpoint de creación de petición EMU pendiente. Capturar desde DevTools > Network." }
```

### Peticiones

```text
GET /api/requests
  QueryParams: search, category, emu_status, compatibility, resolution, source, origin, nomenclature, limit, offset

POST /api/requests/sync
  Body: { "force": bool, "endpoint_url": str|null }
  Response: { "imported": int, "status": "ok"|"throttled", "wait_seconds": int }

GET /api/requests/{id}
  Response: RequestItem + RequestMatch si existe

POST /api/requests/{id}/match
  Response: { "status": str, "confidence": float, "reasons": [str] }

POST /api/requests/{id}/mark-reviewed
  Response: { "ok": true }
```

### Subidas

```text
GET /api/uploads
  QueryParams: status, limit, offset

GET /api/uploads/{id}
  Response: UploadJob completo con eventos

POST /api/uploads/{id}/cancel
  Response: { "ok": bool }

GET /api/uploads/{id}/stream
  Tipo: text/event-stream (SSE)
  Evento ejemplo:
  data: {"upload_id": 1, "stage": "uploading_to_emu", "percent": 62,
         "speed": "14.2 MB/s", "transferred": "6.2 GB / 10 GB", "eta": "4m 32s"}
```

### Tareas

```text
GET /api/tasks
  QueryParams: limit, offset

POST /api/tasks/{name}/run
  Tareas disponibles: sync-library, sync-requests, match-requests, check-emu
  Response: { "task_id": int, "started": true }
```

### Logs y Configuración

```text
GET  /api/logs
  QueryParams: tail (int, default 100)

GET  /api/config
POST /api/config/general
POST /api/config/tmdb
POST /api/config/emu
POST /api/config/uploadrr
```

---

## 4.11 CLI equivalente

### Correspondencia UI ↔ CLI

| Acción en UI | Comando CLI equivalente |
|---|---|
| Dashboard → Sincronizar biblioteca | `emuwarez-uploadrr sync [--episodes]` |
| Dashboard → Sincronizar peticiones | `emuwarez-uploadrr requests sync [--force]` |
| Dashboard → Ver tareas | `emuwarez-uploadrr tasks list` |
| Biblioteca → Listar | `emuwarez-uploadrr library list [--status] [--type] [--search]` |
| Biblioteca → Detalle | `emuwarez-uploadrr library show <id>` |
| Biblioteca → Adaptar nomenclatura | `emuwarez-uploadrr prepare <id>` |
| Biblioteca → Subir | `emuwarez-uploadrr upload <id> [--dry-run]` |
| Faltantes → Listar | `emuwarez-uploadrr missing list` |
| Faltantes → Comprobar EMU | *(pendiente — stub)* |
| Faltantes → Crear petición EMU | `emuwarez-uploadrr missing create-request <id>` *(stub)* |
| Peticiones → Listar | `emuwarez-uploadrr requests list [--search]` |
| Peticiones → Sincronizar | `emuwarez-uploadrr requests sync [--force]` |
| Peticiones → Detalle | `emuwarez-uploadrr requests show <id>` |
| Peticiones → Recalcular cruces | `emuwarez-uploadrr requests match` |
| Instancias → Listar | `emuwarez-uploadrr instances list` |
| Instancias → Añadir | `emuwarez-uploadrr instances add radarr --name ... --url ... --api-key ...` |
| Instancias → Probar | `emuwarez-uploadrr instances test [id]` |
| Instancias → Eliminar | `emuwarez-uploadrr instances remove <id>` |
| Logs | `emuwarez-uploadrr logs [--tail N]` |
| Setup inicial | `emuwarez-uploadrr configure` |
| Estado de entorno | `emuwarez-uploadrr doctor` |
| Ver contrato | `emuwarez-uploadrr web-contract` |

---

## 4.12 Estilo visual de UI

### Tema general

```text
- Dark mode obligatorio como defecto
- Fondo: #0a0d14 (negro azulado profundo)
- Superficie cards: rgba(255,255,255,0.04) con blur sutil (glassmorphism)
- Bordes: 1px solid rgba(59,130,246,0.15) — azul muy atenuado
- Radios de borde: 8px cards, 6px badges, 4px inputs
- Sombras: 0 2px 8px rgba(0,0,0,0.4)
- Tipografía: Inter, system-ui, sans-serif
- Tamaño base: 14px body, 13px tablas, 12px badges
```

### Colores semánticos

| Significado | Color | Hex aproximado |
|---|---|---|
| Disponible / Compatible / Correcta / Completada | Verde | `#22c55e` |
| Faltante / Error / No compatible | Rojo | `#ef4444` |
| Parcial / No adaptada / Warning | Amarillo/Naranja | `#f59e0b` |
| Subiendo / Procesos activos | Morado | `#a855f7` |
| Acciones / Navegación / Info | Azul | `#3b82f6` |
| N/A / Sin petición / Neutro | Gris | `#6b7280` |
| Llena (petición ya cubierta) | Gris claro | `#9ca3af` |

### Grid layout

```text
- Sidebar: 240px fijo
- Topbar: 56px fijo
- Main content: grid 12 columnas, gap 16px
- Cards superiores: 5 cards en fila, misma altura
- Panel derecho (Actividad subida): 320px fijo, misma altura que `Completadas`
- Tabla central: ocupa el resto del ancho menos el panel derecho
- Columnas de tabla: anchos fijos, sin colapsar
- Botones de acción: alineados derecha en columna Acciones
- Badges: altura 20px, padding 4px 8px
```

### Regla obligatoria de iconos

**Cada vez que aparezca Radarr o Sonarr como origen o en resúmenes, debe mostrarse el icono junto al texto.** No solo el nombre en texto plano.

```text
[🎬] Radarr: 8.912          ← icono de Radarr + texto
[📺] Sonarr: 4.345          ← icono de Sonarr + texto
```

Si no hay acceso a los logos oficiales, usar iconos SVG internos que sean visualmente reconocibles e inequívocos (radar como ícono para Radarr, antena como ícono para Sonarr).

### Nombres definitivos de UI (no cambiar)

| Nombre correcto | Nunca usar |
|---|---|
| Nomenclatura | FormatoEMU |
| Adaptar nomenclatura | Añadir formatoEMU |
| Petición | Request |
| Compatible | Fully compatible |
| Parcial | Partially compatible |
| Sin petición | No request |
| Comprobar en EMU | Check EMU |
| Ver progreso | View progress |

---

## 4.13 Docker previsto

### Puerto y variables

```text
Puerto por defecto: 9494
Variables de entorno:
  PORT=9494
  CONFIG_DIR=/config
  TZ=Europe/Madrid
  PUID=1000  (opcional)
  PGID=1000  (opcional)
```

### Volúmenes recomendados

```text
./config:/config                      ← configuración y SQLite
/mnt/storage/media:/media             ← acceso a archivos locales
/mnt/storage/uploads/emu:/uploads     ← destino de hardlinks/preparación
./Uploadrr:/app/Uploadrr              ← motor de subida (externo)
```

Uploadrr no se empaqueta dentro de la imagen Docker. Se monta como volumen externo.

### docker-compose ejemplo

```yaml
services:
  emuwarez-uploadrr:
    image: emuwarez-uploadrr:latest
    container_name: emuwarez-uploadrr
    ports:
      - "9494:9494"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Madrid
      - PORT=9494
      - CONFIG_DIR=/config
    volumes:
      - ./config:/config
      - /mnt/storage/media:/media
      - /mnt/storage/uploads/emu:/uploads
      - ./Uploadrr:/app/Uploadrr
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9494/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Notas

- En Docker, `CONFIG_DIR=/config` debe sobreescribir `~/.config/emuwarez-renamer` del código legacy.
- La base de datos SQLite se guarda en `/config/emuwarez_uploadrr.db` dentro del contenedor.
- Recomendado: usuario no-root con PUID/PGID si el sistema lo soporta.
- Healthcheck: `GET /api/health` devuelve `{"status": "ok"}`.

---

## Phase 9B — E2E controlado en Docker

Esta fase no añade nuevos endpoints API. Añade:

- `scripts/docker-e2e-demo.sh`: E2E controlado completo en Docker con datos simulados
- `emuwarez_uploadrr/services/demo_seed.py`: servicio de seed seguro con token de confirmación
- CLI: `demo seed --media-root <path> --prepared-root <path> --confirm DEMO_SEED`
- CLI: `demo reset --confirm DEMO_RESET`
- `tests/fixtures/fake_uploadrr.py`: fake Uploadrr para E2E sin ejecución real

Garantías: sin servicios reales, sin Uploadrr real, sin subida real, sin API keys reales.

---

## Phase 10A — Nomenclatura editable, Source Assistant y título MKV interno

### Nuevos endpoints

#### Catálogos

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/api/nomenclature/sources` | Bearer | Lista de fuentes EMU (`code`, `label`) |
| GET | `/api/nomenclature/providers` | Bearer | Lista de proveedores EMU (`code`, `name`) |

#### Campos editables

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/api/library/{id}/nomenclature/fields` | Bearer | Campos editables actuales del ítem |
| POST | `/api/library/{id}/nomenclature/preview-fields` | Bearer | Preview con campos modificados (sin guardar) |
| POST | `/api/library/{id}/nomenclature/save-fields` | Bearer | Guarda campos y crea propuesta de nomenclatura |

Body de `preview-fields` y `save-fields`:
```json
{
  "fields": {
    "title": "Dune",
    "year": "2021",
    "resolution": "1080p",
    "source": "WEB-DL",
    "provider": "AMZN",
    "video_codec": "H.265",
    "audio_summary": "DDP5.1",
    "subs": "SPA",
    "tag": "EMUWAREZ"
  }
}
```

Respuesta de `preview-fields`:
```json
{
  "torrent_name": "Dune 2021 1080p AMZN WEB-DL H.265 DDP5.1 SPA - EMUWAREZ",
  "internal_mkv_title": "Dune.2021.1080p.AMZN.WEB-DL.H.265.DDP5.1.SPA.-.EMUWAREZ",
  "fields": { "..." : "..." },
  "provider_options": [
    { "code": "AMZN", "name": "Amazon Prime Video", "label": "AMZN (Amazon Prime Video)", "tmdb_available": true }
  ]
}
```

#### Título MKV interno

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/api/library/{id}/mkv-title/preview` | Bearer | Preview del título a aplicar vía mkvpropedit |
| POST | `/api/library/{id}/mkv-title/apply` | Bearer | Aplica título (requiere token `APLICAR_TITULO_MKV`) |

Body de `mkv-title/apply`:
```json
{
  "dry_run": true,
  "apply": false,
  "confirmation": null
}
```

Para escritura real: `{"dry_run": false, "apply": true, "confirmation": "APLICAR_TITULO_MKV"}`.

### Reglas de negocio

- Solo `WEB-DL` acepta prefijo de proveedor: `AMZN WEB-DL`, `NF WEB-DL`, etc.
- `mkvpropedit` usa `shell=False`; solo aplica a `.mkv` en `prepared_path`
- TMDb Watch Providers es opcional, nunca bloquea el flujo
- `SCHEMA_VERSION = 12`: 9 columnas nuevas en `nomenclature_proposals`, 3 entradas nuevas en `settings`

---

## Phase 10C — Test de conexión para APIs externas

Botones "Probar conexión" para TMDb, eMuwarez, Radarr y Sonarr, sin guardar credenciales. Uploadrr queda fuera de esta fase.

### Nuevos endpoints

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| POST | `/api/integrations/test/tmdb` | Bearer | Prueba una API key de TMDb (enviada o guardada) |
| POST | `/api/integrations/test/emuwarez` | Bearer | Prueba credenciales de eMuwarez (enviadas o guardadas) |
| POST | `/api/integrations/test/arr` | Bearer | Prueba Radarr/Sonarr: instancia guardada (`instance_id`) o credenciales sin guardar (`kind`/`base_url`/`api_key`) |

Body de `test/tmdb` (todos opcionales; si se omite `api_key` usa la guardada):
```json
{ "api_key": "opcional", "language": "es-ES", "region": "ES" }
```

Body de `test/emuwarez` (todos opcionales; si se omiten usa los guardados):
```json
{ "api_key": "opcional", "base_url": "opcional" }
```

Body de `test/arr` — instancia guardada:
```json
{ "instance_id": 1 }
```

Body de `test/arr` — credenciales sin guardar:
```json
{ "kind": "radarr", "base_url": "http://192.168.1.10:7878", "api_key": "..." }
```

`kind` inválido (distinto de `radarr`/`sonarr`) o falta de `base_url`/`api_key` sin `instance_id` → `422`.

Respuesta común (`IntegrationTestResult`):
```json
{ "ok": true, "service": "radarr", "status": "connected", "message": "Conexión correcta", "details": {"version": "5.3.6"} }
```

`status` posibles: `connected`, `not_configured`, `invalid_key`, `connection_error`, `timeout`, `invalid_url`, `invalid_kind`, `unexpected_error`.

### Reglas de negocio

- Todas las pruebas son de solo lectura (TMDb `/configuration`, eMuwarez `/api/torrents/filter?perPage=1`, Arr `/api/v3/system/status`).
- Probar una credencial nunca la guarda.
- Ninguna respuesta ni log contiene la API key completa.
- Uploadrr no tiene código ni endpoint de test en esta fase — ver Fase 10F.

---

## Phase 10F — Ejecución controlada Uploadrr-EMU, settings de runtime y UI de progreso

### Settings de runtime Uploadrr (`GET`/`PUT /api/settings`)

Campos nuevos en `SettingsResponse`/`SettingsUpdateRequest` (sin secretos):
```json
{
  "uploadrr_path": "/opt/Uploadrr",
  "uploadrr_runtime_type": "uploadrr_emu",
  "uploadrr_python_path": "/usr/local/bin/python",
  "uploadrr_timeout": 7200,
  "uploadrr_allowed_roots": ["/data/uploads/emu", "/data/media"]
}
```
Reglas:
- `uploadrr_runtime_type` solo acepta `uploadrr_emu`/`uploadrr_generic` → `422` si es otro valor.
- `uploadrr_timeout` debe ser entero positivo → `422` si es `<= 0`.
- `uploadrr_allowed_roots` acepta `list[str]` o un string CSV (`"a,b,c"`); siempre se normaliza y se devuelve como `list[str]`.
- Las claves se escriben en su forma dotted canónica (`uploadrr.path`, etc.) — la forma legacy con guion bajo sigue funcionando solo como fallback de lectura.

### Test de conexión Uploadrr (`POST /api/integrations/test/uploadrr`)

Solo comprobaciones de filesystem — **nunca ejecuta `upload.py`, nunca lee secretos de `config.yaml`, nunca abre un subproceso**.

Body (todo opcional; si se omite usa lo guardado):
```json
{ "path": "opcional", "python_path": "opcional" }
```
Respuesta (`IntegrationTestResult`), `status` posibles: `not_configured`, `not_found`, `script_missing`, `python_missing`, `connected_no_config` (ok=true, falta `data/config.yaml`), `connected` (ok=true, todo encontrado).

### Ejecución controlada (`POST /api/uploads/{id}/start`)

Sin cambios de contrato respecto a Fase 6C/6D salvo una regla nueva: con `apply=true` (`dry_run=false`, `start=true`, `confirmation=INICIAR_UPLOADRR`), si `uploadrr.runtime_type != "uploadrr_emu"` la respuesta es `400` con `error="unsupported_runtime"` — la ejecución controlada real de esta fase solo cubre el runtime `uploadrr_emu`.

Antes de invocar el subproceso se stagea `DEFAULT.tmdb`/`TRACKERS.EMU.api_key` en `data/config.yaml` (backup automático); al terminar —éxito, fallo, timeout o cancelación— se restaura siempre el original.

### Progreso (`GET /api/uploads`, `GET /api/uploads/{id}`)

Ver el bloque `UploadJobDetail` documentado en la sección "Subidas" más arriba (`runtime_type`, `command_preview`, `progress_phase`). La UI usa polling (~2.5s), no SSE.

### Reglas de seguridad

- `subprocess.Popen` con `shell=False`, argv siempre `list[str]`.
- Nunca se ejecuta un Uploadrr-EMU real en tests/E2E — se usa `tests/fixtures/fake_uploadrr_emu.py`.
- `Uploadrr/` nunca se modifica ni se vendoriza en la imagen.
- Secretos nunca aparecen en `command_preview`, logs o `safe_command_json`.

Ver `docs/codex_phase_10f_controlled_uploadrr_emu_execution_report.md` para el detalle completo.
