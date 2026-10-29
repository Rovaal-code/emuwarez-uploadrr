# Despliegue con Docker

Cómo desplegar eMuwarez Uploadrr con Docker Compose en un servidor o NAS, y qué mirar cuando algo falla. El
[README](../README.md) tiene el arranque rápido; aquí está el porqué de cada ruta y cada permiso.

## 1. Qué necesitas

- Docker 24+ con Compose v2 (`docker compose`).
- Un host Linux con la media de Radarr/Sonarr. El contenedor la lee, la renombra y la enlaza, así que tiene que verla
  y poder escribir en ella.
- qBittorrent para sembrar lo que subes. Es opcional: sin él, los torrents se añaden a mano.
- Las claves: API key y usuario de eMuwarez, API key de TMDb y las de Radarr/Sonarr. Se introducen en el asistente
  web o en Configuración, nunca en el compose ni en el `.env`.

## 2. Las rutas

Es lo único delicado del despliegue. El contenedor trabaja con tres:

| En el contenedor | En el host (ejemplo) | Qué hay |
|---|---|---|
| `/config` | `/srv/emuwarez-uploadrr/config` | Base de datos SQLite, ajustes, backups (`/config/backups`) y el estado de Uploadrr-EMU (`/config/Uploadrr`). |
| `/data` | `/srv/data` | Raíz común: la media de Radarr/Sonarr (`/data/media`) y la carpeta de subidas. |
| `/data/uploads/emu` | `/srv/data/uploads/emu` | Carpeta de subidas, la que indica `UPLOADRR_UPLOADS_DIR`. |

### Qué pasa al subir

1. La app renombra el fichero en la biblioteca a la nomenclatura de eMuwarez.
2. Lo enlaza en la carpeta de subidas. Una película o un capítulo suelto va directamente en la raíz; un pack de
   temporada, en una carpeta con el nombre del release y un enlace por capítulo, para que el torrent se llame como
   el release sin tocar la carpeta de Sonarr.
3. Uploadrr-EMU crea el torrent desde ahí, lo sube a eMuwarez y se lo pasa a qBittorrent con esa carpeta como ruta
   de guardado. qBittorrent siembra desde la carpeta de subidas.

El enlace es **duro** siempre que se puede: otro nombre para los mismos datos, que no ocupa disco. Si no se puede,
la app crea uno **simbólico**. Pasa en estos casos:

- La carpeta de subidas está en otro sistema de ficheros que la media (`EXDEV`).
- La media está en un montaje CIFS o NFS que no admite enlaces duros (`EPERM`).
- `PUID:PGID` no es dueño del fichero de la media ni puede escribirlo: el kernel no deja enlazarlo
  (`fs.protected_hardlinks`, también `EPERM`).
- El fichero ha llegado a su límite de enlaces (`EMLINK`).

Un enlace simbólico solo siembra si qBittorrent puede resolver a dónde apunta, es decir, si también ve la
biblioteca en la misma ruta.

De ahí salen las reglas:

- **La carpeta de subidas va en el mismo sistema de ficheros que la media.** En el ejemplo, las dos cuelgan de
  `/srv/data`, montado como `/data`. Sin `UPLOADRR_UPLOADS_DIR`, la carpeta es `/config/Uploadrr/uploads`, que
  normalmente está en otro disco, y todos los enlaces saldrían simbólicos.
- **qBittorrent ve la carpeta de subidas en la misma ruta que este contenedor.** Si corre en Docker, móntale el
  mismo `/srv/data:/data`. Si corre directamente en el host, donde la ruta es `/srv/data/uploads/emu`, monta la raíz
  con la misma ruta en los dos lados (`/srv/data:/srv/data` y `UPLOADRR_UPLOADS_DIR: /srv/data/uploads/emu`).
- **Si Radarr/Sonarr ven la media en otra ruta** que este contenedor, añade una regla en Configuración →
  Diagnóstico → *Mapeo de rutas (biblioteca remota)*. Traduce la ruta que reportan a la ruta donde la app alcanza
  el fichero, y se aplica al leer el MediaInfo, al verificar y al subir.
- **Rutas permitidas.** La app comprueba que lo que entrega a Uploadrr-EMU está dentro de Configuración → *Acceso a
  la biblioteca* → *Rutas permitidas*, que por defecto es `/data`. Si montas la raíz de datos en otra ruta,
  ponla ahí.

La app no borra los enlaces de una subida completada, porque qBittorrent siembra de ahí. Al borrar una subida en
Subidas solo se quitan los enlaces de los intentos fallidos o cancelados que no use otra subida. El fichero de la
biblioteca nunca se toca.

## 3. Preparar el host

```bash
# UID y GID del dueño de la media: son tu PUID y PGID
id tu_usuario

mkdir -p /srv/emuwarez-uploadrr/config /srv/data/uploads/emu
chown 1000:1000 /srv/emuwarez-uploadrr/config /srv/data/uploads/emu
```

El contenedor corre directamente como `PUID:PGID` (la clave `user:` del compose), sin pasar por root, así que no
puede crear ni cambiar de dueño nada dentro de una carpeta que no sea suya. Por eso las dos carpetas se crean antes
de arrancar y con ese dueño. El mismo usuario tiene que ser dueño de la media, o al menos poder escribir en ella: el
paso 1 de la subida renombra el fichero ahí, y sin eso el enlace del paso 2 sale simbólico.

## 4. El compose

[`docker-compose.yml`](../docker-compose.yml) usa la imagen publicada en `ghcr.io/kisnov/emuwarez-uploadrr`, así que
no compila nada. Lo que hay que mirar:

| Clave | En el repo | Para qué |
|---|---|---|
| `image` | `ghcr.io/kisnov/emuwarez-uploadrr:${EMUWAREZ_UPLOADRR_TAG:-latest}` | `latest` es la última de `master`. Cada imagen se publica también con el SHA completo del commit como etiqueta, para fijar una versión. |
| `ports` | `${EMUWAREZ_UPLOADRR_PORT:-9494}:9494` | Interfaz web y API. |
| `user` | `${PUID:-1000}:${PGID:-1000}` | El usuario con el que corre todo (sección 3). |
| `cpus`, `mem_limit` | `"2"`, `"2g"` | Cada subida activa puede ocupar un núcleo entero (el hash del torrent) y unos 0,8 GB de RAM: con estos valores caben unas dos subidas en paralelo. Si subes *Máximo de Subidas en Paralelo* (Configuración → Otros), sube también estos dos. |
| `TZ` | `Europe/Madrid` | Zona horaria. |
| `CONFIG_DIR` | `/config` | Dónde vive la configuración. No lo cambies. |
| `UPLOADRR_UPLOADS_DIR` | `/data/uploads/emu` | Carpeta de subidas (sección 2). |
| `volumes` | `/srv/emuwarez-uploadrr/config:/config` y `/srv/data:/data` | Cambia la parte del host por tus rutas. |

Si Radarr, Sonarr y qBittorrent corren en Docker, descomenta `networks` y pon el contenedor en su misma red: así
los alcanzas por el nombre del servicio (`http://radarr:7878`).

Para no editar el compose, copia [`.env.example`](../.env.example) a `.env` al lado y ajusta `PUID`, `PGID`, `TZ`,
`EMUWAREZ_UPLOADRR_PORT` y `EMUWAREZ_UPLOADRR_TAG`. Luego:

```bash
docker compose up -d
docker compose ps        # al cabo de unos segundos debe salir (healthy)
```

El estado `healthy` lo da el healthcheck de la imagen, que consulta `/api/health`.

### Construir la imagen tú mismo

[`docker-compose.example.yml`](../docker-compose.example.yml) es el mismo compose, pero construye la imagen desde
el código:

```bash
git clone https://github.com/Kisnov/emuwarez-uploadrr.git
cd emuwarez-uploadrr
cp .env.example .env
docker compose -f docker-compose.example.yml build \
  --build-arg UPLOADRR_COMMIT=$(git ls-remote https://github.com/Kisnov/Uploadrr-EMU.git main | cut -f1)
docker compose -f docker-compose.example.yml up -d
```

`UPLOADRR_COMMIT` hace que Uploadrr-EMU se vuelva a clonar cuando tiene commits nuevos. Sin él, Docker puede
reutilizar de la caché una copia antigua.

## 5. Primer arranque

Abre `http://<IP-del-servidor>:9494`. El asistente de configuración se abre solo:

1. **Bienvenida.**
2. **Crear admin**: usuario y contraseña de al menos 12 caracteres, con mayúsculas, minúsculas, un número y un
   símbolo.
3. **eMuwarez**: API key, tu usuario y el tag del grupo de subida. Para continuar hay que pulsar «Probar conexión» y
   que funcione.
4. **Instancias**: Radarr y/o Sonarr con nombre, URL y API key. La URL es la que alcanza este contenedor: dentro de
   él, `localhost` es el propio contenedor, no el host. «Probar conexión» también avisa si las carpetas raíz de la
   instancia no se ven desde aquí (sección 2).
5. **TMDb**: API key y región. Es obligatoria: traduce los títulos de las series, detecta el proveedor de los
   WEB-DL y la necesita Uploadrr-EMU para la ficha.
6. **qBittorrent**: URL del WebUI, tag, usuario y contraseña. Se puede omitir.
7. **Proveedores de vídeo**: el orden de preferencia cuando el contenido está en varias plataformas.
8. **Imágenes**: dónde se suben las capturas. imgbox va por defecto y no necesita key.
9. **Completar.**

Todo se puede cambiar después en Configuración. Luego, en el Panel, sincroniza la biblioteca (↻ Biblioteca) y las
peticiones; desde Tareas se repiten solas cada cierto tiempo.

Para subir algo, pulsa **Subir** en la Biblioteca. El asistente comprueba el fichero (que se pueda leer, enlazar en
la carpeta de subidas y renombrar), el directorio de salida de Uploadrr-EMU, qBittorrent, el host de imágenes y
eMuwarez; después genera el nombre y lanza la subida. El progreso y los logs están en Subidas.

## 6. Uploadrr-EMU

Va dentro de la imagen, en `/opt/Uploadrr`: no hay nada que montar ni configurar. Al arrancar,
`docker-entrypoint.sh` sustituye `/opt/Uploadrr/data` y `/opt/Uploadrr/tmp` por enlaces a `/config/Uploadrr/data`
y `/config/Uploadrr/tmp`, así que su `config.yaml` y sus temporales sobreviven a recrear el contenedor. La primera
vez, `/config/Uploadrr/data` se copia del que trae la imagen.

Antes de cada subida, la app escribe en `config.yaml` las claves de TMDb y eMuwarez, los hosts de imágenes y
qBittorrent, y al terminar lo restaura desde `config.yaml.bak`. Si quieres tocar algo a mano, edita
`/config/Uploadrr/data/config.yaml.bak`: un cambio en `config.yaml` se pierde en la siguiente subida.

## 7. Actualizar

```bash
docker compose pull
docker compose up -d
```

La base de datos se migra sola. Si construyes la imagen tú, haz `git pull` y repite los dos comandos de
[Construir la imagen tú mismo](#construir-la-imagen-tú-mismo).

## 8. Backup

En Configuración → Backup, «Crear backup ahora» genera un `.tar.gz` de `/config` en `/config/backups`, sin la
carpeta de subidas por defecto (`/config/Uploadrr/uploads`) ni los temporales de Uploadrr-EMU. En la misma pestaña
se restaura. Como queda dentro de `/config`, cópialo a otro disco.

Desde la línea de comandos:

```bash
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py maintenance backup
```

## 9. Problemas frecuentes

### El contenedor se para nada más arrancar

```bash
docker logs emuwarez-uploadrr
```

Si sale `mkdir: cannot create directory ‘/config/Uploadrr’: Permission denied`, el `PUID:PGID` del contenedor no
puede escribir en `/config`. Arréglalo en el host y vuelve a arrancar:

```bash
chown -R 1000:1000 /srv/emuwarez-uploadrr/config   # tu PUID:PGID
docker compose up -d
```

### PUID/PGID no coinciden con el dueño de la media

Con otro usuario, la app no puede renombrar: el asistente de subida falla en «Se puede renombrar». Y aunque pueda
leer la media, el enlace sale simbólico en vez de duro. Pon en el `.env` el UID y GID que da `id` para el dueño de
la media y recrea el contenedor con `docker compose up -d`.

### «No se puede preparar la carpeta de subida»

La carpeta de subidas no existe y el contenedor no ha podido crearla, normalmente porque la carpeta padre es de
root. En el log de arranque sale `No se pudo crear la carpeta de subidas`. Créala con el dueño correcto:

```bash
mkdir -p /srv/data/uploads/emu
chown 1000:1000 /srv/data/uploads/emu
docker compose restart
```

### La comprobación dice «enlace simbólico»

Cuando todo va bien, el asistente muestra `/data/uploads/emu (enlace duro)`. Si dice `enlace simbólico`, mira los
casos de la sección 2: carpeta de subidas en otro sistema de ficheros, montaje sin enlaces duros, o media que no es
de `PUID:PGID`. Funciona solo si qBittorrent ve la biblioteca en la misma ruta, así que conviene arreglarlo:
mueve la carpeta de subidas al sistema de ficheros de la media o corrige el dueño de la media.

### qBittorrent no siembra

Si el torrent sale en qBittorrent con ficheros que faltan, qBittorrent no ve la carpeta de subidas en la misma ruta
que este contenedor. Monta en los dos la misma raíz con la misma ruta (sección 2).

Si en cambio el asistente dice «qBittorrent no conectado», revisa la URL del WebUI en Configuración: tiene que ser
alcanzable desde el contenedor, así que usa la IP del host o el nombre del servicio, no `127.0.0.1`.

### «El archivo no es accesible», o la instancia no deja ver el contenido

El contenedor no ve la media en la ruta que reporta Radarr/Sonarr. O montas la media igual que en Radarr/Sonarr
(`/srv/data:/data` en todos), o añades una regla en Configuración → Diagnóstico → *Mapeo de rutas (biblioteca
remota)*.

### «Directorio de salida no escribible»

Es `/opt/Uploadrr/tmp`, que apunta a `/config/Uploadrr/tmp`. Comprueba que los enlaces existen y que `/config` es
del `PUID:PGID`:

```bash
docker exec emuwarez-uploadrr ls -la /opt/Uploadrr
ls -la /srv/emuwarez-uploadrr/config/Uploadrr
```

`data` y `tmp` tienen que verse como enlaces a `/config/Uploadrr/data` y `/config/Uploadrr/tmp`.

### Pantalla en blanco o 404 en la raíz

- Con la imagen publicada, vuelve a bajarla: `docker compose pull && docker compose up -d`.
- Si la construyes tú, comprueba que el frontend llegó a la imagen:
  `docker exec emuwarez-uploadrr ls /app/frontend/dist/` tiene que mostrar `index.html` y `assets`. Si no, la
  compilación del frontend falló: reconstruye y mira la salida de `npm run build`.
- Detrás de un proxy inverso, sírvela en la raíz de un dominio o subdominio. El frontend pide sus ficheros a
  `/assets/…`, así que en una subruta (`https://servidor/emuwarez/`) la página sale en blanco.

### Construida en Windows, el contenedor no arranca con «no such file or directory»

Git ha convertido `docker-entrypoint.sh` a finales de línea CRLF. Construye desde una copia con LF:

```bash
git -c core.autocrlf=false archive HEAD | docker build -t emuwarez-uploadrr:local -
docker compose -f docker-compose.example.yml up -d
```

### He olvidado la contraseña

```bash
docker exec -it emuwarez-uploadrr python3 emuwarez_uploader.py web reset-password --username admin
```

## 10. Diagnóstico

```bash
docker logs emuwarez-uploadrr --tail 50
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py web doctor
docker exec emuwarez-uploadrr python3 emuwarez_uploader.py web setup-status
```

`web doctor` revisa que `/config` sea escribible, la base de datos, el frontend, Uploadrr-EMU, las rutas permitidas,
las claves de TMDb y eMuwarez, y las instancias de Radarr/Sonarr. En la web, Configuración → Diagnóstico muestra la
versión, la base de datos y el inventario de `/config`, y Logs, los registros de la app y de cada subida. La CLI
completa está en [`README_CLI_READY.md`](../README_CLI_READY.md).
