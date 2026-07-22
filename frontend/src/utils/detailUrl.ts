// Keeps a detail view's numeric id in sync with the URL — /<base>/<id> while
// it's open, back to /<base> when it closes — so a deep link to one specific
// movie/season/episode/upload/request is bookmarkable and survives a reload,
// and the browser back button closes the detail view instead of leaving the
// app. `base` is always one of AppShell's own VALID_PAGES tab names
// (e.g. 'library', 'uploads', 'requests').

export function getDetailIdFromPath(base: string): number | null {
  const parts = window.location.pathname.replace(/^\/+/, '').split('/')
  if (parts[0] !== base || !parts[1]) return null
  const id = Number(parts[1])
  return Number.isFinite(id) ? id : null
}

export function pushDetailPath(base: string, id: number) {
  const path = `/${base}/${id}`
  if (window.location.pathname !== path) {
    window.history.pushState({}, '', path)
  }
}

export function closeDetailPath(base: string) {
  const path = `/${base}`
  if (window.location.pathname !== path) {
    window.history.replaceState({}, '', path)
  }
}
