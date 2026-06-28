# eMuwarez Uploadrr — Pack maestro para Codex v3

Documento de trabajo para implementar la evolución de `eMuwarez Uploadrr` desde el motor/CLI actual hacia una aplicación web completa con Docker, dashboard, setup inicial, sincronización Radarr/Sonarr, lectura de peticiones eMuwarez, compatibilidad, nomenclatura y subidas con Uploadrr.

Este documento está pensado para dárselo a Codex como contexto global y después trabajar **fase por fase**. No debe ejecutarse todo de golpe.

---

## 1. Objetivo del proyecto

`eMuwarez Uploadrr` debe convertirse en un servicio web autoalojado que:

1. Mantiene la CLI actual funcionando.
2. Añade backend web con API.
3. Añade frontend moderno tipo dashboard.
4. Se instala y ejecuta con Docker.
5. Usa Radarr/Sonarr como fuente principal de biblioteca.
6. Usa eMuwarez como fuente de peticiones y destino de subida.
7. Usa Uploadrr como motor de subida.
8. Usa TMDb para matching, títulos españoles, IDs y metadatos.
9. Puede usar Jellyfin y Seerr como integraciones opcionales.
10. Permite ver qué peticiones de eMuwarez pueden cubrirse con contenido ya disponible.
11. Permite adaptar nomenclatura y subir contenido desde la UI.
12. Deja preparada la creación automática de peticiones en eMuwarez para una fase final.

La función principal no es sustituir a Seerr, Radarr, Sonarr ni Trailarr. La función principal es:

```text
Detectar qué tienes, qué falta, qué pide eMuwarez, qué puedes cubrir, adaptar nomenclatura y subir con Uploadrr.
```

---

## 2. Estado actual esperado del repo

Se parte de una versión similar a:

```text
emuwarez_uploadrr_cli_ready_v2/
├── emuwarez_uploader.py
├── emuwarez_uploadrr/
│   ├── legacy.py
│   ├── cli.py
│   ├── database.py
│   ├── models.py
│   ├── integrations/
│   │   ├── radarr.py
│   │   ├── sonarr.py
│   │   └── emu.py
│   └── services/
│       ├── instances.py
│       ├── library.py
│       ├── requests.py
│       └── tasks.py
├── README_REFACTOR.md
├── README_CLI_READY.md
└── pyproject.toml
```

El modo antiguo debe seguir funcionando:

```bash
python3 emuwarez_uploader.py "/ruta/pelicula.mkv" --dry-run
python3 emuwarez_uploader.py --configure
python3 emuwarez_uploader.py --doctor
```

La nueva CLI también debe seguir funcionando:

```bash
python3 emuwarez_uploader.py db init
python3 emuwarez_uploader.py instances list
python3 emuwarez_uploader.py sync
python3 emuwarez_uploader.py library list
python3 emuwarez_uploader.py requests list
python3 emuwarez_uploader.py tasks list
```

---

## 3. Principios no negociables

### 3.1. No romper la CLI

La CLI es la base operativa. La web debe reutilizar el motor/servicios existentes, no duplicar lógica.

Regla:

```text
CLI = espejo funcional de la Web
Web = interfaz visual sobre el mismo motor
```

Todo lo importante que pueda hacerse en la web debe poder ejecutarse por CLI.

### 3.2. Radarr/Sonarr son la fuente principal de biblioteca

No usar Jellyfin como fuente principal de biblioteca.

Orden de confianza:

```text
1. Radarr/Sonarr
2. TMDb
3. eMuwarez
4. Jellyfin opcional
5. Seerr opcional
```

Radarr/Sonarr aportan:

```text
- películas/series/episodios gestionados
- estado disponible/faltante
- queue
- history
- rutas reales
- calidad
- resolución
- quality profile
- monitored/unmonitored
- TMDb/IMDb/TVDb IDs
- root folder
- instancia origen
```

Jellyfin queda como verificación opcional:

```text
- verificar si un contenido está visible en Jellyfin
- detectar contenido manual fuera de Radarr/Sonarr
- enlaces rápidos a Jellyfin
- posible refresh de biblioteca
```

Seerr queda como integración opcional:

```text
- entender solicitudes de usuarios
- conocer flujo Jellyfin/Seerr -> Radarr/Sonarr
- aportar contexto, no sustituir Radarr/Sonarr
```

### 3.3. eMuwarez: lectura ahora, creación al final

Hay dos bloques separados.

Lectura de peticiones:

```text
- listar peticiones activas
- ver detalle de petición
- extraer TMDb/IMDb si aparece en el detalle
- extraer título, categoría, resolución, tipo/source, puntos, estado y fecha
- cruzar contra biblioteca
```

Crear petición en eMuwarez:

```text
- queda para la fase final
- no inventar endpoint
- no asumir payload
- implementar solo cuando el usuario aporte la request real capturada en DevTools > Network
```

Hasta entonces debe existir un stub seguro:

```python
emu_create_request(...)
```

que devuelva:

```text
Función preparada, pendiente de implementar endpoint real de eMuwarez.
```

### 3.4. Todas las acciones peligrosas tienen prechecks

Antes de recomendar crear petición, subir, adaptar nomenclatura o tocar archivos, comprobar:

```text
- si está disponible localmente
- si está en queue de Radarr/Sonarr
- si está descargando
- si hay error de importación
- si ya existe en eMuwarez
- si ya hay petición eMuwarez activa
- si la petición ya está llena
- si hay posible duplicado
```

### 3.5. Git obligatorio por fases

Codex debe trabajar así:

```bash
git status
git checkout -b feature/<fase>
# modificar
# validar
git status
git diff
git add ...
git commit -m "..."
```

Reglas:

```text
- no hacer push salvo orden explícita
- no sobrescribir cambios sin revisarlos
- no usar git reset --hard salvo orden explícita
- commits pequeños y descriptivos
- una rama por fase
```

---

## 4. Conceptos funcionales definitivos

### 4.1. Biblioteca, Faltantes y Peticiones

#### Biblioteca

Origen principal: Radarr/Sonarr.

Muestra todo lo que el sistema conoce desde las instancias configuradas:

```text
- películas disponibles
- películas faltantes
- series
- temporadas
- episodios disponibles/faltantes
- calidad
- rutas
- estado local
- origen
- nomenclatura
- relación con peticiones eMuwarez
```

#### Faltantes

Origen: Radarr/Sonarr.

Muestra contenido que está añadido/monitorizado en Radarr/Sonarr pero no está disponible localmente.

Ejemplos:

```text
- película monitorizada sin archivo
- episodio monitorizado sin archivo
- temporada incompleta
- item con fallo de importación
- item que no se encuentra en indexadores
```

Objetivo:

```text
Determinar si conviene buscar, revisar Radarr/Sonarr, comprobar eMuwarez o, al final, crear petición en eMuwarez.
```

#### Peticiones

Origen: eMuwarez.

Muestra todas las peticiones de eMuwarez, cruzadas contra la biblioteca local.

Objetivo:

```text
Saber qué peticiones de eMuwarez puedes cubrir con contenido que ya tienes.
```

Peticiones no es lo mismo que Faltantes.

Orden por defecto de Peticiones:

```text
1. Compatible + Disponible + Nomenclatura correcta
2. Compatible + Disponible + Nomenclatura no adaptada
3. Parcial por source
4. Parcial por resolución
5. Parcial por source y resolución
6. Relacionado pero no compatible
7. No encontrado en biblioteca
8. Petición llena
```

### 4.2. Estados principales

Estado local:

```text
Disponible
Faltante
En cola
Descargando
Pendiente de importación
Error de importación
Error de búsqueda
Subiendo
Subido
Error
```

Estado eMuwarez:

```text
No comprobado
Existe en eMuwarez
No existe en eMuwarez
Petición activa
Petición llena
Posible duplicado
Duplicado confirmado
Error comprobando
```

Petición:

```text
Sin petición
Compatible
Parcial
No compatible
Llena
```

Nomenclatura:

```text
Correcta
No adaptada
N/A
```

No usar `FormatoEMU`. La columna debe llamarse siempre:

```text
Nomenclatura
```

El botón debe llamarse:

```text
Adaptar nomenclatura
```

### 4.3. Compatibilidad de petición

Una petición eMuwarez se compara contra un item local.

Campos:

```text
- TMDb ID
- IMDb ID
- título español
- título original
- título normalizado
- tipo: película/serie/temporada/episodio
- categoría: películas/series
- resolución pedida
- source/tipo pedido
- calidad local
- source local
- disponibilidad local
- estado eMuwarez: sin llenar/lleno
```

Reglas:

```text
EMU pide 1080p WEB-DL
Local tiene 1080p WEB-DL
=> Compatible

EMU pide 2160p WEB-DL
Local tiene 1080p WEB-DL
=> Parcial
Motivo: resolución diferente

EMU pide 1080p WEB-DL
Local tiene 1080p BluRay
=> Parcial
Motivo: source diferente

EMU pide Any 1080p
Local tiene 1080p BluRay
=> Compatible o Parcial leve según configuración

EMU pide 2160p
Local no tiene archivo
=> No compatible / Faltante

EMU estado = Lleno
=> Llena, aunque exista localmente
```

La UI debe mostrar motivos:

```text
Motivos:
  ✓ TMDb coincide
  ✓ Resolución compatible: 1080p
  ⚠ Source diferente: EMU pide WEB-DL y tienes BluRay
```

---

## 5. Flujo funcional completo

### 5.1. Setup inicial

Al abrir por primera vez:

```text
http://IP:9494
```

Debe aparecer un wizard. No mostrar Dashboard hasta completar setup.

Pasos:

```text
1. Crear usuario admin
2. Configuración general
3. Conectar Radarr
4. Conectar Sonarr
5. Conectar eMuwarez
6. Conectar TMDb
7. Conectar Uploadrr
8. Jellyfin opcional
9. Seerr opcional
10. Resumen y primera sincronización
```

#### Paso 1 — Usuario admin

Campos:

```text
Usuario
Contraseña
Confirmar contraseña
```

Validaciones:

```text
- usuario obligatorio
- contraseña mínimo 12 caracteres
- contraseña debe confirmar
- guardar hash, nunca texto claro
```

#### Paso 2 — Configuración general

Campos:

```text
Nombre de instancia
Zona horaria
Puerto web: 9494 por defecto
Ruta de configuración: /config
Ruta Uploadrr
Ruta base hardlinks/subidas
Tag release por defecto
```

#### Paso 3 — Radarr

Múltiples instancias.

Campos:

```text
Nombre
URL
API key
Tipo de instancia: Normal / 4K / Anime / Otro
Root folder
Quality profile
Enabled
```

Botones:

```text
Probar conexión
Añadir otra instancia
Eliminar
```

#### Paso 4 — Sonarr

Igual que Radarr.

Campos:

```text
Nombre
URL
API key
Tipo de instancia: Normal / 4K / Anime / Otro
Root folder
Quality profile
Enabled
```

#### Paso 5 — eMuwarez

Campos:

```text
API key
Anon por defecto: sí/no
Refresco automático de peticiones: mínimo 1 hora
```

Botón:

```text
Probar conexión
```

#### Paso 6 — TMDb

Campos:

```text
API key
Idioma preferido: es-ES
Región preferida: ES
```

TMDb es recomendado para:

```text
- título español
- título original
- IDs externos
- matching
- posters
```

#### Paso 7 — Uploadrr

Campos:

```text
Ruta Uploadrr
Ruta upload.py
Ruta config.yaml
Ruta tmp
Modo torrent client: watch / qBittorrent
```

No romper la lógica actual de backup/restauración de config de Uploadrr.

#### Paso 8 — Jellyfin opcional

Campos:

```text
URL
API key
Bibliotecas a verificar
```

#### Paso 9 — Seerr opcional

Campos:

```text
URL
API key
```

#### Paso 10 — Primera sincronización

Tareas iniciales:

```text
1. Sincronizar Radarr/Sonarr
2. Sincronizar queue/history
3. Sincronizar peticiones eMuwarez si disponible
4. Calcular compatibilidad
5. Ir al Dashboard
```

### 5.2. Flujo seguro de decisión

Ejemplo:

```text
Usuario solicita Transformers.
Seerr añade Transformers a Radarr.
Radarr intenta buscar/importar.
```

eMuwarez Uploadrr debe observar, no actuar a ciegas.

Flujo:

```text
1. Detectar item en Radarr/Sonarr.
2. Comprobar si tiene archivo.

Si tiene archivo:
  - Estado local = Disponible
  - comprobar nomenclatura
  - comprobar petición eMuwarez compatible
  - recomendar Adaptar nomenclatura/Subir

Si no tiene archivo:
  - comprobar queue

Si está en queue:
  - Estado local = En cola / Descargando / Pendiente de importación
  - recomendación = Esperar descarga

Si no está en queue:
  - comprobar history y warnings

Si hay error:
  - Estado local = Error de búsqueda/importación
  - recomendación = Revisar Radarr/Sonarr

Si no hay error:
  - Estado local = Faltante
  - recomendación = Comprobar en eMuwarez

Al comprobar eMuwarez:
  - si existe torrent: recomendar Abrir resultado/Reintentar búsqueda
  - si existe petición activa: recomendar Ver petición/esperar/cubrir si disponible
  - si no existe torrent ni petición: recomendación futura = Crear petición eMuwarez
```

### 5.3. Crear petición eMuwarez

Fase final.

Condiciones futuras para activar botón:

```text
- item faltante en Radarr/Sonarr
- no está en queue
- no está descargando
- no hay error que explique el fallo
- no existe en eMuwarez
- no hay petición activa compatible
- endpoint real de crear petición configurado
```

Mientras no esté implementado:

```text
Crear petición en eMuwarez
Estado: pendiente de implementar endpoint real
```

---

## 6. UI final esperada

### 6.1. Estilo visual

Tema:

```text
- dark mode por defecto
- fondo navy/black
- cards con glassmorphism sutil
- bordes azul oscuro
- sombras suaves
- acentos neón controlados
- tipografía clara y legible
```

Colores semánticos:

```text
Azul    = acciones, navegación, información
Verde   = disponible, compatible, correcta, completada
Amarillo= parcial, no adaptada, warning
Rojo    = faltante, error, no compatible
Morado  = subiendo, procesos activos
Gris    = N/A, sin petición, estados neutros
```

### 6.2. Layout grid obligatorio

Debe parecer construido con CSS Grid/Flex bien alineado.

Reglas:

```text
- sidebar ancho fijo
- topbar alto fijo
- main content con grid de 12 columnas
- gap consistente
- cards superiores alineadas en altura
- panel derecho alineado con tarjeta Completadas
- tabla central alineada con paneles inferiores
- columnas de tabla con anchos constantes
- botones alineados en acciones
- badges con altura uniforme
- iconos Radarr/Sonarr alineados con texto
```

Requisito explícito:

```text
Donde aparezca Radarr o Sonarr, usar sus iconos propios o una representación visual clara de sus iconos junto al texto.
```

Ejemplos:

```text
[icono Radarr] Radarr principal
[icono Sonarr] Sonarr Anime
```

Si no se pueden usar logos oficiales por licencia/assets, crear iconos internos consistentes inspirados pero no copiados.

### 6.3. Sidebar

Items:

```text
Dashboard
Biblioteca
Faltantes
Peticiones
Subidas
Tareas
Instancias
Logs
Configuración
```

Dashboard seleccionado por defecto.

### 6.4. Dashboard

Top cards:

```text
Biblioteca sincronizada
Faltantes
Disponibles
Subiendo
Completadas
```

Tarjeta `Biblioteca sincronizada`:

```text
13.257
Biblioteca sincronizada
[icono Radarr] Radarr: 8.912
[icono Sonarr] Sonarr: 4.345
```

`Completadas` debe tener el mismo ancho/columna que el panel derecho `Actividad de subida`.

Las otras cuatro cards deben ocupar el ancho de la zona central.

### 6.5. Tabla Actividad reciente

Título:

```text
Actividad reciente
```

Botón:

```text
Actualizar
```

Columnas:

```text
Título
Origen
Estado
Petición
Nomenclatura
Tamaño
Añadido
Acciones
```

Filas ejemplo:

```text
Dune: Parte Dos (2024)
Origen: [Radarr icon] Radarr
Estado: Disponible
Petición: Compatible
Nomenclatura: Correcta
Acción: Subir

Oppenheimer (2023)
Origen: [Radarr icon] Radarr
Estado: Disponible
Petición: Compatible
Nomenclatura: No adaptada
Acción: Adaptar nomenclatura + Subir

Fallout - T01E01
Origen: [Sonarr icon] Sonarr
Estado: Faltante
Petición: Sin petición
Nomenclatura: N/A
Acción: Comprobar en EMU

The Last of Us - T01E05
Origen: [Sonarr icon] Sonarr
Estado: Subiendo
Petición: Llena
Nomenclatura: Correcta
Acción: Ver progreso

Spider-Man: No Way Home (2021)
Origen: [Radarr icon] Radarr
Estado: Disponible
Petición: Parcial
Nomenclatura: No adaptada
Acción: Adaptar nomenclatura + Subir
```

### 6.6. Panel Actividad de subida

Mostrar:

```text
- título
- tamaño
- tipo: película/episodio/temporada
- barra de progreso
- porcentaje
- etapa actual
- velocidad
- transferido
- ETA
- pasos:
  - validando archivos
  - comprimiendo
  - subiendo a EMU
  - publicado en EMU
```

### 6.7. Panel Últimas tareas ejecutadas

Columnas:

```text
Tarea
Origen
Estado
Detalles
Ejecutado
```

Ejemplos:

```text
Sincronización completa
Análisis de faltantes
Comprobación en EMU
Sincronización de peticiones
Subida automática
Sincronización incremental
```

### 6.8. Panel Últimos eventos

Columnas:

```text
Hora
Evento
Origen
```

Eventos ejemplo:

```text
Sincronización completa finalizada
Análisis de faltantes completado
Comprobación en EMU completada
Nueva petición detectada
Nomenclatura adaptada
Subida añadida a cola
```

---

## 7. Pantalla Peticiones

Esta pantalla es obligatoria y separada de Faltantes.

### 7.1. Objetivo

Mostrar peticiones de eMuwarez y ordenarlas por capacidad de cubrirlas desde la biblioteca.

### 7.2. Filtros

```text
Búsqueda por título
Categoría: Películas / Series / Todas
Estado eMuwarez: Sin llenar / Lleno / Todos
Compatibilidad: Compatible / Parcial / No compatible / Sin match / Todas
Resolución pedida: Any / 720p / 1080p / 2160p
Source pedido: Any / WEB-DL / BluRay / HDTV / BDRemux / Otro
Origen local: Radarr / Sonarr / Todos
Nomenclatura: Correcta / No adaptada / N/A
```

### 7.3. Tabla

Columnas:

```text
Petición
Categoría
Tipo pedido
Resolución pedida
Estado eMuwarez
Compatibilidad
Contenido local
Origen local
Calidad local
Nomenclatura
Puntos
Creada
Acciones
```

### 7.4. Orden por defecto

```text
1. Compatible + disponible + nomenclatura correcta
2. Compatible + disponible + nomenclatura no adaptada
3. Parcial con un solo motivo
4. Parcial con varios motivos
5. No compatible pero con match probable
6. Sin contenido local
7. Llena
```

### 7.5. Panel de detalle

Al hacer clic:

```text
Petición eMuwarez
  Nombre
  Categoría
  Tipo pedido
  Resolución pedida
  Estado
  Puntos
  Creada
  TMDb
  IMDb
  Enlace eMuwarez

Contenido local
  Título
  Origen
  Estado local
  Calidad
  Resolución
  Source
  Ruta
  Nomenclatura

Compatibilidad
  Resultado
  Motivos con ✓ / ⚠ / ✗

Acciones
  Subir
  Adaptar nomenclatura
  Abrir en eMuwarez
  Abrir en Radarr/Sonarr
  Marcar revisado
```

---

## 8. Pantalla Faltantes

### 8.1. Objetivo

Mostrar items faltantes desde Radarr/Sonarr y decidir qué hacer.

### 8.2. Filtros

```text
Origen
Tipo
Calidad esperada
Estado de queue
Tiene error
Existe en eMuwarez
Tiene petición eMuwarez
Recomendación
```

### 8.3. Tabla

Columnas:

```text
Título
Origen
Tipo
Estado local
Queue
Último error
eMuwarez
Petición
Recomendación
Acciones
```

### 8.4. Acciones

```text
Comprobar en EMU
Abrir Radarr/Sonarr
Reintentar búsqueda
Ver history/queue
Crear petición eMuwarez (futuro)
```

---

## 9. Backend esperado

### 9.1. Estructura propuesta

```text
emuwarez_uploadrr/
├── api/
│   ├── __init__.py
│   ├── app.py
│   ├── deps.py
│   ├── auth.py
│   ├── routers/
│   │   ├── setup.py
│   │   ├── auth.py
│   │   ├── dashboard.py
│   │   ├── instances.py
│   │   ├── library.py
│   │   ├── missing.py
│   │   ├── requests.py
│   │   ├── uploads.py
│   │   ├── tasks.py
│   │   ├── logs.py
│   │   └── settings.py
│   └── schemas/
├── integrations/
│   ├── radarr.py
│   ├── sonarr.py
│   ├── emu.py
│   ├── tmdb.py
│   ├── jellyfin.py
│   └── seerr.py
├── services/
│   ├── setup.py
│   ├── auth.py
│   ├── dashboard.py
│   ├── library_sync.py
│   ├── missing.py
│   ├── request_sync.py
│   ├── compatibility.py
│   ├── nomenclature.py
│   ├── upload_jobs.py
│   ├── task_runner.py
│   └── recommendations.py
└── ...
```

### 9.2. API mínima

```text
GET  /api/health
GET  /api/setup/status
POST /api/setup/admin
POST /api/setup/general
POST /api/setup/instances/test
POST /api/setup/complete

POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me

GET  /api/dashboard/summary
GET  /api/dashboard/recent-activity
GET  /api/dashboard/upload-activity
GET  /api/dashboard/tasks
GET  /api/dashboard/events

GET  /api/instances
POST /api/instances
PATCH /api/instances/{id}
DELETE /api/instances/{id}
POST /api/instances/{id}/test

POST /api/sync/library
POST /api/sync/requests

GET  /api/library
GET  /api/library/{id}

GET  /api/missing
POST /api/missing/{id}/check-emu
POST /api/missing/{id}/create-request  # stub

GET  /api/requests
GET  /api/requests/{id}
POST /api/requests/sync
POST /api/requests/{id}/mark-reviewed

POST /api/nomenclature/{library_id}/preview
POST /api/nomenclature/{library_id}/apply

POST /api/uploads
GET  /api/uploads
GET  /api/uploads/{id}
GET  /api/uploads/{id}/events

GET  /api/tasks
POST /api/tasks/{task_name}/run

GET  /api/logs
```

### 9.3. WebSocket/SSE

Para progreso de subidas:

```text
GET /api/uploads/{id}/stream
```

Evento ejemplo:

```json
{
  "upload_id": 1,
  "stage": "uploading_to_emu",
  "percent": 62,
  "message": "Subiendo archivo",
  "speed": "14.2 MB/s",
  "transferred": "6.2 GB / 10 GB",
  "eta": "4m 32s"
}
```

---

## 10. Base de datos

SQLite por defecto:

```text
/config/emuwarez_uploadrr.db
```

Tablas mínimas:

```text
users
settings
instances
library_items
request_items
request_matches
queue_items
history_items
upload_jobs
upload_events
task_runs
event_log
app_state
```

### 10.1. library_items

Campos:

```text
id
external_id
source_system: radarr/sonarr/jellyfin/manual
source_instance_id
media_type: movie/series/season/episode
title
original_title
spanish_title
year
tmdb_id
imdb_id
tvdb_id
season_number
episode_number
path
file_path
size_bytes
quality_name
resolution
source
codec
audio
subtitles
monitored
has_file
local_status
nomenclature_status
nomenclature_title
created_at
updated_at
```

### 10.2. request_items

Campos:

```text
id
emu_id
title
category
requested_type
requested_resolution
requested_source
status_emu
points
comments
created_at_emu
tmdb_id
imdb_id
url
raw_json
last_synced_at
```

### 10.3. request_matches

Campos:

```text
id
request_item_id
library_item_id
match_status
compatibility_score
title_score
id_match
resolution_match
source_match
type_match
reasons_json
created_at
updated_at
```

### 10.4. upload_jobs

Campos:

```text
id
library_item_id
request_item_id
title
status
stage
percent
source_path
prepared_path
uploadrr_tmp_path
description_path
emu_url
dupe_status
dupe_message
created_at
started_at
finished_at
error_message
```

---

## 11. Docker esperado

Puerto por defecto:

```text
9494
```

Variables:

```text
PUID
PGID
TZ
PORT=9494
CONFIG_DIR=/config
```

docker-compose esperado:

```yaml
services:
  emuwarez-uploadrr:
    image: emuwarez-uploadrr:latest
    container_name: emuwarez-uploadrr
    ports:
      - "9494:9494"
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Madrid
      - PORT=9494
      - CONFIG_DIR=/config
    volumes:
      - ./config:/config
      - /mnt/storage/media:/media
      - /mnt/storage/uploads/emu:/uploads
      - ./Uploadrr:/app/Uploadrr
    restart: unless-stopped
```

---

## 12. Prompts para Codex por fases

Instrucción general para Codex antes de cualquier fase:

```text
Trabaja sobre el repo indicado por el usuario. Antes de modificar nada, ejecuta git status, revisa la estructura y explica brevemente qué vas a tocar. Crea una rama específica para la fase. Haz commits pequeños. No hagas push. No borres ni reescribas lógica existente sin justificarlo. Mantén la CLI antigua funcionando.
```

### Fase 0 — Auditoría del repo

Rama:

```bash
feature/ui-phase-00-audit
```

Prompt:

```text
Necesito que audites el repo actual de eMuwarez Uploadrr antes de implementar la UI.

Objetivos:
1. Revisar estructura actual.
2. Identificar la CLI legacy y la CLI nueva.
3. Identificar modelos, base de datos, servicios e integraciones ya existentes.
4. Confirmar qué comandos funcionan.
5. No cambiar comportamiento funcional.
6. Crear docs/ARCHITECTURE_AUDIT.md con estructura actual, módulos existentes, qué se reutilizará para la web, riesgos y recomendaciones.

Reglas:
- Ejecuta git status antes.
- Crea rama feature/ui-phase-00-audit.
- No hagas push.
- No elimines legacy.py.
- Mantén py_compile funcionando.
- Commit final: docs: add architecture audit for UI migration

Validaciones:
python3 -m py_compile emuwarez_uploader.py
find emuwarez_uploadrr -name "*.py" -print0 | xargs -0 python3 -m py_compile
python3 emuwarez_uploader.py --help
python3 emuwarez_uploader.py web-contract
```

### Fase 1 — Contrato funcional y modelos

Rama:

```bash
feature/ui-phase-01-contract
```

Prompt:

```text
Implementa el contrato funcional interno para preparar la web.

Objetivos:
1. Añadir/enriquecer modelos para LocalStatus, EmuStatus, RequestStatus, NomenclatureStatus, RecommendationType, LibraryItem, RequestItem, RequestMatch, UploadJob y TaskRun.
2. Añadir docs/FUNCTIONAL_FLOW.md con diferencia entre Biblioteca/Faltantes/Peticiones, flujo seguro, reglas de compatibilidad, estados definitivos y prechecks.
3. Añadir docs/UI_SPEC.md con estilo visual, grid layout, sidebar, dashboard, pantalla Peticiones, pantalla Faltantes y uso obligatorio de iconos Radarr/Sonarr.
4. No implementar frontend todavía.
5. No romper CLI.

Reglas:
- Reutiliza modelos existentes si los hay.
- Si añades enums, usa strings estables para API/UI.
- Commit final: feat: add functional contract and UI specification

Validaciones:
python3 -m py_compile emuwarez_uploader.py
find emuwarez_uploadrr -name "*.py" -print0 | xargs -0 python3 -m py_compile
python3 emuwarez_uploader.py db init
python3 emuwarez_uploader.py web-contract
```

### Fase 2 — Backend FastAPI base

Rama:

```bash
feature/ui-phase-02-backend-base
```

Prompt:

```text
Crea el backend web base con FastAPI sin romper la CLI.

Objetivos:
1. Añadir emuwarez_uploadrr/api/app.py.
2. Añadir routers mínimos: health, setup/status, auth placeholder y dashboard placeholder.
3. Añadir comando CLI: python3 emuwarez_uploader.py web serve --host 0.0.0.0 --port 9494
4. Añadir endpoints GET /api/health y GET /api/setup/status.
5. Si no existe usuario admin/config completada, setup/status debe devolver initialized=false.
6. No implementar frontend todavía.
7. Añadir dependencia FastAPI/uvicorn de forma compatible.
8. Mantener modo legacy.

Reglas:
- No mover legacy.py.
- No duplicar lógica de database si ya existe.
- Usar /config o CONFIG_DIR si existe.
- Commit final: feat: add FastAPI backend base

Validaciones:
python3 -m py_compile emuwarez_uploader.py
find emuwarez_uploadrr -name "*.py" -print0 | xargs -0 python3 -m py_compile
python3 emuwarez_uploader.py web serve --help
python3 - <<'PY'
from emuwarez_uploadrr.api.app import create_app
app = create_app()
print(app.title)
PY
```

### Fase 3 — Setup wizard frontend/backend

Rama:

```bash
feature/ui-phase-03-setup-wizard
```

Prompt:

```text
Implementa la base de frontend y el setup wizard inicial.

Backend:
- GET /api/setup/status
- POST /api/setup/admin
- POST /api/setup/general
- POST /api/setup/complete
- guardar usuario admin con hash seguro
- initialized=true solo al completar setup

Frontend:
- React + Vite o stack elegido
- dark theme por defecto
- ruta /setup
- wizard visual con admin, general, Radarr, Sonarr, eMuwarez, TMDb, Uploadrr, Jellyfin opcional, Seerr opcional y resumen
- si initialized=false, redirigir a /setup
- si initialized=true, redirigir a /dashboard

Estilo:
- dark navy/black
- cards redondeadas
- acentos azules
- grid limpio

Commit final: feat: add setup wizard shell
```

### Fase 4 — Radarr/Sonarr sync

Rama:

```bash
feature/ui-phase-04-radarr-sonarr-sync
```

Prompt:

```text
Implementa integración real con Radarr/Sonarr y sincronización de biblioteca.

Objetivos:
1. Conectar múltiples instancias Radarr/Sonarr.
2. Test de conexión por instancia.
3. Obtener movies, series, episodes, files, queue, history relevante, root folders y quality profiles si es viable.
4. Guardar en SQLite como library_items.
5. Calcular local_status: Disponible, Faltante, En cola, Descargando, Pendiente de importación, Error de importación, Error de búsqueda.
6. Endpoints: GET /api/library, GET /api/library/{id}, POST /api/sync/library, GET /api/missing.
7. CLI: sync, library list, library show, missing list.
8. UI básica de Dashboard/Biblioteca/Faltantes con datos reales si existen.

Reglas:
- Radarr/Sonarr son fuente principal.
- Jellyfin no es fuente principal.
- No hacer acciones destructivas.
- Commit final: feat: sync library from Radarr and Sonarr
```

### Fase 5 — eMuwarez requests lectura

Rama:

```bash
feature/ui-phase-05-emu-requests
```

Prompt:

```text
Implementa lectura de peticiones eMuwarez dejando stubs seguros donde falte endpoint real.

Objetivos:
1. Cliente eMuwarez: test_connection, list_requests, get_request_detail, search_existing.
2. Si no se conoce endpoint real para alguna función, dejar NotImplemented controlado con mensaje claro.
3. Guardar request_items en SQLite.
4. Aplicar límite de sync manual de peticiones máximo 1 vez por hora y automático mínimo 1 hora.
5. Endpoints: GET /api/requests, GET /api/requests/{id}, POST /api/requests/sync.
6. CLI: requests sync, requests list, requests show.
7. UI básica Peticiones.

Reglas:
- No inventar endpoint de crear petición.
- No bloquear todo el sistema si eMuwarez requests no está disponible.
- Commit final: feat: add eMuwarez request sync scaffolding
```

### Fase 6 — Motor de compatibilidad

Rama:

```bash
feature/ui-phase-06-compatibility-engine
```

Prompt:

```text
Implementa el motor de compatibilidad entre peticiones eMuwarez y biblioteca local.

Objetivos:
1. Crear service compatibility.py.
2. Matching por prioridad: TMDb ID, IMDb ID, título español, título original, título normalizado, fuzzy fallback.
3. Comparar tipo, resolución, source, disponibilidad local, estado eMuwarez y nomenclatura.
4. Generar RequestMatch con score y reasons_json.
5. Estados: Compatible, Parcial, No compatible, Llena, Sin petición.
6. Ordenar Peticiones por compatible disponible correcta, compatible disponible no adaptada, parcial, no compatible, sin match, llena.
7. Añadir explicación de motivos para UI.

Tests mínimos:
- 1080p WEB-DL vs 1080p WEB-DL => compatible
- 2160p WEB-DL vs 1080p WEB-DL => parcial resolución
- 1080p WEB-DL vs 1080p BluRay => parcial source
- Any 1080p vs 1080p BluRay => compatible/parcial leve según regla documentada
- petición llena => llena

Commit final: feat: add request compatibility engine
```

### Fase 7 — Dashboard + Peticiones/Faltantes UI

Rama:

```bash
feature/ui-phase-07-dashboard-requests-ui
```

Prompt:

```text
Implementa la UI principal siguiendo exactamente la especificación visual.

Objetivos:
1. Layout app con topbar, sidebar, main grid y right panel.
2. Sidebar: Dashboard, Biblioteca, Faltantes, Peticiones, Subidas, Tareas, Instancias, Logs, Configuración.
3. Dashboard: cards superiores, Actividad reciente, Actividad de subida, Últimas tareas ejecutadas, Últimos eventos.
4. Tabla Actividad reciente con columnas: Título, Origen, Estado, Petición, Nomenclatura, Tamaño, Añadido, Acciones.
5. Usar iconos Radarr/Sonarr junto al texto en cards, tabla, tareas, eventos y filtros.
6. Alinear todo con grid estricto: spacing consistente, columnas exactas, cards mismo alto, panel derecho alineado, botones alineados.
7. Pantalla Peticiones con filtros, tabla, orden por compatibilidad y panel detalle.
8. Pantalla Faltantes con filtros, tabla y recomendaciones.
9. Estados visuales: verde compatible/disponible/correcta, amarillo parcial/no adaptada, rojo faltante/error, morado subiendo, gris N/A/sin petición.

Texto exacto:
- Nomenclatura, no FormatoEMU.
- Adaptar nomenclatura, no Añadir formato.
- Comprobar en EMU.
- Ver progreso.
- Subir.

Reglas:
- No usar layouts descuadrados.
- No dejar textos desalineados.
- No omitir iconos Radarr/Sonarr.
- Commit final: feat: add dashboard and request management UI
```

### Fase 8 — Nomenclatura y Uploadrr desde UI

Rama:

```bash
feature/ui-phase-08-nomenclature-uploadrr
```

Prompt:

```text
Conecta la UI con el motor de nomenclatura y subida Uploadrr.

Objetivos:
1. POST /api/nomenclature/{library_id}/preview.
2. POST /api/nomenclature/{library_id}/apply.
3. POST /api/uploads.
4. GET /api/uploads y GET /api/uploads/{id}.
5. GET /api/uploads/{id}/stream.
6. Reutilizar MediaInfo, naming, hardlinks, Uploadrr config injection, Uploadrr runner, progress parser y results parser.
7. UI para preview de nomenclatura, confirmar antes de aplicar, progreso en vivo y resultado final.
8. Dupe preparado: dupe_status, dupe_message, parseo básico de mensajes conocidos.

Reglas:
- No duplicar lógica legacy si puede reutilizarse.
- Dry-run disponible.
- No tocar archivos sin confirmación.
- Commit final: feat: connect nomenclature and Uploadrr uploads to UI
```

### Fase 9 — Docker

Rama:

```bash
feature/ui-phase-09-docker
```

Prompt:

```text
Prepara Docker completo para eMuwarez Uploadrr.

Objetivos:
1. Dockerfile multi-stage si aplica.
2. docker-compose.yml ejemplo.
3. Puerto por defecto 9494.
4. Volumen /config.
5. Montajes documentados para media, uploads y Uploadrr.
6. Healthcheck GET /api/health.
7. README_DOCKER.md con instalación, variables, volúmenes, primer arranque, setup wizard y actualización.
8. No romper ejecución local.

Reglas:
- Usar usuario no-root si viable.
- Respetar PUID/PGID si se implementa.
- Commit final: chore: add Docker deployment
```

### Fase final — Crear petición eMuwarez

Rama:

```bash
feature/ui-final-emu-create-request
```

Prompt:

```text
Implementa la creación real de peticiones en eMuwarez usando la request capturada manualmente desde DevTools.

El usuario proporcionará:
- URL endpoint
- método
- headers
- payload
- auth/cookie/csrf/API key
- respuesta esperada
- errores conocidos

Objetivos:
1. Implementar emu_create_request().
2. Validar payload antes de enviar.
3. Añadir dry-run.
4. Añadir UI para Crear petición eMuwarez.
5. Mostrar prechecks antes de permitir crear.
6. Guardar resultado en event_log/task_runs.
7. Añadir errores claros.

Reglas:
- No enviar petición sin confirmación.
- No enviar si prechecks fallan.
- No loguear cookies/tokens.
- Commit final: feat: add eMuwarez request creation
```

---

## 13. Criterios de aceptación globales

El proyecto se considera listo para uso real cuando:

```text
1. Docker arranca en puerto 9494.
2. Primer setup crea admin.
3. Se pueden conectar Radarr/Sonarr.
4. Se sincroniza biblioteca.
5. Dashboard muestra datos reales.
6. Faltantes muestra items reales.
7. Peticiones muestra peticiones eMuwarez o estado claro si endpoint no está configurado.
8. Matching clasifica Compatible/Parcial/No compatible/Llena.
9. UI usa Nomenclatura y Adaptar nomenclatura.
10. Radarr/Sonarr aparecen con iconos y texto alineados.
11. Layout está en grid limpio.
12. Uploadrr puede ejecutarse desde UI en dry-run.
13. CLI sigue funcionando.
14. Git tiene commits por fase.
15. No hay secretos en logs ni commits.
```

---

## 14. Checklist rápido para Codex antes de cada commit

```text
[ ] git status revisado
[ ] no hay secretos
[ ] CLI legacy sigue funcionando
[ ] py_compile pasa
[ ] tests nuevos pasan si existen
[ ] docs actualizadas si cambió comportamiento
[ ] commit pequeño y descriptivo
[ ] no push
```

---

## 15. Referencia visual textual

La UI debe parecerse al dashboard generado previamente en este chat:

```text
- tema oscuro azul/neón
- sidebar completa
- sección Peticiones separada
- columna Nomenclatura
- botón Adaptar nomenclatura
- columna Petición con Compatible/Parcial/Sin petición/Llena
- iconos Radarr/Sonarr junto al texto
- diseño alineado en grid
```

Si Codex no tiene acceso a la imagen, debe seguir esta especificación textual.

