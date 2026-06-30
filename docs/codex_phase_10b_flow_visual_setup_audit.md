# Fase 10B Audit — Flow, Visual Style and Initial Setup

Fecha: 2026-06-30  
Auditor: Claude (read-only, sin modificaciones ni commits)

---

## Estado del repo

- Rama: `master`
- Estado: limpio (sin cambios sin commitear)
- Último commit: `a0ec7ee` — docs: add editable nomenclature MKV title milestone checkpoint
- Tag activo: `emuwarez-uploadrr-editable-nomenclature-mkv-title-v0`
- py_compile: OK (todos los `.py` compilan sin errores)
- Tests: **783 passed, 1 warning** (deprecation de httpx, no bloqueante)
- Frontend build: **OK** — 76 módulos, 1 aviso no bloqueante (dynamic import duplicado en RequestsPage)

---

## Setup inicial actual

El flujo de primera ejecución es:

1. El usuario abre `http://localhost:9494`
2. `App.tsx` consulta `GET /api/setup/status`
3. Si `admin_configured = false` → muestra `SetupWizard` directamente
4. Si hay token válido pero `initialized = false` → muestra `SetupWizard` desde el paso en que se quedó
5. Si no hay token → muestra `LoginPage`

El wizard se abre sin necesidad de login para el primer paso (crear admin). Los pasos siguientes requieren auth.

---

## Campos disponibles en setup

El wizard tiene **7 pasos** en orden estricto:

| Paso | Label | Campos |
|------|-------|--------|
| admin | Crear admin | usuario, contraseña, confirmar contraseña |
| base | Configuración general | nombre de app, zona horaria |
| uploadrr | Uploadrr | ruta al directorio Uploadrr |
| tmdb | TMDb | API key, idioma (es-ES), región (ES) |
| emu | eMuwarez | API key, endpoint (opcional) |
| instances | Instancias | tipo (radarr/sonarr), nombre, URL, API key, flags 4K/anime |
| complete | Completar | botón final — llama `POST /api/setup/complete` |

- Permite crear usuario admin: ✓
- Permite configurar Radarr: ✓ (en paso instances)
- Permite configurar Sonarr: ✓ (en paso instances)
- Permite configurar eMuwarez API key: ✓
- Permite configurar TMDb API key: ✓
- Permite configurar región TMDb Watch Providers: ✓ (campo "Región" en paso TMDb)
- Permite configurar idioma TMDb: ✓ (campo "Idioma" en paso TMDb)
- Permite configurar ruta Uploadrr: ✓
- Permite configurar default_release_tag: ✗ (no existe campo en setup)
- Permite configurar provider_priority_order: ✗ (no existe campo en setup)
- Permite configurar rutas/mounts media: no directamente — se instruye en docs

El setup backend sí tiene `POST /api/setup/tmdb` con `api_key`, `lang` y `region` (ver `setup_tmdb` en `setup_service`). El frontend los envía correctamente.

---

## TMDb API key: presente o ausente

| Lugar | Estado |
|-------|--------|
| Setup wizard — paso TMDb | **PRESENTE** — campo visible, obligatorio |
| SettingsPage — pestaña Configuración | **AUSENTE** — es un placeholder con texto estático |
| Backend settings API (`/api/settings`) | **NO EXISTE** el endpoint — no hay `settings.py` en `web/api/` |
| `.env.example` | **AUSENTE** (intencionado — el comment dice "configúrala desde setup web") |
| `docs/DEPLOYMENT_DOCKER.md` sección 9 | **DOCUMENTADA** — hay sección "9. Configurar TMDb API key" |

**Conclusión**: TMDb API key solo es configurable en el setup inicial. No hay forma de cambiarla desde la UI una vez completado el setup. No hay endpoint de settings para modificarla.

---

## Settings disponibles

`SettingsPage` tiene 4 pestañas:

| Pestaña | Estado |
|---------|--------|
| Configuración | **PLACEHOLDER** — texto indicando que se use el wizard o la CLI. Lista las secciones pendientes pero no hay campos editables. |
| Diagnóstico | **FUNCIONAL** — muestra estado de la base de datos y directorio de config |
| Backup | **FUNCIONAL** — crear backup .tar.gz, listar backups, restaurar con token RESTAURAR_CONFIG |
| Mantenimiento | **FUNCIONAL** — VACUUM DB (token MANTENIMIENTO_DB), limpiar logs (token LIMPIAR_LOGS), exportar settings JSON |

No existe un endpoint `/api/settings` para leer/escribir settings vía UI.

---

## Flujo post-setup

Tras `POST /api/setup/complete`, el frontend vuelve a llamar `bootstrap()` → el estado pasa a `'app'` → se renderiza `AppShell`.

El usuario ve el **Dashboard** con:
- 5 stat-cards: Biblioteca, Faltantes, Disponibles, Subiendo, Completadas
- Botón "Sincronizar biblioteca"
- Panel "Salud Radarr/Sonarr" (contadores OK/Aviso/Error)
- Panel "Qué hacer ahora" (cola operativa, top 5)
- Panel "Peticiones accionables" (readiness stats)
- Panel "Subidas Uploadrr" (contadores listos/en curso/completados/fallidos)

Si no se ha sincronizado, todos los contadores son 0 y la cola aparece vacía.

---

## Secciones reales de la app

La navegación del sidebar (`domain.ts`) define **10 secciones**:

### Dashboard

- Ruta frontend: `page: 'dashboard'` (sin router, navegación por estado)
- Endpoint: `GET /api/dashboard/summary`, `GET /api/dashboard/activity`, `GET /api/operational-queue` (top 5)
- Muestra: stat-cards, actividad reciente, salud ARR, cola prioritaria, readiness peticiones, subidas
- Acciones: Sincronizar biblioteca, Refrescar cola operativa
- Estado vacío: EmptyState "No hay actividad reciente todavía"
- Estado error: ErrorState con botón Reintentar

### Biblioteca

- Ruta: `page: 'library'`
- Endpoint: `GET /api/library` (paginado, filtros: búsqueda, tipo, estado, origen)
- Muestra: tabla paginada con columnas Título, Tipo, Origen, Estado, Archivo, Petición, Nomenclatura, Diagnóstico, Acción recomendada, Calidad, Actualizado, Acciones
- Acciones por ítem: "Nomenclatura" (abre NomenclatureModal), "Subir" (abre UploadPreflightModal)
- Clic en fila: panel detalle (nombre, metadatos, badges, diagnóstico Fase 8A)
- Estado vacío: EmptyState "Biblioteca vacía"

### Faltantes

- Ruta: `page: 'missing'`
- Endpoint: `GET /api/library/missing`
- Muestra: ítems con `local_status = 'Faltante'` + info ARR queue/history/diagnóstico

### Peticiones

- Ruta: `page: 'requests'`
- Endpoint: `GET /api/requests`, `GET /api/requests/prioritized`, `GET /api/requests/readiness`
- Muestra: peticiones eMuwarez con compatibilidad, readiness, prioridad
- Acciones: sync peticiones, recalcular readiness, ver candidatos
- Bloqueo: sync con throttle mínimo 1 hora

### Uploads

- Ruta: `page: 'uploads'`
- Endpoint: `GET /api/uploads/jobs`, `POST /api/library/{id}/uploads/preflight`, `POST /api/library/{id}/uploads/start`
- Muestra: jobs de subida con estado, logs, artefactos
- Acciones: preflight, iniciar (requiere token INICIAR_UPLOADRR), retry

### Cola operativa

- Ruta: `page: 'queue'`
- Endpoint: `GET /api/operational-queue`, `POST /api/operational-queue/refresh`
- Muestra: ítems priorizados (critical/high/medium/low/blocked) con acción recomendada
- Acciones: refrescar cola, ejecutar acción, resolver ítem, ver action-plan

### Settings

- Ruta: `page: 'settings'`
- Nota: la página se llama `SettingsPage` pero en el sidebar aparece como "Configuración"
- Pestañas: Configuración (placeholder), Diagnóstico, Backup, Mantenimiento
- Acciones destructivas exigen tokens de confirmación escritos a mano

### Maintenance

- No existe como página separada. Está integrada dentro de SettingsPage como pestañas.

### Instancias

- Ruta: `page: 'instances'`
- Endpoint: `GET /api/instances`, `POST /api/instances`, `POST /api/instances/{id}/test`
- Muestra: instancias Radarr/Sonarr con estado de test
- Acciones: añadir, editar, testear, eliminar instancia

### Tareas / Logs

- Rutas: `page: 'tasks'`, `page: 'logs'`
- Muestran actividad de tareas en background y logs del sistema

---

## Flujo de nomenclatura

El flujo de nomenclatura tiene **dos capas**:

### Capa 1 — NomenclatureModal (la que se usa en producción)

- Se abre desde LibraryPage → botón "Nomenclatura" por fila
- Llama: `POST /api/library/{id}/nomenclature/preview`
- Muestra: propuesta generada automáticamente (nombre actual → nombre propuesto)
- Campos: resolution, source, video_codec, audio_summary, subtitle_summary, release_tag (todos de solo lectura — resultado del análisis)
- Acción apply: dry-run → token `APLICAR_NOMENCLATURA` → crea hardlink
- No permite editar campos manualmente
- No muestra provider, no llama a TMDb watch providers, no usa source_assistant

### Capa 2 — NomenclatureFieldsModal (Fase 10A, dead code)

- **NUNCA se abre desde ninguna página**
- El componente existe en `components/NomenclatureFieldsModal.tsx` pero no hay ningún `import NomenclatureFieldsModal` en ningún archivo de páginas
- Campos editables: title, year, resolution, source (dropdown), provider (dropdown condicional si source=WEB-DL), video_codec, audio_summary, subs, tag
- Sí muestra provider solo cuando source = WEB-DL ✓
- Sí marca con ★ los providers disponibles en TMDb ✓ (via `tmdb_available` flag)
- Sí respeta tag configurado (campo editable con valor inicial del settings `default_release_tag`)
- Tiene sección MKV title con preview y apply
- **PROBLEMA**: ninguna página lo instancia → inaccessible para el usuario

---

## Flujo de título interno MKV

El flujo MKV existe en backend y en el componente NomenclatureFieldsModal, pero dado que el modal nunca se abre, el flujo es **inaccessible desde la UI**.

Backend (funcional):
- `GET /api/library/{id}/mkv-title/preview` → `preview_internal_title_update()`
- `POST /api/library/{id}/mkv-title/apply` → `apply_internal_title_update()` — requiere `apply=True` y `confirmation='APLICAR_TITULO_MKV'`
- Requiere `prepared_path` (hardlink ya aplicado) para funcionar
- Bloquea si `mkvpropedit` no está disponible

UI: parcialmente implementada (en NomenclatureFieldsModal) pero no accesible.

---

## TMDb Watch Providers

El backend implementa `get_tmdb_available_providers()` en `source_assistant.py`:
- Llama a `https://api.themoviedb.org/3/{movie|tv}/{tmdb_id}/watch/providers`
- Filtra por región (setting `tmdb_watch_region`, default "ES")
- Devuelve lista de códigos de providers disponibles

El endpoint `POST /api/library/{id}/nomenclature/preview-fields` devuelve `provider_options` con `tmdb_available: true/false` para cada provider.

La UI (NomenclatureFieldsModal) marca con ★ los disponibles en TMDb.

**PROBLEMA**: Como NomenclatureFieldsModal no se usa, esta integración no llega al usuario.

---

## Docker onboarding

### Variables de entorno

Definidas en `.env.example` y `docker-compose.example.yml`:

| Variable | Descripción | Documentada |
|----------|-------------|-------------|
| PUID | UID del usuario propietario de los archivos | ✓ |
| PGID | GID del usuario propietario de los archivos | ✓ |
| TZ | Zona horaria | ✓ |
| EMUWAREZ_UPLOADRR_PORT | Puerto de acceso (default 9494) | ✓ |
| CONFIG_DIR | Directorio config en contenedor (fijo: /config) | ✓ en Dockerfile |

**NO documentadas en .env.example** (intencionado — se configuran vía setup web):
- TMDb API key: documentada en DEPLOYMENT_DOCKER.md sección 9 ✓
- eMuwarez API key: documentada en DEPLOYMENT_DOCKER.md sección 10 ✓
- provider_priority_order: NO documentada en ningún doc Docker
- default_release_tag: NO documentada en ningún doc Docker

### Volúmenes Docker

| Volumen | Propósito | Requerido |
|---------|-----------|-----------|
| `/config` | Base de datos SQLite + settings persistentes | Obligatorio |
| `/opt/Uploadrr` | Bind mount de Uploadrr (externo) — solo lectura | Obligatorio |
| `/data` | Raíz común para media + uploads (evita EXDEV) | Obligatorio |

### Puerto

- `9494` — frontend React + API FastAPI en el mismo servidor

### Primer arranque

1. El contenedor arranca con `python3 emuwarez_uploader.py web serve --host 0.0.0.0 --port 9494`
2. Se inicializa la BD SQLite en `/config`
3. El usuario abre `http://localhost:9494` → setup wizard automático
4. HEALTHCHECK: `GET /api/health` cada 30s

### Comandos de diagnóstico

```bash
python3 emuwarez_uploader.py web doctor
python3 emuwarez_uploader.py web setup-status
bash scripts/docker-smoke-test.sh
bash scripts/docker-e2e-demo.sh
```

---

## Variables de entorno

Ver tabla en sección "Docker onboarding". Las API keys NO van en `.env` — van en la BD vía setup web.

---

## Volúmenes Docker

Ver tabla en sección "Docker onboarding". Requisito clave: `/data/media` y `/data/uploads/emu` en el MISMO filesystem para hardlinks sin EXDEV.

---

## Estilo visual implementado

- **Sistema CSS**: CSS propio con variables CSS, sin Tailwind, sin librería UI externa. Los archivos de estilos son `styles/globals.css`, `styles/layout.css`, `styles/dashboard.css`, `styles/components.css`.
- **Tema**: oscuro por defecto. `color-scheme: dark`.
- **Paleta**:
  - Fondo base: `#0a0d14` (azul muy oscuro, casi negro)
  - Superficie: `#0f1420`
  - Sidebar: `#080b11`
  - Accent: `#3b82f6` (azul) / `#a78bfa` (púrpura para acciones recomendadas)
  - Texto primario: `#e5e7eb`
  - Texto secundario: `#9ca3af`
  - Texto muted: `#6b7280`
  - Borde: `rgba(59, 130, 246, 0.15)`
- **Tipografía**: `Inter` (sans) + `JetBrains Mono` (mono para rutas/código)
- **Tarjetas**: `background: rgba(255,255,255,0.04)`, border con azul translúcido, `border-radius: 8px`, `box-shadow: 0 2px 8px rgba(0,0,0,0.4)`
- **Tablas**: clase `.data-table` con filas clickables y hover sobre fondo semi-transparente
- **Modales**: overlay con `rgba(0,0,0,0.6)`, panel centrado con `box-shadow: 0 8px 32px rgba(0,0,0,0.6)`
- **Botones**: clases `.btn .btn-primary/.btn-secondary/.btn-ghost/.btn-danger/.btn-sm`
- **Layout**: sidebar fijo 240px + topbar 56px + área de contenido principal. Sin router — navegación por estado `useState`.
- **NomenclatureFieldsModal vs resto**: el modal usa clases `.modal-overlay`, `.modal-panel`, `.modal-wide`, `.modal-header`, `.modal-body`, `.modal-actions`, `.preview-box`, `.fields-grid`, `.apply-section` — **algunas de estas clases no existen en los CSS auditados** (globals/layout/dashboard/components.css). Es probable que estas clases estén sin definir, lo que causaría un aspecto visual inconsistente si el modal se llegara a abrir.

---

## Idioma de la UI

- **Predominantemente español** — labels de navegación, mensajes de usuario, títulos de página, estados.
- **Términos técnicos en inglés** (esperado para el dominio): `Source`, `WEB-DL`, `BluRay`, `BDRemux`, `WEBRip`, `HDTV`, `tag`, `MKV`, `provider`, `preflight`, `VACUUM`.
- **Sin mezcla problemática**: los términos en inglés son invariablemente nombres técnicos del dominio de releases, no traducciones descuidadas.
- **Strings de sistema**: `APLICAR_NOMENCLATURA`, `APLICAR_TITULO_MKV`, `INICIAR_UPLOADRR`, `RESTAURAR_CONFIG`, `MANTENIMIENTO_DB`, `LIMPIAR_LOGS` — todos en mayúsculas, sin idioma forzado.

---

## Gaps encontrados

### 🔴 PRIORIDAD ALTA — NomenclatureFieldsModal no conectada a ninguna página

`NomenclatureFieldsModal` existe en `frontend/src/components/NomenclatureFieldsModal.tsx` pero **ningún archivo la importa ni la usa**. Verificado con `grep -rn "NomenclatureFieldsModal"` → solo aparece en su propia definición.

`LibraryPage` usa `NomenclatureModal` (la anterior, sin campos editables).

**Consecuencias**:
- Los campos editables de nomenclatura (Fase 10A) son **inaccessibles desde la UI**
- El flujo de MKV title es **inaccessible desde la UI**
- La integración TMDb Watch Providers es **inaccessible desde la UI**
- Todo el trabajo backend de Fase 10A (source_assistant, mkv_title, endpoints) está operativo pero sin entrada desde el frontend

### 🔴 PRIORIDAD ALTA — SettingsPage pestaña Configuración es placeholder

La pestaña "Configuración" de Settings no tiene campos editables. Muestra texto estático indicando al usuario que use el setup wizard o la CLI. Esto significa que **no existe una forma UI de modificar las settings una vez completado el setup** (ni TMDb API key, ni emu API key, ni ruta Uploadrr, ni idioma TMDb, ni región TMDb).

### 🔴 PRIORIDAD ALTA — default_release_tag no editable en UI

`default_release_tag` está en la BD (valor inicial `"EMUWAREZ"`) y se usa en `nomenclature.py` y `source_assistant.py`, pero **no hay campo en setup ni en settings** para que el usuario lo cambie.

### 🔴 PRIORIDAD ALTA — provider_priority_order no editable en UI

`provider_priority_order` está en la BD (valor inicial `'["AMZN","NF","DSNP","MAX","ATVP"]'`) y se usa en `source_assistant.py` para sugerir el provider. **No hay campo en setup ni en settings** para que el usuario lo modifique.

### 🔴 PRIORIDAD ALTA — Flujo MKV title no accesible en UI

El backend está completo. El componente UI existe. Pero como `NomenclatureFieldsModal` no está conectado, el usuario no puede ni previsualizar ni aplicar el título interno MKV desde la interfaz.

### 🟡 PRIORIDAD MEDIA — No hay endpoint `/api/settings` para leer/modificar config

No existe `web/api/settings.py`. El único endpoint que lee settings es `GET /api/setup/status` (que devuelve flags booleanos, no los valores). Esto implica que no hay forma de hacer una "settings page" funcional sin crear este endpoint.

### 🟡 PRIORIDAD MEDIA — Clases CSS de NomenclatureFieldsModal posiblemente ausentes

Las clases `.fields-grid`, `.preview-box`, `.apply-section`, `.confirm-input`, `.text-error`, `.text-warning`, `.text-success`, `.text-sm`, `.text-muted` usadas en el modal pueden no estar definidas en los archivos CSS actuales. Requiere verificación antes de conectar el modal.

### 🟢 PRIORIDAD BAJA — TMDb API key no modificable post-setup vía UI

Consecuencia del gap de SettingsPage. La API key de TMDb solo se puede cambiar vía CLI (`maintenance export-settings` + reimport) o reiniciando el setup. Documentada en Docker docs.

---

## Recomendaciones

1. **Conectar NomenclatureFieldsModal a LibraryPage** — en la columna "Acciones", añadir un botón "Editar campos" que abra `NomenclatureFieldsModal` (además del botón "Nomenclatura" existente que abre el modal antiguo). O bien reemplazar el modal antiguo por el nuevo.

2. **Verificar y completar CSS de NomenclatureFieldsModal** — antes de conectarlo, auditar qué clases usa y añadir las que falten en `components.css`.

3. **Implementar Settings editable** — crear `web/api/settings.py` con `GET /api/settings` y `PUT /api/settings` para TMDb key/lang/region, emu key/endpoint, uploadrr path, default_release_tag, provider_priority_order. Conectar la pestaña "Configuración" de SettingsPage.

4. **Añadir default_release_tag y provider_priority_order** al setup wizard (paso TMDb o paso nuevo) y/o a Settings.

5. **Documentar provider_priority_order y default_release_tag** en Docker docs y README.

---

## Siguiente fase propuesta

**Fase 10B — Settings page funcional + NomenclatureFieldsModal conectado**

Objetivos:
1. Crear endpoint `GET/PUT /api/settings` en backend con soporte para: tmdb_api_key, tmdb_language, tmdb_watch_region, emu_api_key, emu_endpoint, uploadrr_path, default_release_tag, provider_priority_order
2. Implementar pestaña "Configuración" en SettingsPage con campos reales (enmascarando secrets en lectura)
3. Conectar `NomenclatureFieldsModal` desde LibraryPage (botón "Editar campos" junto al botón "Nomenclatura")
4. Verificar y completar CSS de NomenclatureFieldsModal
5. Añadir tests para el endpoint de settings y para la integración del modal en la página de biblioteca

Criterios de aceptación:
- El usuario puede cambiar TMDb API key sin reiniciar el setup
- El usuario puede cambiar default_release_tag desde la UI
- El usuario puede cambiar provider_priority_order desde la UI
- El modal de campos editables se abre desde LibraryPage
- El flujo MKV title es accesible desde la UI (previsualizar + aplicar con token)
- 783+ tests pasando
