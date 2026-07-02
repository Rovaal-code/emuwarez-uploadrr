# Fase 11C — Wizard de onboarding de primer arranque

Tercera sub-fase de la iteración grande de UI/configuración (ver
`docs/codex_phase_11a_settings_overhaul_report.md` para contexto y
roadmap). Cubre únicamente el wizard de setup.

## Estado del repo

| Campo | Valor |
|-------|-------|
| Rama base | `master` (limpia, incluye Fases 11A+11B ya mergeadas) |
| Rama de esta fase | `feature/ui-phase-11c-onboarding-wizard` |
| Tests previos | 1039 passed |
| Tests tras esta fase | 1054 passed, 0 fallos (1039 + 15 nuevos) |

## Contexto importante: el wizard ya existía

A diferencia de lo que el encargo original sugería ("the app appears to
provide demo credentials or skips initial configuration"), el wizard de
7 pasos (admin/base/uploadrr/tmdb/emu/instances/complete) **ya existía y
funcionaba** — verificado en la Fase 11 anterior que las credenciales
"demo" vistas por el usuario las creé yo manualmente por curl para
capturas de pantalla, no un comportamiento de la app. Esta fase es una
**ampliación** del wizard existente, no una reconstrucción desde cero.

## Qué se implementó

1. **Nuevo paso "Bienvenida"** (primer paso, solo frontend, sin llamada
   API): explica qué hace la app (sincronizar bibliotecas, conectar con
   Emuwarez, detectar peticiones, preparar/subir con nomenclatura,
   hardlinks opcionales).
2. **Reordenación de pasos** para seguir el orden pedido: Bienvenida →
   Admin → Base → **eMuwarez** → Instancias → **Seerr (nuevo)** → TMDb →
   Uploadrr → **Nomenclatura y hardlinks (nuevo)** → Completar. (Antes:
   Admin→Base→Uploadrr→TMDb→eMuwarez→Instancias→Completar.)
   `web/services/setup_service.py::next_step()` actualizado para el nuevo
   orden de reanudación; los 40 tests existentes de `test_setup_auth.py`
   siguen pasando sin cambios (el orden de comprobación no afecta a sus
   aserciones).
3. **Paso Seerr** (opcional/omitible): URL + API key + probar conexión
   (reutiliza el cliente de la Fase 11B), muestra el usuario detectado.
   No bloquea `next_step()` ni `setup_complete()` — mismo tratamiento que
   ya tenían las instancias Radarr/Sonarr antes de esta fase.
4. **Paso "Nomenclatura y hardlinks"** (nuevo, opcional/omitible):
   etiqueta de subida (`default_release_tag`) + directorio de hardlinks
   (`hardlink_base` — **esta era una settings existente sin NINGUNA UI
   para configurarla en todo el proyecto**, ni en el wizard ni en
   Settings, hasta ahora) + checkbox "No usar hardlinks" que exige
   escribir el token exacto `DESACTIVAR_HARDLINKS` antes de poder
   continuar (mismo patrón de confirmación que `INICIAR_UPLOADRR`/
   `APLICAR_NOMENCLATURA`/etc.). Persiste el nuevo setting
   `nomenclature.use_hardlinks` (`"true"`/`"false"`, por defecto `true`).
5. **Paso eMuwarez — advertencia de omisión explícita**: si el usuario
   intenta continuar sin haber probado la key con éxito, aparece un aviso
   claro explicando las consecuencias y exige marcar una casilla
   "Entiendo, continuar sin verificar" antes de habilitar "Continuar".
   Antes se podía continuar en silencio sin ningún aviso.
6. **Paso TMDb**: región e idioma ahora son `<select>` (reutiliza
   `constants/regionLanguage.ts` de la Fase 11A) en vez de texto libre;
   el placeholder de la API key ya no sugería "sk-" (ya estaba limpio en
   este paso concreto, a diferencia del de Settings que sí se corrigió en
   11A).
7. **Bug real corregido**: `frontend/src/api/setup.ts::setupInstances()`
   enviaba `POST /api/setup/instances` con el cuerpo `{ instances: [...] }`
   (un array envuelto), pero el endpoint siempre esperó **una sola
   instancia por llamada** (`{type, name, url, api_key}` plano) — todos
   los tests de backend ya llamaban así, uno a uno. Con el código
   anterior, añadir cualquier instancia en el wizard habría fallado con
   422 en producción real (nunca se detectó porque no había tests E2E de
   frontend). Corregido: `setupInstances()` ahora hace un `POST` por cada
   instancia del array, en lugar de envolverlas.

## Backend — detalle

- `web/services/setup_service.py`: `get_setup_state()` calcula
  `seerr_configured` real (antes siempre `False`); `next_step()`
  reordenado; nuevas `setup_seerr()` y `setup_nomenclature()` +
  `NOMENCLATURE_DISABLE_HARDLINKS_TOKEN = "DESACTIVAR_HARDLINKS"`.
- `web/schemas.py`: `SetupSeerrRequest`, `SetupNomenclatureRequest`.
- `web/api/setup.py`: `POST /setup/seerr`, `POST /setup/nomenclature`
  (valida la confirmación exacta si `use_hardlinks=False`, 400 si falta o
  es incorrecta).

## Frontend — detalle

- `types/domain.ts`: `SETUP_STEPS`/`SETUP_STEP_LABELS` con los 10 pasos.
- `api/setup.ts`: fix de `setupInstances()` (bucle en vez de wrapper),
  nuevas `setupSeerr()`/`setupNomenclature()`.
- `pages/SetupWizard.tsx`: reescrito con los pasos nuevos/reordenados,
  advertencia de omisión en eMuwarez, dropdowns TMDb, checkbox+confirmación
  de hardlinks.

## Tests

- `tests/test_setup_wizard_phase11c.py` (15): orden nuevo de `next_step()`
  paso a paso, Seerr no bloquea reanudación ni completar, endpoint
  nomenclatura (uso por defecto sin confirmación, desactivar sin
  confirmación→400, confirmación incorrecta→400, confirmación
  correcta→persiste), persistencia real de `hardlink_base` y
  `nomenclature.use_hardlinks` en la tabla `settings`, flujo completo end
  to end con el nuevo orden incluyendo Seerr y nomenclatura.
- `tests/test_setup_auth.py` (40, preexistentes): siguen pasando sin
  modificar — confirma que la reordenación no rompió nada.

**`pytest -q`**: `1054 passed, 0 failed`.
**`npm run build`**: OK, sin errores de tipos.

## Verificación manual (end-to-end real, no mockeada)

Arrancado un servidor con una base de datos completamente nueva (sin admin)
y recorrido el wizard completo en un navegador real controlado por
Playwright, paso a paso, incluyendo:
- Bienvenida → crear admin (auto-login) → base.
- eMuwarez: se confirmó que el botón "Continuar" queda deshabilitado hasta
  marcar la casilla de omisión cuando no se ha probado la key.
- Instancias: se añadió una instancia Radarr real (confirma el fix del
  bug de `setupInstances`).
- Seerr: omitido con el botón "Omitir".
- TMDb: dropdowns de región/idioma confirmados visualmente.
- Uploadrr → Nomenclatura: se marcó "No usar hardlinks", se confirmó que
  "Continuar" queda deshabilitado hasta escribir
  `DESACTIVAR_HARDLINKS` exacto, y tras escribirlo se pudo continuar.
- Completar setup → aterrizaje real en el Dashboard.
- Verificado por API tras completar: `initialized: true`, todos los pasos
  reflejados correctamente, `seerr_configured: false` (se omitió).

## Gaps / limitaciones conocidas

- El modo "no usar hardlinks" **solo persiste la preferencia**
  (`nomenclature.use_hardlinks=false`); no se implementó el motor
  alternativo que renombraría el archivo original in situ. Implementarlo
  requeriría tocar una invariante de seguridad usada en varios sitios del
  proyecto ("nunca modificar el archivo original de la biblioteca") — es
  un cambio de arquitectura grande y deliberadamente fuera de alcance de
  esta fase (el encargo original solo pedía "Store this preference").
- Sincronización de peticiones desde Seerr sigue sin implementar (fuera de
  alcance, acordado en la Fase 11B).
- Quedan las fases 11D (Tareas automáticas/scheduler), 11E
  (Biblioteca/pósters) y 11F (Dashboard).
