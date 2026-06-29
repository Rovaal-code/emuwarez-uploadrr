# Codex Phase 05A — Frontend Vite/React + Setup Wizard + Dashboard

**Rama:** `feature/ui-phase-05a-frontend-dashboard`
**Fecha:** 2026-06-29
**Tests backend:** 141 passed, 0 failed
**Build frontend:** OK — 64 módulos, ~210 KB gzip total

---

## Estructura frontend creada

```
frontend/
├── package.json            # React 18 + TypeScript + Vite 5
├── index.html
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts          # proxy /api → http://localhost:9494
└── src/
    ├── main.tsx            # punto de entrada con StrictMode
    ├── App.tsx             # router de estados: loading/setup/login/app
    ├── api/
    │   ├── client.ts       # fetch wrapper, token localStorage, ApiClientError
    │   ├── auth.ts         # login/logout/me
    │   ├── setup.ts        # 7 pasos del wizard
    │   ├── dashboard.ts    # summary + activity
    │   ├── library.ts      # list + detail + syncAll
    │   ├── instances.ts    # list + add + test + sync
    │   └── missing.ts      # list con paginación
    ├── types/
    │   ├── api.ts          # tipos TS mirroring schemas Pydantic
    │   └── domain.ts       # LocalStatus, RequestStatus, NAV_ITEMS, SETUP_STEPS
    ├── components/
    │   ├── AppShell.tsx    # layout sidebar + topbar + router de páginas
    │   ├── Sidebar.tsx     # navegación izquierda con 9 secciones
    │   ├── Topbar.tsx      # topbar con user info + logout
    │   ├── StatCard.tsx    # tarjeta de estadística reutilizable
    │   ├── StatusBadge.tsx # badge de estado (local/request/nomenclature)
    │   ├── ServiceIcon.tsx # SVG propios para Radarr, Sonarr, EMU, Uploadrr
    │   ├── DataTable.tsx   # tabla genérica con column definitions
    │   ├── EmptyState.tsx  # estado vacío con icono, título, body, acción
    │   ├── LoadingState.tsx # spinner centrado
    │   └── ErrorState.tsx  # error con opción de reintentar
    ├── pages/
    │   ├── LoginPage.tsx   # login oscuro profesional
    │   ├── SetupWizard.tsx # 7 pasos con progress bar y validaciones
    │   ├── DashboardPage.tsx # 5 tarjetas + tabla activity + panel subida
    │   ├── LibraryPage.tsx # tabla filtrable/paginada + detalle modal
    │   ├── MissingPage.tsx # tabla paginada de faltantes
    │   ├── InstancesPage.tsx # tarjetas con test/sync por instancia
    │   ├── RequestsPage.tsx  # placeholder profesional con orden previsto
    │   ├── UploadsPage.tsx   # placeholder
    │   ├── TasksPage.tsx     # placeholder
    │   ├── LogsPage.tsx      # placeholder
    │   └── SettingsPage.tsx  # placeholder con secciones previstas
    ├── utils/
    │   ├── format.ts       # formatBytes, formatDate, formatItemType
    │   └── status.ts       # mapas label+color+cssClass para 3 tipos de estado
    └── styles/
        ├── globals.css     # variables CSS, reset, scrollbar
        ├── layout.css      # sidebar, topbar, app-shell, page-container
        ├── components.css  # cards, buttons, badges, inputs, tables, instance-card
        └── dashboard.css   # stat-card, dashboard-grid, wizard, login, empty-state
```

---

## Diseño visual

- Fondo `#0a0d14` (negro azulado profundo)
- Glassmorphism sutil: `rgba(255,255,255,0.04)` con borde `rgba(59,130,246,0.15)`
- Tipografía Inter/system-ui, 14px base, 13px tablas, 11px badges
- Sidebar 240px fija, Topbar 56px fija
- Grid 5 columnas para stat cards
- Todos los colores semánticos como variables CSS (`--color-available`, `--color-missing`, etc.)
- **ServiceIcon**: SVG propios para Radarr (radar naranja), Sonarr (antena azul), EMU (E morado), Uploadrr (flecha verde)
- Radarr y Sonarr **siempre muestran su icono** junto al texto en tablas y tarjetas

---

## Flujo App.tsx

```
1. GET /api/setup/status (skipAuth)
2. Sin admin → SetupWizard (paso admin)
3. Token existe → GET /api/auth/me
   - Token válido + initialized → AppShell
   - Token válido + !initialized → SetupWizard (next_step)
   - Token inválido → clearToken → LoginPage
4. Sin token → LoginPage
5. LoginPage onSuccess → bootstrap() de nuevo
6. SetupWizard onComplete → bootstrap() de nuevo
```

---

## Páginas implementadas

| Página | Endpoints consumidos | Estado |
|--------|---------------------|--------|
| Login | POST /api/auth/login | Real |
| SetupWizard | POST /api/setup/admin + base + uploadrr + tmdb + emu + instances + complete | Real |
| Dashboard | GET /api/dashboard/summary + /activity | Real |
| Biblioteca | GET /api/library (filtros: type, status, origin, search, paginación) | Real |
| Faltantes | GET /api/missing | Real |
| Instancias | GET/POST /api/instances, /test, /sync | Real |
| Peticiones | — (placeholder profesional con orden previsto) | Placeholder |
| Subidas | — | Placeholder |
| Tareas | — | Placeholder |
| Logs | — | Placeholder |
| Configuración | — | Placeholder |

---

## Endpoints aún como placeholder en el frontend

| Endpoint | Razón |
|----------|-------|
| GET /api/requests | Endpoint eMuwarez real no capturado |
| POST /api/requests/sync | Mismo motivo |
| GET /api/uploads | Lógica de subida Uploadrr pendiente |
| GET /api/tasks | Datos de task_runs no suficientemente ricos aún |
| GET /api/logs | Backend /api/logs pendiente |
| GET /api/config | Backend /api/config pendiente |
| POST /api/library/{id}/upload | Motor heredado no expuesto desde UI |
| POST /api/missing/{id}/create-emu-request | Endpoint real EMU pendiente |

---

## Servicio de estáticos en FastAPI

`emuwarez_uploadrr/web/app.py` modificado:

- Si `frontend/dist/` existe y tiene `index.html`:
  - Monta `/assets` desde `frontend/dist/assets/`
  - Añade catch-all `/{full_path:path}` que sirve `index.html` (SPA)
  - Nunca intercepta rutas `/api/*`
- Si `frontend/dist/` no existe: backend funciona exactamente igual que antes

---

## Dependencias frontend añadidas

| Paquete | Justificación |
|---------|---------------|
| `react` + `react-dom` | Framework UI base |
| `@vitejs/plugin-react` | Transpilación JSX/TSX con Fast Refresh |
| `vite` | Build tool + dev server con proxy |
| `typescript` + `@types/*` | Type safety en toda la aplicación |

No se añadieron librerías de UI (no Tailwind, no Material, no Lucide) — CSS propio completo.

---

## Comandos npm ejecutados

```bash
npm install     # OK
npm run build   # OK — 64 módulos, dist ~210 KB gzip
```

---

## Validaciones ejecutadas

```
python3 -m py_compile emuwarez_uploader.py           → OK
find emuwarez_uploadrr -name "*.py" | xargs py_compile → OK
python3 -m json.tool docs/ui_backend_contract.json   → OK
python3 emuwarez_uploader.py --help                  → OK
python3 emuwarez_uploader.py web info                → OK (incluye sección frontend)
python3 emuwarez_uploader.py web setup-status        → OK
python3 emuwarez_uploader.py instances list          → OK
python3 emuwarez_uploader.py library list            → OK
python3 emuwarez_uploader.py missing list            → OK
pytest -q                                            → 141 passed, 0 failed
npm run build                                        → OK
```

---

## Criterios de aceptación verificados

| Criterio | Estado |
|----------|--------|
| CLI legacy sigue funcionando | ✓ |
| CLI moderna sigue funcionando | ✓ |
| Backend setup/auth sigue funcionando | ✓ |
| Endpoints reales Fase 4 siguen funcionando | ✓ |
| frontend/ con Vite + React + TypeScript | ✓ |
| Login contra /api/auth/login | ✓ |
| Setup wizard consume endpoints reales | ✓ |
| AppShell con sidebar definitiva (9 secciones) | ✓ |
| Dashboard consume /api/dashboard/summary y /activity | ✓ |
| Biblioteca consume /api/library | ✓ |
| Faltantes consume /api/missing | ✓ |
| Instancias consume /api/instances | ✓ |
| Peticiones como pantalla placeholder separada | ✓ |
| Radarr/Sonarr con iconos SVG junto al texto | ✓ |
| Grid estricto, diseño oscuro profesional | ✓ |
| No se usa FormatoEMU ni Añadir formatoEMU | ✓ |
| Se usa Nomenclatura y Adaptar nomenclatura | ✓ |
| npm run build funciona | ✓ |
| pytest pasa | ✓ (141 tests) |
| Uploadrr/ no se toca | ✓ |
| Commit final con mensaje correcto | Pendiente |

---

## Riesgos pendientes

- `StaticFiles` de FastAPI requiere `aiofiles` en producción (incluido en `[web]` extras de fastapi). Verificar que `pip install -e ".[web]"` lo incluye, o añadir `aiofiles` explícitamente al `pyproject.toml`.
- El SPA fallback intercepta todas las rutas no-`/api/*`. Si en el futuro se añaden rutas de archivos estáticos a nivel raíz (favicon, robots.txt, etc.) hay que servirlas explícitamente antes del catch-all.

---

## Siguiente fase recomendada (Phase 5B)

- Conectar GET /api/tasks a TasksPage con datos reales
- Implementar Subidas con SSE para progreso
- Capturar endpoint real eMuwarez → activar RequestsPage
- Añadir SettingsPage con formularios reales de configuración
- Probar UI integración completa con Radarr/Sonarr reales
