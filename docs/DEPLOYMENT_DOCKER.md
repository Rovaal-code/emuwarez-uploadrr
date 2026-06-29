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

---

## 18. Ver logs y resultados

```bash
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py upload logs <job_id>
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py upload artifacts <job_id>
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

Verifica el bind mount en el compose:

```yaml
- /ruta/real/a/Uploadrr:/opt/Uploadrr
```

Comprueba que `/ruta/real/a/Uploadrr` existe en el host:

```bash
ls /srv/Uploadrr
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

---

### Radarr/Sonarr no conectan

- Verifica que la URL es accesible desde dentro del contenedor
- Si Radarr/Sonarr también corren en Docker, usa el nombre de servicio y la red compartida
- Comprueba la API key en la interfaz de Radarr/Sonarr

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
