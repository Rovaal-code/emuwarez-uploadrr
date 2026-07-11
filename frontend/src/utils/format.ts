// Formatting utilities

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || bytes === 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit++
  }
  return `${value.toFixed(1)} ${units[unit]}`
}

// Backend timestamps are UTC. Some carry a 'Z'/offset (ISO), others are naive
// ("YYYY-MM-DD HH:MM:SS" from SQLite CURRENT_TIMESTAMP). Browsers parse a naive
// string as *local* time, which shifts the displayed hour by the tz offset —
// so treat a timezone-less string as UTC before converting to local.
export function parseServerDate(dateStr: string): Date {
  const s = dateStr.trim()
  const hasTz = /([zZ]|[+-]\d{2}:?\d{2})$/.test(s)
  return new Date(hasTz ? s.replace(' ', 'T') : s.replace(' ', 'T') + 'Z')
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    return parseServerDate(dateStr).toLocaleString('es-ES', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}

export function formatDateShort(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    return parseServerDate(dateStr).toLocaleString('es-ES', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return dateStr
  }
}

export function formatItemType(type: string): string {
  const map: Record<string, string> = {
    movie: 'Película',
    series: 'Serie',
    season: 'Temporada',
    episode: 'Episodio',
  }
  return map[type] ?? type
}
