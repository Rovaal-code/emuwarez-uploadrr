# Fase 10C — Botones "Probar conexión" para APIs externas

## Resumen

Implementación de botones "Probar conexión" para TMDb, eMuwarez, Radarr y Sonarr.
Uploadrr queda completamente fuera de esta fase.

## Archivos creados

| Archivo | Tipo | Descripción |
|---------|------|-------------|
| `emuwarez_uploadrr/services/integration_tests.py` | Backend — servicio | Funciones de test: `test_tmdb_connection`, `test_emuwarez_connection`, `test_arr_connection` |
| `emuwarez_uploadrr/web/api/integration_tests.py` | Backend — endpoints | `POST /api/integrations/test/{tmdb,emuwarez,arr}` |
| `frontend/src/api/integrationTests.ts` | Frontend — API helper | `testTmdbConnection`, `testEmuwarezConnection`, `testArrConnection` |
| `tests/test_integration_tests_service.py` | Tests | 29 tests unitarios del servicio (HTTP mockeado) |
| `tests/test_integration_tests_api.py` | Tests | 20 tests de API (servicio mockeado) |

## Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `emuwarez_uploadrr/web/schemas.py` | Nuevos schemas: `TestTmdbRequest`, `TestEmuwarezRequest`, `TestArrRequest`, `IntegrationTestResult` |
| `emuwarez_uploadrr/web/api/router.py` | Registra `integration_tests_router` |
| `frontend/src/pages/SettingsPage.tsx` | Botón "Probar conexión" + resultado en sección TMDb de ConfigTab |
| `frontend/src/pages/SetupWizard.tsx` | Botones en steps TMDb, EMU e Instances |
| `frontend/src/pages/InstancesPage.tsx` | Botón "Probar conexión" en formulario de añadir instancia (credenciales no guardadas) |

## Endpoints implementados

### `POST /api/integrations/test/tmdb`
```json
// Request (todos opcionales — si omites api_key usa la guardada en DB)
{ "api_key": "...", "language": "es-ES", "region": "ES" }

// Response
{ "ok": true, "service": "tmdb", "status": "connected", "message": "Conexión correcta", "details": {"http_status": 200} }
```

### `POST /api/integrations/test/emuwarez`
```json
// Request
{ "api_key": "...", "base_url": "https://emuwarez.com" }

// Response
{ "ok": false, "service": "emuwarez", "status": "invalid_key", "message": "API key inválida", "details": {} }
```

### `POST /api/integrations/test/arr`
```json
// Request (todos requeridos — no guarda nada)
{ "kind": "radarr", "base_url": "http://192.168.1.10:7878", "api_key": "..." }

// Response
{ "ok": true, "service": "radarr", "status": "connected", "message": "Conexión correcta", "details": {"version": "5.3.6"} }
```

## Valores de status posibles

| Status | Significado |
|--------|-------------|
| `connected` | Conexión exitosa |
| `not_configured` | Credencial vacía o no configurada |
| `invalid_key` | HTTP 401/403 — API key incorrecta |
| `connection_error` | Error de red o HTTP inesperado |
| `timeout` | Timeout al conectar |
| `invalid_url` | URL malformada (eMuwarez) |
| `invalid_kind` | Tipo ARR desconocido (solo radarr/sonarr) |
| `unexpected_error` | Excepción no esperada |

## Garantías de seguridad

- Ningún endpoint devuelve la API key completa en la respuesta
- Las credenciales enviadas en el cuerpo de la petición de test no se guardan
- Los tests de eMuwarez no crean peticiones ni suben torrents
- Los tests de Radarr/Sonarr solo llaman a `/api/v3/system/status` (lectura)
- Uploadrr no tiene ningún código en este módulo
- `test_connection` en eMuwarez usa `GET /api/torrents/filter?perPage=1` (solo lectura)

## Validaciones ejecutadas

### py_compile
```
OK — todos los .py compilaron sin errores
```

### pytest (suite completa)
```
845 passed, 4 warnings
0 failures
+49 tests nuevos (29 servicio + 20 API)
```

### npm run build
```
✓ 79 módulos transformados (+1 respecto a Fase 10B)
✓ built in ~1.0s
0 errores TypeScript
```

## UX implementada

- **SettingsPage / TMDb**: Botón "Probar conexión" bajo el campo de nueva API key. Si hay texto en el campo usa esa key, si no usa la guardada. Muestra: ✓ Conectado / ✗ API key inválida / ⚠ Sin configurar / ✗ No se pudo conectar. No guarda nada.
- **SetupWizard / TMDb**: Botón antes del botón "Continuar". Usa los valores del formulario.
- **SetupWizard / EMU**: Botón antes del botón "Continuar". Usa los valores del formulario.
- **SetupWizard / Instances**: Botón "Probar conexión" junto al botón "+ Añadir instancia". Usa el borrador actual del formulario. Muestra versión si disponible.
- **InstancesPage / Add form**: Botón "Probar conexión" junto al botón "Añadir". Prueba las credenciales del formulario sin guardarlas.

## Confirmaciones

- `Uploadrr/` no fue modificado
- No se ejecutó ninguna subida real
- No se ejecutó mkvpropedit real
- No se hizo push al remoto
- No se ejecutaron llamadas HTTP reales en los tests (todo mockeado)
- Git status al finalizar: pendiente de commit
