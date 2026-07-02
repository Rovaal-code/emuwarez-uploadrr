# Fase 11E — Biblioteca: vista de pósters/grid

Quinta sub-fase de la iteración grande de UI/configuración.

## Estado del repo

| Campo | Valor |
|-------|-------|
| Rama base | `master` (incluye 11A+11B+11C+11D ya mergeadas) |
| Rama de esta fase | `feature/ui-phase-11e-library-poster-grid` |
| Tests previos | 1090 passed |
| Tests tras esta fase | 1105 passed, 0 fallos (1090 + 15 nuevos) |

## Qué se implementó

### Extracción de pósters (backend)

Radarr/Sonarr ya devuelven un array `images` en su JSON crudo por
película/serie (guardado sin parsear en `raw_json` desde hace fases), pero
ningún campo lo extraía. Se añadió:

- `emuwarez_uploadrr/integrations/base.py::extract_poster_url()` — función
  pura, sin red: busca la entrada con `coverType == "poster"` y devuelve su
  `remoteUrl` (una URL pública completa), nunca el campo `url` relativo
  (que normalmente requiere la API key/sesión de la instancia para
  cargarse a través de `/MediaCover/...` — `remoteUrl` es la opción
  portable). Devuelve `None` de forma segura ante cualquier estructura
  inesperada (nunca lanza excepción — es metadata best-effort, no algo que
  deba tumbar la sincronización).
- `models.py::LibraryItem` — nuevo campo `poster_url: Optional[str] = None`.
- `integrations/radarr.py::movie_to_library_item()` y
  `integrations/sonarr.py::series_to_library_item()`/`episode_to_library_item()`
  (este último usa el póster de la serie, ya que los episodios no tienen
  imagen propia) — ahora rellenan `poster_url` vía `extract_poster_url()`.
- `database.py::_migrate_library_items_phase11e()` — nueva columna
  `poster_url TEXT` en `library_items` (patrón `ALTER TABLE ADD COLUMN`
  estándar del proyecto), `SCHEMA_VERSION` 15→16.
- `services/library.py::upsert_library_item()` — columna añadida a la
  lista genérica de INSERT/UPDATE (patrón ya existente, solo extender la
  lista).
- `web/api/library.py`/`web/schemas.py` — `poster_url` añadido a
  `LibraryItemResponse`.

### Vista de pósters (frontend)

- `frontend/src/types/api.ts` — `poster_url` añadido a `LibraryItemResponse`.
- `frontend/src/pages/LibraryPage.tsx`:
  - Nuevo toggle "Pósters" / "Lista" en la cabecera de la página.
  - **Por defecto: vista de pósters** (grid), tal como pedía el encargo.
    La preferencia se persiste en `localStorage`
    (`emuwarez_uploadrr_library_view`) — primer uso de `localStorage` para
    una preferencia de UI en este proyecto (hasta ahora solo se usaba para
    el token de sesión); verificado que sobrevive a un reload completo de
    la página.
  - Vista de pósters: grid responsive (`repeat(auto-fill, minmax(140px,1fr))`),
    cada tarjeta con imagen 2:3, badge de estado superpuesto, título +
    año debajo. Si no hay `poster_url`, se muestra un icono de
    marcador de posición (🎬/📺 según tipo) en vez de un hueco vacío o un
    error de imagen rota.
  - **Todos los filtros (búsqueda, tipo, estado, origen), la paginación y
    los modales existentes (detalle, nomenclatura, campos, subida) se
    mantienen intactos** — el toggle solo cambia cómo se renderiza la
    lista de resultados, nunca la lógica de carga/filtrado.
  - El modal de detalle ahora muestra también una miniatura del póster
    junto al título, si existe.

## Tests

- `tests/test_library_poster_extraction.py` (14): `extract_poster_url()`
  unitario (prefiere `remoteUrl`, ignora entradas sin poster, ignora
  `remoteUrl` vacío/en blanco, tolera listas malformadas, `None`, no-lista),
  `movie_to_library_item`/`series_to_library_item`/`episode_to_library_item`
  rellenan `poster_url` correctamente (o `None` si no hay `images`),
  `sync_instance()` end-to-end persiste `poster_url` en la fila real de
  `library_items`.
- `tests/test_dashboard_library_api.py` — 1 test nuevo:
  `test_library_after_sync_includes_poster_url` confirma que
  `GET /api/library` expone el campo tras una sincronización real (mockeada).

**`pytest -q`**: `1105 passed, 0 failed`.
**`npm run build`**: OK, sin errores de tipos.

## Verificación manual (servidor demo real)

Insertados manualmente 3 pósters de prueba (SVG en `data:` URI, sin
depender de red externa) sobre filas reales de la base de datos demo, y
confirmado en navegador (Playwright):

- La vista de pósters muestra las imágenes reales, y el icono de
  marcador de posición para el elemento sin póster — en la misma
  cuadrícula.
- El modal de detalle muestra la miniatura del póster junto al título.
- El toggle a "Lista" restaura la tabla original sin cambios.
- Tras recargar la página completa (nueva sesión de React, misma
  `localStorage`) y volver a abrir Biblioteca, la vista quedó en modo
  "Lista" — confirma que la preferencia persiste correctamente.
- Los datos de prueba (pósters SVG manuales) se revirtieron a `NULL`
  después de la verificación, para no dejar datos falsos en la base de
  datos de demo persistente.

## Gaps / limitaciones conocidas

- Solo se extrae `remoteUrl`; si una instancia Radarr/Sonarr real solo
  expone la variante relativa `url` (sin `remoteUrl`), el póster quedará
  en blanco (icono de marcador de posición) en vez de intentar construir
  una URL absoluta con la API key de la instancia. Esto evita filtrar la
  API key de la instancia en una URL de imagen cliente-visible; documentado
  como decisión de diseño deliberada, no un descuido.
- No existe ningún fixture de test en el repo que confirme la estructura
  exacta de `images[]` contra un Radarr/Sonarr real — la implementación
  sigue el contrato documentado de la API v3 de ambos proyectos.
- Queda pendiente la Fase 11F (Dashboard, la más grande).
