# Checkpoint — Library poster/grid view milestone (Fase 11E)

| Campo | Valor |
|-------|-------|
| Rama fusionada | `feature/ui-phase-11e-library-poster-grid` |
| Commit de la fase | `75ca8e2` ("feat: library poster/grid view with poster extraction from Radarr/Sonarr") |
| Merge commit | `fd44808` ("merge: library poster/grid view milestone", `--no-ff`, sin conflictos, sobre base `d89f7d0`) |
| Tag | `emuwarez-uploadrr-library-poster-grid-v0` (apunta al merge commit) |
| Tests | 1105 passed, 0 fallos (verificado de nuevo en `master` tras el merge) |
| `npm run build` | OK |
| Push | Ninguno — no hay remote configurado en este repo |

## Resumen de la fase

Quinta sub-fase (11E) de la iteración grande de UI/configuración. Extrae
`poster_url` del array `images[]` que Radarr/Sonarr ya devuelven (guardado
sin parsear en `raw_json` desde hace fases, nunca usado hasta ahora) vía
`integrations/base.py::extract_poster_url()` (prefiere `remoteUrl`, nunca
la variante relativa `url`, para no filtrar la API key de la instancia en
una URL de imagen visible en el cliente). Columna nueva en `library_items`
(migración estándar `ALTER TABLE ADD COLUMN`, `SCHEMA_VERSION` 15→16),
propagada por todo el pipeline (modelo, sync, schema, API).

`LibraryPage.tsx` ahora muestra por defecto una vista de pósters en grid
(toggle a la tabla original sigue disponible), con la preferencia
persistida en `localStorage` — primer uso de esa API para una preferencia
de UI en el proyecto. Todos los filtros/paginación/modales existentes se
mantienen intactos.

Verificado con capturas reales en navegador: pósters de prueba (SVG
`data:` URI, sin depender de red externa) renderizados correctamente en el
grid, icono de marcador de posición para ítems sin póster, miniatura en el
modal de detalle, y persistencia confirmada tras un reload completo de la
página.

Detalle completo: `docs/codex_phase_11e_library_poster_grid_report.md`.

Queda pendiente la Fase 11F (Dashboard, la más grande y última de la
iteración).

## Confirmaciones de seguridad

- Nunca se construye una URL de imagen absoluta a partir del campo `url`
  relativo + API key de la instancia — solo se usa `remoteUrl` (público,
  sin credenciales).
- Los datos de prueba manuales insertados en la base de datos demo durante
  la verificación se revirtieron a `NULL` tras la captura de pantallas.
- Sin push en ningún momento.
