# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Gabriel (Kisnov) y unos pocos conocidos: uploaders hispanohablantes de eMuwarez (tracker privado UNIT3D,
https://emu-warez.com) con Radarr y Sonarr en un NAS doméstico. No es un producto abierto a cualquier uploader. Saben lo que es
un release, un pack, un trump o el seeding; quieren subir contenido de su biblioteca, a menudo para cubrir peticiones con
recompensa, sin hacerlo a mano. Trabajan sobre todo en escritorio (1280-1440 px); el móvil sirve para mirar el estado y
alguna acción suelta.

## Product Purpose

Convierte la biblioteca de Radarr/Sonarr en subidas correctas a eMuwarez sin tocar la biblioteca: sincroniza, cruza con
las peticiones abiertas y con lo que ya hay en el tracker, genera el nombre con la nomenclatura de eMuwarez, enlaza los
ficheros en una carpeta de subidas aparte (para seguir sembrando) y lanza la subida con Uploadrr-EMU, que va dentro de la
imagen. El éxito es subir más y bien (sin rechazos ni duplicados) con menos trabajo manual.

## Positioning

Una herramienta hecha para un solo tracker: conoce su nomenclatura, sus peticiones, su catálogo y su límite de API, y
trabaja sobre la biblioteca real del NAS sin renombrarla ni reescribirla.

## Operating Context

- Autoalojada en Docker en el NAS, junto a Radarr, Sonarr, qBittorrent y Jellyfin; se abre en el navegador del PC.
- Flujos principales: Panel (qué se puede subir hoy), Biblioteca y su ficha, Peticiones, el asistente de subida y «Subir por
  lotes», Subidas y su detalle, Estadísticas del perfil; además Configuración, Tareas, Instancias, Logs y la Guía de la
  nomenclatura.
- Hay una CLI (`emuwarez_uploader.py`) para lo mismo sin interfaz.

## Capabilities and Constraints

- Interfaz, README y docs en castellano.
- Nunca se renombra ni se escriben bytes fuera de la carpeta de subidas: Jellyfin usa los nombres de Sonarr/Radarr y los
  ficheros comparten inodo con torrents que se siembran.
- Autoalojado y de un solo proceso: SQLite, un uvicorn, bus de eventos en memoria; sin servicios externos propios. El
  servidor avisa por `/api/eventos` en vez de que la interfaz sondee.
- Ningún secreto a la vista: las claves de eMuwarez y TMDb nunca salen en logs, respuestas ni pantallas.
- La API de eMuwarez admite 30 llamadas por minuto, compartidas con Uploadrr-EMU.

## Brand Commitments

- Nombre: eMuwarez Uploadrr.
- Voz: directa y técnica, de tú, frases cortas, con la jerga del tracker (release, pack, trump, seeding) sin explicarla.

## Evidence on Hand

- Capturas de la interfaz en `docs/capturas/` (Panel, Biblioteca, Peticiones, pistas, detalle de subida).
- Datos de prueba: `python emuwarez_uploader.py demo seed` siembra una biblioteca ficticia. No hay testimonios, cifras de
  uso ni usuarios externos que citar.

## Product Principles

1. La biblioteca es intocable: cualquier acción que pueda afectarla se hace en la carpeta de subidas o no se hace.
2. Decir la verdad sobre el estado: si algo no se pudo cargar o una instancia no responde, se dice; nunca un vacío que
   parezca «no hay nada».
3. Lo que se puede subir hoy, primero: cada pantalla lleva a la siguiente subida útil con el menor número de pasos.
4. Evitar el rechazo antes de subir: nombre, pistas, castellano y duplicados se comprueban antes del botón «Subir».

## Accessibility & Inclusion

Buenas prácticas, sin un estándar certificado: todo se puede hacer con teclado, foco visible, contraste AA en el texto,
nombres accesibles en los controles y nada que dependa solo del hover.
