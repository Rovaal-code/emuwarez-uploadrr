# Fase 10B — Settings funcional + NomenclatureFieldsModal conectado

## Rama usada

`feature/ui-phase-10b-settings-and-nomenclature-modal`

## Endpoints settings creados

| Método | Ruta | Auth |
|--------|------|------|
| GET | `/api/settings` | Bearer |
| PUT | `/api/settings` | Bearer |

Implementados en `emuwarez_uploadrr/web/api/settings.py` y registrados en `web/api/router.py`.

## SettingsPage funcional

La pestaña **Configuración** dejó de ser un placeholder. Ahora renderiza un formulario real con:

- Estado de la TMDb API key (configurada / no configurada + valor enmascarado)
- Campo para introducir nueva TMDb API key (campo vacío = no sobreescribir)
- Región TMDb (`tmdb_watch_region`)
- Idioma TMDb (`tmdb_language`)
- Default release tag (`default_release_tag`)
- Orden de providers (`provider_priority_order`) — campo CSV con validación backend

## Campos editables implementados

- `default_release_tag` — texto libre, no vacío
- `provider_priority_order` — lista de códigos, sin duplicados, solo códigos EMU válidos
- `tmdb_watch_region` — código ISO de país
- `tmdb_language` — código de idioma
- `tmdb_api_key` — opcional, vacío = mantener la existente

## Tratamiento seguro de TMDb API key

- `GET /api/settings` nunca devuelve la key completa
- Solo devuelve `tmdb_api_key_configured: bool` y `tmdb_api_key_masked: str | null`
- `PUT /api/settings` con `tmdb_api_key` vacío o null no borra la key existente
- La key no se imprime en logs

## Setup wizard actualizado

`POST /api/setup/tmdb` ahora acepta `language` y `region` opcionales además de `api_key`.
`setup_service.setup_tmdb` persiste `tmdb_language` y `tmdb_watch_region` desde el wizard.

## Conexión de NomenclatureFieldsModal

El componente `NomenclatureFieldsModal` (Fase 10A, `frontend/src/components/`) ya existía
completo pero sin ser importado en ninguna página.

**Conectado desde:** `LibraryPage`

- Nuevo botón **"Campos"** por cada fila de la tabla de biblioteca
- Botón **"Editar campos"** en el panel de detalle del ítem
- Estado `fieldsItem` gestiona qué ítem tiene el modal abierto
- `onSaved` recarga la lista de biblioteca

## Flujo MKV title desde UI

Ya estaba implementado dentro de `NomenclatureFieldsModal`. Al conectar el modal la sección
"Título interno MKV" quedó accesible para el usuario:

- Botón "Previsualizar MKV" — `GET /api/library/{id}/mkv-title/preview` (dry_run)
- Botón "Aplicar título MKV" — deshabilitado hasta que el usuario escriba `APLICAR_TITULO_MKV`
- El campo de confirmación exige el token exacto antes de habilitar el botón

## CSS añadido

Clases añadidas a `frontend/src/styles/components.css`:

- `.modal-panel`, `.modal-wide`, `.modal-close`
- `.modal-actions`
- `.fields-grid` (grid 2 columnas para los campos del modal)
- `.preview-box`, `.preview-ok`, `.preview-error`
- `.apply-section`, `.confirm-input`
- `.text-error`, `.text-success`, `.text-warning`, `.text-sm`
- `.badge-tmdb` (badge verde para providers disponibles en TMDb)

## Resultado de tests

```
796 passed, 4 warnings
```

13 tests nuevos en `tests/test_settings_api.py`.

## npm build

```
✓ 78 modules transformed
✓ built in 1.81s
```

Sin errores TypeScript. 2 módulos nuevos respecto a Fase 10A (settings.ts + uso en SettingsPage).

## Docker

No disponible en este entorno. Los endpoints settings siguen el mismo patrón de auth Bearer
que el resto de la API; no requieren cambios en Dockerfile ni docker-compose.

## Confirmaciones de restricciones

- `Uploadrr/` no fue tocado
- No se ejecutó ninguna subida real
- No se implementó Jellyfin ni Seerr
- TMDb API key nunca expuesta completa en respuesta API ni en UI
- MKV title exige token exacto `APLICAR_TITULO_MKV` antes de habilitar el botón de aplicar
- `source_path` no modificado

## Gaps restantes

- `default_release_tag` no se aplica aún automáticamente al inicializar campos en
  `build_editable_nomenclature_fields` (el campo se puede editar manualmente pero el
  valor por defecto que propone el backend todavía está hardcoded en `source_assistant.py`).
  Resoluble en una fase 10C menor.
- `provider_priority_order` se persiste pero `source_assistant.py` ya lo lee correctamente.
- Los providers con `tmdb_available: true` se muestran con `★` en el select del modal;
  se podría mejorar visualmente con el badge verde `.badge-tmdb` en una futura iteración.
