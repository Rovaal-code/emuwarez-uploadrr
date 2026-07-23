// Shared by every form that takes a Radarr/Sonarr/qBittorrent base URL
// (Setup wizard, Instancias, Configuración) — catches obvious garbage
// client-side instead of waiting on a round-trip to the backend's own
// validators (which reject the same thing, but only after a submit).
export function isValidHttpUrl(value: string): boolean {
  const v = value.trim()
  if (!v) return false
  try {
    const u = new URL(v)
    return u.protocol === 'http:' || u.protocol === 'https:'
  } catch {
    return false
  }
}
