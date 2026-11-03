# Política de seguridad

Este repositorio es privado: solo lo ven quienes tienen acceso a él.

## Versiones con soporte

Solo la última: la imagen `ghcr.io/kisnov/emuwarez-uploadrr:latest`, construida desde `master`. No se mantienen
versiones antiguas.

## Cómo avisar de un fallo de seguridad

Si tienes acceso al repositorio, avisa directamente a Gabriel (Kisnov) o abre un issue aquí, que solo lo ven los
colaboradores. Cuenta qué has visto, qué impacto crees que tiene y cómo reproducirlo, y la versión de la imagen.

Si el fallo está en la subida en sí (el programa que se lanza para subir a eMuwarez), repórtalo en
[Kisnov/Uploadrr-EMU](https://github.com/Kisnov/Uploadrr-EMU/security/advisories/new), que tiene informes privados.

## Qué cuenta

- Entrar o usar la API sin haber iniciado sesión, o con una sesión que ya no debería valer.
- Que una clave salga donde no debe: las de eMuwarez, TMDb, qBittorrent, Radarr/Sonarr o la del widget, en un registro,
  o en una respuesta de la API.
- Leer o escribir ficheros fuera de las carpetas que la aplicación gestiona (biblioteca y carpeta de subidas).
- Ejecutar comandos o acciones no previstas a través de un dato que llega de fuera (un nombre de fichero, un título,
  una respuesta de otro servicio).

## Claves y datos personales

Nunca pegues una clave, el contenido de la base de datos ni una copia de seguridad en un issue, un mensaje o un
registro. Si crees que una clave se ha filtrado, cámbiala primero en el servicio al que pertenece (eMuwarez, TMDb,
qBittorrent…) y avísame después.

## Qué esperar

El mantenimiento lo lleva una sola persona, sin plazos garantizados. Se confirmará el aviso en cuanto se vea y se
arreglará en la siguiente versión que se publique.
