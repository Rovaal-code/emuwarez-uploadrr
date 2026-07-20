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

// Same as formatDate but with seconds — Subidas' Creado/Finalizado need
// second-level precision (unlike Biblioteca/Peticiones' timestamps, where
// minute precision is enough) since Progreso/Duración already tick in
// seconds and jobs frequently start/finish within the same minute.
export function formatDateTimeSeconds(dateStr: string | null | undefined): string {
  if (!dateStr) return '–'
  try {
    return parseServerDate(dateStr).toLocaleString('es-ES', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
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

// Relative "hace X" label in Spanish (for the requests table).
export function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    const secs = Math.max(0, Math.floor((Date.now() - parseServerDate(dateStr).getTime()) / 1000))
    if (secs < 60) return 'hace segundos'
    const mins = Math.floor(secs / 60)
    if (mins < 60) return `hace ${mins} min`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `hace ${hours} h`
    const days = Math.floor(hours / 24)
    if (days < 30) return `hace ${days} día${days === 1 ? '' : 's'}`
    const months = Math.floor(days / 30)
    if (months < 12) return `hace ${months} mes${months === 1 ? '' : 'es'}`
    const years = Math.floor(days / 365)
    return `hace ${years} año${years === 1 ? '' : 's'}`
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
