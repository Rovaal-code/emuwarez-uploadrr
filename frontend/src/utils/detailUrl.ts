// Keeps a detail view's numeric id in sync with the URL — /<base>/<id> while
// it's open, back to /<base> when it closes — so a deep link to one specific
// movie/season/episode/upload/request is bookmarkable and survives a reload,
// and the browser back button closes the detail view instead of leaving the
// app. `base` is always one of AppShell's own VALID_PAGES tab names
// (e.g. 'library', 'uploads', 'requests').

/** El id de la ficha en una ruta, o null. Puro, para poder probarlo: es la
 *  regla que decide qué se abre al pegar un enlace. */
export function idEnLaRuta(pathname: string, base: string): number | null {
  const parts = pathname.replace(/^\/+/, '').split('/')
  if (parts[0] !== base || !parts[1]) return null
  const id = Number(parts[1])
  return Number.isFinite(id) ? id : null
}

/** Si la ruta pertenece a esa sección, con ficha abierta o sin ella. */
export function esDeLaSeccion(pathname: string, base: string): boolean {
  return pathname.replace(/^\/+/, '').split('/')[0] === base
}

export function getDetailIdFromPath(base: string): number | null {
  return idEnLaRuta(window.location.pathname, base)
}

export function pushDetailPath(base: string, id: number) {
  const path = `/${base}/${id}`
  if (window.location.pathname !== path) {
    window.history.pushState({}, '', path)
  }
}

export function closeDetailPath(base: string) {
  // Solo si de verdad estás en esa sección. Al salir de una, la sección se
  // reinicia y cierra su ficha (ver context/SeccionVisible::useAlSalir), pero
  // eso ocurre DESPUÉS de que la navegación haya puesto la URL de la sección
  // nueva: sin esta comprobación, salir de Biblioteca con una ficha abierta
  // dejaba la barra de direcciones diciendo /library estando ya en Subidas.
  if (!esDeLaSeccion(window.location.pathname, base)) return
  const path = `/${base}`
  if (window.location.pathname !== path) {
    window.history.replaceState({}, '', path)
  }
}
