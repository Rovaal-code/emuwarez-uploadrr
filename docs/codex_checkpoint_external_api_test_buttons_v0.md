# Checkpoint — External API Test Buttons v0

## Estado del repo

| Campo | Valor |
|-------|-------|
| Rama mergeada | `feature/ui-phase-10c-external-api-test-buttons` |
| Commit Fase 10C | `3b29c25` |
| Commit fixes post-review | `94b37ec` |
| Merge commit | `e33d675` |
| Tag | `emuwarez-uploadrr-external-api-test-buttons-v0` |
| Rama activa | `master` |
| Git status | Limpio |

## Validaciones ejecutadas

### py_compile
```
OK — todos los .py compilan sin errores
```

### pytest
```
852 passed, 4 warnings
0 failures
```

56 tests nuevos en `tests/test_integration_tests_service.py` y `tests/test_integration_tests_api.py`
(29 + 20 originales de la Fase 10C, + 7 añadidos en la revisión post-implementación).

### npm run build (frontend)
```
✓ 79 módulos transformados
✓ built in ~1-2.5s
0 errores TypeScript
```

### JSON contract
```
python3 -m json.tool docs/ui_backend_contract.json → OK
```

### Docker
No disponible en este entorno de desarrollo local. Dockerfile y docker-compose.example.yml
no fueron modificados en esta fase.

## Archivos principales modificados (Fase 10C)

| Archivo | Cambio |
|---------|--------|
| `emuwarez_uploadrr/services/integration_tests.py` | Nuevo — `test_tmdb_connection`, `test_emuwarez_connection`, `test_arr_connection` |
| `emuwarez_uploadrr/web/api/integration_tests.py` | Nuevo — `POST /api/integrations/test/{tmdb,emuwarez,arr}` |
| `emuwarez_uploadrr/web/schemas.py` | `TestTmdbRequest`, `TestEmuwarezRequest`, `TestArrRequest`, `IntegrationTestResult` |
| `emuwarez_uploadrr/web/api/router.py` | Registra `integration_tests_router` |
| `frontend/src/api/integrationTests.ts` | Nuevo — helpers tipados `testTmdbConnection`, `testEmuwarezConnection`, `testArrConnection` |
| `frontend/src/pages/SettingsPage.tsx` | Botón "Probar conexión" en sección TMDb |
| `frontend/src/pages/SetupWizard.tsx` | Botones en pasos TMDb, eMuwarez e Instancias |
| `frontend/src/pages/InstancesPage.tsx` | Botón "Probar conexión" en formulario de nueva instancia |
| `tests/test_integration_tests_service.py` | Nuevo — tests unitarios del servicio |
| `tests/test_integration_tests_api.py` | Nuevo — tests de los endpoints |

## Fixes aplicados en revisión post-implementación (antes del merge)

1. `POST /api/integrations/test/arr` no soportaba `instance_id` pese a que el servicio ya
   tenía la lógica de lookup de instancia guardada — se conectó en el router y se añadieron tests.
2. `kind` inválido devolvía `200` con `status=invalid_kind` en vez de `422` — el router ahora
   valida antes de llamar al servicio y lanza `HTTPException(422)`.
3. Documentación no actualizada — se añadieron secciones Phase 10C a
   `docs/ui_backend_contract.md`, `docs/ui_backend_contract.json`, `README_CLI_READY.md` y
   notas de troubleshooting en `docs/DEPLOYMENT_DOCKER.md`.

## Funcionalidades incluidas

- Botones "Probar conexión" para TMDb, eMuwarez, Radarr y Sonarr en Settings, SetupWizard e InstancesPage
- Prueba de credenciales guardadas o escritas en formulario sin guardar (nunca se persisten al probar)
- `POST /api/integrations/test/arr` soporta tanto `instance_id` (instancia guardada) como `kind/base_url/api_key` (credenciales sueltas)
- Operaciones exclusivamente de lectura: TMDb `/configuration`, eMuwarez `/api/torrents/filter?perPage=1`, Arr `/api/v3/system/status`
- Estados de respuesta: `connected`, `not_configured`, `invalid_key`, `connection_error`, `timeout`, `invalid_url`, `invalid_kind`, `unexpected_error`

## Garantías de seguridad

- Ningún endpoint devuelve la API key completa en la respuesta
- Las credenciales enviadas solo para test no se guardan
- Los tests de eMuwarez no crean peticiones ni suben torrents
- Radarr/Sonarr solo se prueban vía `system/status` (lectura)
- `Uploadrr` no tiene código en este módulo — excluido explícitamente de la Fase 10C

## Gaps restantes

- Test de conexión para Uploadrr — pospuesto a fase separada por tener flujo/fork propio
- Jellyfin y Seerr — fuera de alcance
- Creación automática de peticiones eMuwarez — bloqueada hasta API oficial

## Confirmaciones

- `Uploadrr/` no fue tocado en ningún momento
- No se ejecutó ninguna subida real ni mkvpropedit real
- No se hizo push al remoto (no hay remoto configurado)
- No se ejecutaron llamadas HTTP reales en los tests (todo mockeado)
- Git status al finalizar: limpio
