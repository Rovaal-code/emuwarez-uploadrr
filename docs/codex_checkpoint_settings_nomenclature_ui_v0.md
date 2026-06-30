# Checkpoint — Settings y Nomenclatura UI v0

## Estado del repo

| Campo | Valor |
|-------|-------|
| Rama mergeada | `feature/ui-phase-10b-settings-and-nomenclature-modal` |
| Commit Fase 10B | `171f42c` |
| Merge commit | `0b4c3e6` |
| Tag | `emuwarez-uploadrr-settings-nomenclature-ui-v0` |
| Rama activa | `master` |
| Git status | Limpio |

## Validaciones ejecutadas

### py_compile
```
OK — todos los .py compilan sin errores
```

### pytest
```
796 passed, 4 warnings
0 failures
```

13 tests nuevos en `tests/test_settings_api.py`.

### npm run build (frontend)
```
✓ 78 módulos transformados
✓ built in ~2.6s
0 errores TypeScript
```

### Docker
No disponible en este entorno de desarrollo local.
El Dockerfile y docker-compose.example.yml no fueron modificados en esta fase.
Las variables de entorno y volúmenes no cambiaron.

### JSON contract
```
python3 -m json.tool docs/ui_backend_contract.json → OK
```

## Archivos principales modificados (Fase 10B)

| Archivo | Cambio |
|---------|--------|
| `emuwarez_uploadrr/web/api/settings.py` | Nuevo — GET/PUT /api/settings |
| `emuwarez_uploadrr/web/api/router.py` | Registra settings_router |
| `emuwarez_uploadrr/web/api/setup.py` | setup/tmdb persiste language y region |
| `emuwarez_uploadrr/web/schemas.py` | SetupTmdbRequest acepta language y region opcionales |
| `emuwarez_uploadrr/web/services/setup_service.py` | setup_tmdb persiste tmdb_language y tmdb_watch_region |
| `frontend/src/api/settings.ts` | Nuevo — fetchSettings(), updateSettings() |
| `frontend/src/api/client.ts` | Añade api.put() |
| `frontend/src/pages/SettingsPage.tsx` | ConfigTab funcional con formulario real |
| `frontend/src/pages/LibraryPage.tsx` | Importa y conecta NomenclatureFieldsModal |
| `frontend/src/styles/components.css` | Clases modal-panel, fields-grid, preview-box, confirm-input, etc. |
| `tests/test_settings_api.py` | Nuevo — 13 tests para settings API |
| `docs/codex_phase_10b_flow_visual_setup_audit.md` | Reporte de auditoría 10B |
| `docs/codex_phase_10b_settings_nomenclature_modal_report.md` | Reporte de implementación 10B |

## Funcionalidades incluidas

- **SettingsPage funcional** — la pestaña "Configuración" dejó de ser un placeholder
- **GET /api/settings** — devuelve settings editables sin secretos completos
- **PUT /api/settings** — actualiza settings con validación
- **TMDb API key editable con masking seguro** — solo se muestra enmascarada, nunca completa
- **PUT con key vacía conserva la existente** — campo vacío = no sobreescribir
- **default_release_tag editable** desde UI
- **provider_priority_order editable como CSV** con validación de códigos y duplicados
- **tmdb_watch_region editable** desde UI
- **tmdb_language editable y persistido** desde UI y desde el setup wizard
- **Setup wizard actualizado** — POST /api/setup/tmdb ahora persiste language y region
- **NomenclatureFieldsModal conectado desde LibraryPage** — era dead code en Fase 10A
- **Botón "Campos" por fila** en la tabla de biblioteca
- **Botón "Editar campos" en detail panel** del ítem
- **Provider dropdown con providers TMDb marcados** (★ cuando tmdb_available=true)
- **Flujo MKV title accesible desde modal** — ya estaba en el componente, ahora es alcanzable
- **Apply MKV title exige APLICAR_TITULO_MKV** — botón deshabilitado hasta token exacto

## Garantías de seguridad

- `GET /api/settings` nunca devuelve `tmdb_api_key` completa
- `tmdb_api_key_masked` es siempre un fragmento enmascarado o null
- `PUT /api/settings` con `tmdb_api_key` vacío o null no modifica la key existente
- La key no aparece en logs ni en respuestas de error
- `NomenclatureFieldsModal`: MKV apply solo se habilita con token `APLICAR_TITULO_MKV` exacto
- `source_path` no es modificado por ningún flujo de esta fase

## Gaps restantes

- Creación automática de peticiones eMuwarez — bloqueada hasta API oficial
- Jellyfin — fuera de alcance
- Seerr — fuera de alcance
- Subida real — requiere flujo confirmado en entorno controlado
- `default_release_tag` aún no se inyecta como valor por defecto en `build_editable_nomenclature_fields` (gap menor para Fase 10C)
- Providers TMDb disponibles muestran `★` en el select pero no el badge verde `.badge-tmdb` visual (mejora menor)

## Confirmaciones

- `Uploadrr/` no fue tocado en ningún momento
- No se ejecutó ninguna subida real
- No se ejecutó mkvpropedit real (solo en tests mockeados)
- No se hizo push al remoto
- Git status al finalizar: limpio
