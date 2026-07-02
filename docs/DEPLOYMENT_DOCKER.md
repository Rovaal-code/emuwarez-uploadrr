# eMuwarez Uploadrr — Guía de despliegue Docker

Guía paso a paso para desplegar eMuwarez Uploadrr como contenedor Docker en un homelab.

---

## 1. Requisitos

- Docker 24+ con BuildKit habilitado
- Docker Compose v2 (`docker compose`, no `docker-compose`)
- Sistema Linux con usuario con permisos Docker
- Directorio de datos con espacio suficiente para media y uploads

---

## 2. Preparar carpetas

```bash
# Directorio de configuración persistente
mkdir -p /srv/emuwarez-uploadrr/config

# Raíz de datos — media y uploads en el MISMO filesystem para hardlinks
mkdir -p /srv/data/media
mkdir -p /srv/data/uploads/emu

# Directorio donde está instalado Uploadrr (externo, bind mount)
# Ajusta la ruta a tu instalación real de Uploadrr
# mkdir -p /srv/Uploadrr  # solo si aún no existe
```

> **Importante para hardlinks**: `/srv/data/media` y `/srv/data/uploads/emu` deben estar en el mismo dispositivo/partición para evitar el error `EXDEV (cross-device link)`. Usa una raíz común como `/srv/data` o `/data`.

---

## 3. Copiar .env

```bash
cd ~/emuwarez_uploadrr_cli_ready_v2  # o donde hayas clonado el repositorio
cp .env.example .env
# Edita .env y ajusta PUID, PGID y TZ a tu entorno
nano .env
```

Ajusta `PUID` y `PGID` al UID/GID del usuario que posee los archivos de media:

```bash
id $(whoami)  # muestra tu UID y GID
```

---

## 4. Levantar con Compose

```bash
docker compose -f docker-compose.example.yml up -d --build
```

La primera vez construye la imagen (incluye el build del frontend React). Puede tardar 1-3 minutos.

---

## 5. Abrir la interfaz web

Abre el navegador en:

```
http://localhost:9494
```

O si accedes desde otra máquina de la red:

```
http://<IP-DEL-SERVIDOR>:9494
```

---

## 6. Crear el primer usuario administrador

El setup wizard se abre automáticamente en el primer arranque.

Desde CLI, si prefieres:

```bash
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py web create-admin --username admin
```

---

## 7. Configurar la ruta de Uploadrr

En el setup web, en la sección **Uploadrr**, indica la ruta dentro del contenedor:

```
/opt/Uploadrr
```

Esta ruta corresponde al bind mount definido en `docker-compose.example.yml`:

```yaml
- /srv/Uploadrr:/opt/Uploadrr
```

Ajusta `/srv/Uploadrr` a la ruta real de tu instalación de Uploadrr en el host.

---

## 7b. Configurar el runtime Uploadrr-EMU (Fases 10E/10F)

El comando real que se construye para Uploadrr-EMU
(`-tk EMU -mt <título> -tmdb <id> -ua -c movie|tv -res <resolución>`) depende
de estos settings, editables desde **Configuración → Uploadrr** en la UI (o
por API/CLI):

| Setting | Valor por defecto | Notas |
|---|---|---|
| `uploadrr.path` | _(sin valor)_ | Ruta dentro del contenedor al directorio de Uploadrr-EMU, p.ej. `/opt/Uploadrr`. |
| `uploadrr.runtime_type` | `uploadrr_emu` | Perfil de flags a usar. El único runtime con ejecución controlada real soportada en la Fase 10F es `uploadrr_emu`; `uploadrr_generic` solo genera una previsualización best-effort y bloquea el inicio real. |
| `uploadrr.python_path` | `/usr/local/bin/python` | Asume la imagen base Python del contenedor. Uploadrr-EMU necesita su **propio venv** con sus dependencias (`requirements.txt` del fork) — instálalo en un volumen propio y ajusta este setting a `<venv>/bin/python`. **Nunca reutilices el intérprete del backend** (`sys.executable`). |
| `uploadrr.timeout` | `7200` (segundos) | Timeout del subproceso de subida. Si se excede, el job pasa a `failed`/`stage=timeout` y el proceso recibe `SIGKILL`. |
| `uploadrr.allowed_roots` | `[]` (JSON, editable como CSV en la UI) | Rutas permitidas para `prepared_path`. Vacío → usa `hardlink_base` como raíz permitida. |

Usa el botón **Probar configuración** en Settings para verificar (solo
filesystem, nunca ejecuta Uploadrr-EMU) que la ruta, el script `upload.py` y
`data/config.yaml` existen antes de intentar una subida real.

Estos settings se leen con fallback automático a la forma legacy sin punto
(`uploadrr_path`, etc.) pero solo el setup wizard/API escriben la forma con
punto — no hace falta migrar nada manualmente.

### Mounts necesarios (Fase 10F)

Antes de ejecutar una subida real, Uploadrr-EMU necesita:

1. **Código** (`/opt/Uploadrr`): puede ser `:ro`, no se modifica en ejecución.
2. **`data/`** (`/opt/Uploadrr/data`): debe ser **`rw`** — antes de cada
   ejecución se hace backup de `data/config.yaml` y se stagean ahí
   `DEFAULT.tmdb` y `TRACKERS.EMU.api_key`/`anon`; al terminar (éxito, fallo,
   timeout o cancelación) se **restaura siempre** el `config.yaml` original.
3. **`tmp/`** (`/opt/Uploadrr/tmp`): debe ser **`rw`** — el fork escribe ahí
   temporales (torrents, capturas, descripciones) durante la subida.

Ver `docker-compose.example.yml` para el mount de ejemplo (variables
`UPLOADRR_PATH` / `UPLOADRR_DATA_PATH` / `UPLOADRR_TMP_PATH` en `.env`). Si tu
fork de Uploadrr-EMU necesita otros directorios escribibles, documéntalos y
añade mounts específicos siguiendo el mismo patrón — nunca montes el árbol
completo en `rw` si el código en sí no necesita escribirse.

> **Importante**: `data/` y `tmp/` deben existir ya como directorios dentro
> de `$UPLOADRR_PATH` (el checkout de Uploadrr-EMU en el host) **antes** de
> arrancar el contenedor. Un mount anidado en `rw` dentro de un mount padre
> `:ro` falla con `Read-only file system` si Docker tiene que crear el
> directorio destino en el momento del montaje — solo puede montarse sobre
> un directorio que ya existe. Git no trackea directorios vacíos, así que si
> tu checkout de Uploadrr-EMU tiene un `tmp/` vacío (a diferencia de `data/`,
> que normalmente ya contiene `config.yaml`), créalo a mano una vez:
> `mkdir -p $UPLOADRR_PATH/tmp`.

**Nunca se vendoriza Uploadrr-EMU dentro de la imagen principal.**

---

## 8. Configurar hardlink_base

En el setup web, en la sección **Base**, indica el directorio donde se crearán los hardlinks preparados para subida:

```
/data/uploads/emu
```

> Este directorio debe estar en el mismo filesystem que los archivos fuente (Radarr/Sonarr). Si usas el compose example con `-v /srv/data:/data`, tanto `/data/media` como `/data/uploads/emu` estarán en el mismo montaje y los hardlinks funcionarán sin errores EXDEV.

---

## 9. Configurar TMDb API key

En el setup web, sección **TMDb**, introduce tu API key de The Movie Database.

---

## 10. Configurar eMuwarez API key

En el setup web, sección **eMuwarez**, introduce tu API token de eMuwarez (UNIT3D).

---

## 11. Añadir instancias Radarr y Sonarr

En la sección **Instancias**, añade tus instancias:

- Tipo: `radarr` o `sonarr`
- URL: `http://radarr:7878` (nombre de servicio Docker si en la misma red) o `http://192.168.1.x:7878`
- API key de Radarr/Sonarr

---

## 12. Sincronizar la biblioteca

Desde el Dashboard, pulsa **Sincronizar** o desde CLI:

```bash
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py sync
```

---

## 13. Sincronizar peticiones eMuwarez

Desde el Dashboard o CLI:

```bash
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py requests sync
```

---

## 13b. Evaluar readiness de peticiones (Phase 8B)

Tras sincronizar peticiones, puedes evaluar cuáles están listas para subir:

```bash
# Recalcular readiness de todas las peticiones
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py requests readiness-refresh

# Ver peticiones priorizadas (high → medium → low → blocked)
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py requests prioritized

# Ver readiness de una petición concreta
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py requests readiness <id>

# Ver candidatos locales para una petición
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py requests candidates <id>
```

Desde la UI, en **Peticiones**, aparecen las columnas Readiness, Acción, Prioridad y Candidato, así como el panel "Peticiones accionables" en el Dashboard.

**Garantías de seguridad**: el cálculo de readiness es de solo lectura. No modifica eMuwarez, Radarr, Sonarr ni el filesystem. No ejecuta Uploadrr. Solo escribe en tablas locales de la base de datos.

---

## 14. Generar nomenclatura

Desde la UI, en la sección **Biblioteca**, selecciona un ítem y pulsa **Adaptar nomenclatura** para ver la propuesta de nombre conforme a eMuwarez.

---

## 15. Crear hardlink preparado

En la UI, en el detalle del ítem con nomenclatura adaptada, confirma la creación del hardlink pulsando **Aplicar nomenclatura** e introduciendo el token de confirmación `APLICAR_NOMENCLATURA`.

---

## 16. Preflight Uploadrr

Antes de subir, genera el preflight para verificar que todo está listo:

```bash
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py upload jobs
```

---

## 17. Ejecutar Uploadrr

Desde la UI en **Subidas**, confirma la ejecución introduciendo el token exacto `INICIAR_UPLOADRR`. O desde CLI:

```bash
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py upload start <job_id> --apply --confirm INICIAR_UPLOADRR
```

El comando usa el contrato real de Uploadrr-EMU (ver
[7b](#7b-configurar-el-runtime-uploadrr-emu-fases-10e10f)): `shell=False`,
argv como lista, `config.yaml` stageado/restaurado automáticamente, logs y
`command_preview` con secretos redactados. La UI muestra el progreso
(`Subidas` hace polling cada ~2.5s mientras el job está `running`), los logs
recientes y el resultado (URL/torrent ID) al terminar.

> La ejecución controlada real se ha validado exhaustivamente en tests y en
> el E2E Docker usando un **Uploadrr-EMU fake** (`tests/fixtures/fake_uploadrr_emu.py`)
> — nunca un fork real. La primera ejecución contra tu instalación real de
> Uploadrr-EMU sigue siendo responsabilidad del operador; usa **Probar
> configuración** en Settings y revisa los mounts de `data/`/`tmp/` (sección
> 7b) antes de confiar en una subida real en producción.

---

## 18. Ver logs y resultados

```bash
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py upload status <job_id>   # alias de 'upload job'
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py upload logs <job_id>
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py upload artifacts <job_id>
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py upload cancel <job_id>    # cancela un job en ejecución
```

---

## 19. Backup de /config

La base de datos SQLite y la configuración están en el volumen `/config`:

```bash
tar czf emuwarez-backup-$(date +%Y%m%d).tar.gz /srv/emuwarez-uploadrr/config
```

---

## 20. Actualización

Para actualizar a una nueva versión del código:

```bash
cd ~/emuwarez_uploadrr_cli_ready_v2
git pull
docker compose -f docker-compose.example.yml up -d --build
```

La base de datos se migra automáticamente al arrancar.

---

## 21. Troubleshooting

### El contenedor no arranca

```bash
docker logs emuwarez-uploadrr
```

Busca errores de permisos en `/config`, puertos ocupados o dependencias Python faltantes.

---

### `/api/health` falla o no responde

1. Verifica que el contenedor está corriendo: `docker ps`
2. Verifica el puerto: `docker port emuwarez-uploadrr`
3. Revisa los logs: `docker logs emuwarez-uploadrr --tail 50`

---

### Permisos denegados en /config

El usuario dentro del contenedor (PUID/PGID) no puede escribir en el volumen `/config`.

Solución:

```bash
# Ajusta PUID/PGID en .env al propietario real de los archivos
id $(whoami)
# Luego reinicia
docker compose -f docker-compose.example.yml down
docker compose -f docker-compose.example.yml up -d
```

---

### PUID/PGID incorrectos

Si los archivos de media pertenecen a otro usuario, ajusta en `.env`:

```env
PUID=1001
PGID=1001
```

---

### Uploadrr no está montado

Verifica los bind mounts en el compose (código `:ro`, `data/` y `tmp/` en `rw`):

```yaml
- ${UPLOADRR_PATH:-/srv/Uploadrr}:/opt/Uploadrr:ro
- ${UPLOADRR_DATA_PATH:-/srv/emuwarez-uploadrr/uploadrr-data}:/opt/Uploadrr/data:rw
- ${UPLOADRR_TMP_PATH:-/srv/emuwarez-uploadrr/uploadrr-tmp}:/opt/Uploadrr/tmp:rw
```

Comprueba que las rutas existen en el host:

```bash
ls /srv/Uploadrr
ls /srv/emuwarez-uploadrr/uploadrr-data
ls /srv/emuwarez-uploadrr/uploadrr-tmp
```

El diagnóstico lo detecta:

```bash
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py web doctor
```

---

### Hardlinks fallan con error EXDEV

El error `EXDEV: cross-device link` significa que el directorio fuente y `hardlink_base` están en dispositivos distintos. Los hardlinks solo funcionan dentro del mismo filesystem.

Solución: usa una raíz común para ambos directorios:

```yaml
volumes:
  - /srv/data:/data  # media en /data/media, uploads en /data/uploads/emu
```

Configura en el setup:
- Biblioteca Radarr: `/data/media/movies`
- `hardlink_base`: `/data/uploads/emu`

---

### API keys no configuradas

Usa el setup web (`http://localhost:9494`) o:

```bash
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py web setup-status
```

En Settings (TMDb) y en el setup wizard (TMDb, eMuwarez) puedes usar "Probar conexión" para
validar una key antes de guardarla (Phase 10C).

---

### Radarr/Sonarr no conectan

- Verifica que la URL es accesible desde dentro del contenedor
- Si Radarr/Sonarr también corren en Docker, usa el nombre de servicio y la red compartida
- Comprueba la API key en la interfaz de Radarr/Sonarr
- Usa el botón "Probar conexión" en Settings/Instancias/setup wizard (Phase 10C) antes de
  guardar: prueba la URL/API key escrita en el formulario sin necesidad de guardarla primero

---

### El frontend no carga (pantalla en blanco o 404)

El frontend debe estar construido dentro de la imagen Docker. Reconstruye:

```bash
docker compose -f docker-compose.example.yml up -d --build
```

Verifica que `/app/frontend/dist/index.html` existe en el contenedor:

```bash
docker exec emuwarez-uploadrr ls /app/frontend/dist/
```

---

### Los logs de Uploadrr muestran secretos

Los logs están automáticamente saneados. Si detectas alguna fuga, repórtala como issue. Las API keys nunca deben aparecer en `upload_job_logs`.

---

## Diagnóstico rápido

```bash
# Desde el host
python3 emuwarez_uploader.py web doctor

# Desde el contenedor
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py web doctor
```

---

## Smoke test

Para verificar que la imagen arranca y todos los endpoints responden:

```bash
bash scripts/docker-smoke-test.sh
```

---

## E2E controlado con datos simulados (Phase 9B)

Valida el flujo completo end-to-end en Docker usando datos simulados (sin servicios reales):

```bash
# E2E completo
bash scripts/docker-e2e-demo.sh

# Mantener contenedor para depuración
KEEP_CONTAINER=1 bash scripts/docker-e2e-demo.sh

# Puerto alternativo
PORT=9595 bash scripts/docker-e2e-demo.sh
```

El script:
- Crea un `tmpdir` temporal con estructura de datos simulados
- Construye la imagen Docker
- Arranca el contenedor con volúmenes temporales
- Siembra datos demo via `python3 emuwarez_uploader.py demo seed --confirm DEMO_SEED`
- Valida el flujo: library verify, readiness, queue refresh, action-plan, nomenclature preview, upload preflight
- Verifica que Uploadrr/ no está dentro de la imagen
- Limpia el contenedor y el tmpdir al terminar (salvo `KEEP_CONTAINER=1`)

**No usa Radarr/Sonarr reales. No usa eMuwarez real. No ejecuta Uploadrr real. No sube contenido real.**
