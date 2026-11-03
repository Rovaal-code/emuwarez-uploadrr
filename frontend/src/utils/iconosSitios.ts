// Los iconos de los sitios que enseña la interfaz (proveedores de imágenes y de vídeo, eMuwarez, TMDb…) van dentro
// del proyecto, en assets/iconos/<dominio>.<ext>: los logos no cambian y la lista es cerrada, así que el navegador
// no pide nada a nadie de fuera. Se bajan con `python scripts/descargar_iconos.py`; para un sitio nuevo, se vuelve
// a correr (un test avisa si falta el de alguno).
//
// `?no-inline`: Vite pegaría los pequeños dentro del JS como data:, y aquí interesa que cada uno sea un fichero
// que el navegador pide solo si lo pinta.
const ICONOS = (import.meta as unknown as {
  glob: (pattern: string, opts: object) => Record<string, string>
}).glob('../assets/iconos/*', { eager: true, query: '?no-inline', import: 'default' })

const POR_DOMINIO = new Map<string, string>()
for (const [ruta, url] of Object.entries(ICONOS)) {
  POR_DOMINIO.set(ruta.split('/').pop()!.replace(/\.[^.]+$/, '').toLowerCase(), url)
}

/** La URL del icono del dominio (p. ej. `netflix.com`), o null si no hay. */
export function iconoDe(dominio: string): string | null {
  return POR_DOMINIO.get(dominio.toLowerCase()) ?? null
}
