# Reporte de ejecución — Fase 3
## Setup inicial backend real + autenticación básica

**Fecha:** 2026-06-28
**Rama:** feature/ui-phase-03-setup-auth

---

## Rama usada

```
feature/ui-phase-03-setup-auth
```

Creada desde `feature/ui-phase-02-backend-base`.

---

## Archivos creados

| Archivo | Descripción |
|---|---|
| `emuwarez_uploadrr/web/security.py` | Hashing de contraseñas (PBKDF2-SHA256) + tokens opacos |
| `emuwarez_uploadrr/web/dependencies.py` | `get_current_user`, `require_auth` (FastAPI `Depends`) |
| `emuwarez_uploadrr/web/services/__init__.py` | Paquete de servicios web |
| `emuwarez_uploadrr/web/services/auth_service.py` | Usuarios, sesiones, autenticación |
| `emuwarez_uploadrr/web/services/settings_service.py` | Tabla `settings` con enmascarado de secretos |
| `emuwarez_uploadrr/web/services/setup_service.py` | Orquestación del setup wizard |
| `emuwarez_uploadrr/web/api/auth.py` | `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout` |
| `tests/conftest.py` | Fixtures compartidas: `isolated_db`, `client`, `admin_token`, `auth_headers` |
| `tests/test_setup_auth.py` | Suite de 40 tests para Fase 3 |
| `docs/codex_phase_03_setup_auth_report.md` | Este reporte |

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `emuwarez_uploadrr/database.py` | Schema v3: tablas `users`, `auth_sessions`, `settings`; `db_path()` dinámico (respeta `CONFIG_DIR` env var en tiempo de llamada) |
| `emuwarez_uploadrr/web/schemas.py` | Añadidos 14 modelos Pydantic para auth, setup, settings, instancias |
| `emuwarez_uploadrr/web/api/setup.py` | Reescrito: `GET /api/setup/status` real + 7 endpoints POST del wizard |
| `emuwarez_uploadrr/web/api/placeholders.py` | Todos los endpoints sensibles protegidos con `Depends(require_auth)` |
| `emuwarez_uploadrr/web/api/router.py` | Incluye el nuevo `auth_router` |
| `emuwarez_uploadrr/cli.py` | Añadidos `web setup-status`, `web create-admin --username`, `cmd_web_setup_status()`, `cmd_web_create_admin()`, `cmd_web_info()` extendido |
| `tests/test_web_app.py` | Actualizado: protected endpoints esperan 401 sin token, 200 con token |
| `README_CLI_READY.md` | Sección de Setup y autenticación añadida |

---

## Módulo de seguridad (`web/security.py`)

| Función | Descripción |
|---|---|
| `validate_password_strength(pw)` | Mínimo 12 caracteres, minúscula, mayúscula, dígito, símbolo. Devuelve mensaje de error o `None`. |
| `hash_password(pw)` | `pbkdf2_sha256$210000$<salt_b64>$<hash_b64>` — salt aleatorio con `secrets.token_bytes(32)` |
| `verify_password(pw, hash)` | Comparación con `hmac.compare_digest` — protege contra timing attacks |
| `create_token()` | `secrets.token_urlsafe(48)` — 64+ caracteres, criptográficamente seguro |
| `hash_token(token)` | SHA-256 hex del token claro — lo único guardado en BD |
| `verify_token(token, hash)` | `hmac.compare_digest` — comparación constante |

---

## Flujo de autenticación

```
1. Usuario llama POST /api/setup/admin  →  se crea usuario admin (solo antes de que exista)
2. Usuario llama POST /api/auth/login   →  recibe token CLARO (64+ chars, urlsafe)
3. Para todas las rutas protegidas:      →  Authorization: Bearer <token>
4. El servidor busca SHA-256(token) en auth_sessions
5. Si se encuentra y no está revocado   →  devuelve la petición
6. POST /api/auth/logout                →  marca revoked_at en auth_sessions
```

**Regla de seguridad cumplida:** El token claro NUNCA se guarda en la base de datos.  
El test `test_token_not_stored_as_clear` lo verifica explícitamente.

---

## Endpoints implementados

### Setup wizard

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/api/setup/status` | No | Estado completo del wizard con `next_step` |
| `POST` | `/api/setup/admin` | No | Crear primer usuario admin (bloqueado si ya existe) |
| `POST` | `/api/setup/base` | Sí | Nombre de la app y zona horaria |
| `POST` | `/api/setup/uploadrr` | Sí | Ruta del directorio Uploadrr |
| `POST` | `/api/setup/tmdb` | Sí | API key de TMDb |
| `POST` | `/api/setup/emu` | Sí | API key de eMuwarez + endpoint opcional |
| `POST` | `/api/setup/instances` | Sí | Añadir instancia Radarr/Sonarr (con `is_4k`, `is_anime`) |
| `POST` | `/api/setup/complete` | Sí | Finalizar setup → `initialized=true` en `app_state` |

### Autenticación

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `POST` | `/api/auth/login` | No | Devuelve token claro. Requiere credenciales válidas |
| `GET` | `/api/auth/me` | Sí | Usuario autenticado actual |
| `POST` | `/api/auth/logout` | Sí | Revoca el token activo |

### Orden de pasos del wizard (`next_step`)

```
admin → base → uploadrr → tmdb → emu → instances → complete → null (done)
```

---

## Schema SQLite v3

Tablas nuevas:

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,          -- pbkdf2_sha256$...
    role          TEXT NOT NULL DEFAULT 'admin',
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT
);

CREATE TABLE auth_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT UNIQUE NOT NULL,     -- SHA-256 hex del token claro
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at  TEXT,
    revoked_at  TEXT,
    user_agent  TEXT,
    ip_address  TEXT
);

CREATE TABLE settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    is_secret  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Columnas añadidas a `instances` (migracion idempotente via `ALTER TABLE ... IF NOT EXISTS`):

```sql
is_4k          INTEGER NOT NULL DEFAULT 0
is_anime       INTEGER NOT NULL DEFAULT 0
last_test_status TEXT
last_test_at     TEXT
```

---

## Enmascarado de secretos

Las respuestas de la API para secretos siempre devuelven:

```json
{
  "configured": true,
  "masked_value": "abcd…wxyz"
}
```

Si el valor tiene más de 8 caracteres, se muestra `primeros_4…últimos_4`.  
Si tiene 8 o menos, se muestra `****`.  
Los secretos (`tmdb.api_key`, `emu.api_key`, `emu.endpoint_url`) se marcan con `is_secret=1` en la tabla `settings`.

---

## Comandos CLI añadidos

| Comando | Descripción |
|---|---|
| `python3 emuwarez_uploader.py web setup-status` | Muestra estado del wizard en tabla de terminal |
| `python3 emuwarez_uploader.py web create-admin --username <name>` | Crea el usuario admin (pide contraseña por consola, o lee `EMUWAREZ_ADMIN_PASSWORD`) |

---

## Validaciones ejecutadas

| Validación | Resultado |
|---|---|
| `find emuwarez_uploadrr tests -name "*.py" \| xargs python3 -m py_compile` | ✓ OK (todos compilan) |
| `.venv/bin/pytest tests/test_setup_auth.py -v` | ✓ **40/40 passed** |
| `.venv/bin/pytest tests/test_web_app.py -v` | ✓ **29/29 passed** |
| `.venv/bin/pytest tests/ -q` | ✓ **69/69 passed** |
| `python3 emuwarez_uploader.py web info` | ✓ Muestra endpoints actualizados |
| `python3 emuwarez_uploader.py web setup-status` | ✓ Muestra estado del wizard |
| `EMUWAREZ_ADMIN_PASSWORD=... python3 emuwarez_uploader.py web create-admin --username admin` | ✓ Crea usuario |
| Contraseña débil → `create-admin` | ✓ Rechazada con código 1 |
| `python3 emuwarez_uploader.py --help` (legacy) | ✓ Legacy intacto |

---

## Reglas de seguridad cumplidas

| Regla | Verificado |
|---|---|
| No contraseñas en texto plano | ✓ PBKDF2-SHA256 con salt |
| Salt aleatorio `secrets.token_bytes` | ✓ 32 bytes por hash |
| Mínimo 210 000 iteraciones | ✓ `_ITERATIONS = 210_000` |
| Comparación con `hmac.compare_digest` | ✓ En `verify_password` y `verify_token` |
| Token aleatorio `secrets.token_urlsafe(48)` | ✓ `create_token()` |
| Solo hash del token en SQLite | ✓ SHA-256 hex en `auth_sessions.token_hash` |
| Token claro devuelto solo en login | ✓ Solo en `POST /api/auth/login` |
| `Authorization: Bearer <token>` | ✓ En todas las rutas protegidas |
| Revocar token en logout | ✓ `revoked_at = CURRENT_TIMESTAMP` |
| No guardar tokens claros en BD | ✓ Test `test_token_not_stored_as_clear` |
| Responses con `masked_value` para secretos | ✓ `settings_service.mask_secret()` |
| Nunca registrar secretos en logs | ✓ No hay `print()` ni `logging` de secretos |
| Contraseña mínimo 12 chars + lower+upper+digit+symbol | ✓ `validate_password_strength()` |

---

## Estado de Uploadrr

- No se tocó ningún archivo dentro de `Uploadrr/`.
- `Uploadrr/` sigue ignorado por `.gitignore`.

---

## Riesgos pendientes

| Riesgo | Detalle | Fase |
|---|---|---|
| Expiración de sesiones | `auth_sessions.expires_at` existe en schema pero no se aplica todavía | 4 |
| Un solo usuario admin | Aún no hay soporte para múltiples usuarios ni roles | 4 |
| Endpoint GET `/api/auth/me` devuelve 401 sin token (esperado en Phase 2 tests) | Phase 2 tests actualizados | — |
| Instancia con `is_4k`/`is_anime` no se filtra en `GET /api/setup/status` | Los flags están en BD; la UI los mostrará en Fase 4 | 4 |
| Verificación real de API keys TMDb/eMuwarez en setup | Se guardan sin validar | 5 |
| Endpoint de creación de petición EMU | Stub bloqueado explícitamente. Sin cambios | final |

---

## Siguiente fase recomendada — Fase 4: Dashboard + Biblioteca

**Objetivo:** Implementar endpoints reales de biblioteca y dashboard.

**Tareas principales:**
1. `GET /api/instances` — listar instancias reales de la BD.
2. `POST /api/instances`, `DELETE /api/instances/{id}`, `POST /api/instances/{id}/test`.
3. `POST /api/sync/library` — sincronizar biblioteca via Radarr/Sonarr.
4. `GET /api/library` — listar con filtros (`status`, `request`, `nomenclature`, `search`, `page`).
5. `GET /api/library/{id}` — detalle de un ítem.
6. `GET /api/dashboard/summary` — contadores reales.
7. `GET /api/tasks` — listar tareas.
8. Tests completos de estos endpoints.

**Rama:** `feature/ui-phase-04-dashboard-library`
**Commit:** `feat: add dashboard and library real endpoints`

---

## Criterios de aceptación de Fase 3

```text
[x] security.py con hash_password/verify_password/create_token/hash_token/verify_token
[x] pbkdf2_sha256 con 210000 iteraciones y salt aleatorio
[x] hmac.compare_digest en todas las comparaciones sensibles
[x] Tabla users en schema v3
[x] Tabla auth_sessions en schema v3 (guarda solo hash del token)
[x] Tabla settings en schema v3
[x] Columnas is_4k/is_anime/last_test_status/last_test_at en instances (idempotente)
[x] db_path() dinámico respetando CONFIG_DIR en tiempo de llamada
[x] POST /api/setup/admin — crea admin, bloqueado si ya existe (409)
[x] POST /api/setup/base, /uploadrr, /tmdb, /emu, /instances, /complete
[x] next_step: admin → base → uploadrr → tmdb → emu → instances → complete → null
[x] POST /api/auth/login — devuelve token claro
[x] GET /api/auth/me — requiere Bearer token
[x] POST /api/auth/logout — revoca token
[x] Todos los placeholders sensibles protegidos con require_auth (401 sin token)
[x] CLI: web setup-status
[x] CLI: web create-admin --username (getpass o EMUWAREZ_ADMIN_PASSWORD)
[x] CLI: web info actualizado con endpoints de auth y setup
[x] tests/conftest.py con isolated_db (autouse), client, admin_token, auth_headers
[x] tests/test_setup_auth.py — 40 tests
[x] tests/test_web_app.py actualizado — 29 tests
[x] Total: 69/69 tests pasan
[x] Uploadrr/ no se tocó
[ ] Commit final feat: add setup and local authentication backend ← pendiente
```
