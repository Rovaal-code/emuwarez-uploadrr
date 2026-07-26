import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'

// "Aportes" only makes sense for content you actually have: a leaf item
// (movie/episode) that's Disponible/Subido/Subiendo, or a series/season
// rollup that's at least Parcial. A Faltante item has nothing to contribute,
// even if eMuwarez's catalog happens not to have it either.
const APORTE_ELIGIBLE_STATUS = new Set(['Disponible', 'Subido', 'Subiendo', 'Parcial'])
export function isAporteEligible(item: LibraryItemResponse): boolean {
  return APORTE_ELIGIBLE_STATUS.has(item.local_status ?? '')
}

// Episode title in the Biblioteca LIST/tree view: just "NombreSerie - SxEx",
// never the per-episode title (Sonarr's own episode titles can be very
// long and break the row layout) — the full descriptive title still shows
// in the episode's own dedicated ficha, this only applies to the list.
export function episodeListLabel(item: LibraryItemResponse): string {
  if (item.item_type !== 'episode' || item.season_number == null || item.episode_number == null) {
    return item.title
  }
  const code = `S${String(item.season_number).padStart(2, '0')}E${String(item.episode_number).padStart(2, '0')}`
  const seriesName = item.title.split(/\s+S\d{2}E\d{2}\b/i)[0] || item.title
  return `${seriesName} - ${code}`
}

// List/tree row title with the year placed right after the series name —
// "NombreSerie (Año) - Temporada X" / "NombreSerie (Año) - SxxEyy" — instead
// of at the very end of the whole label. Purely local (no parent-walk DB
// query, unlike display_title on the single-item detail response): the
// series name for a season/episode row is recovered from that row's own
// title text (built at sync time as "{series} - Temporada N"/"{series}
// SxxEyy - Nombre" — see season_to_library_item/episode_to_library_item),
// so this works for every row already loaded by the list.
export function listDisplayTitle(item: LibraryItemResponse): string {
  const year = item.year ? ` (${item.year})` : ''
  if (item.item_type === 'episode' && item.season_number != null && item.episode_number != null) {
    const code = `S${String(item.season_number).padStart(2, '0')}E${String(item.episode_number).padStart(2, '0')}`
    const seriesName = item.title.split(/\s+S\d{2}E\d{2}\b/i)[0] || item.title
    return `${seriesName}${year} - ${code}`
  }
  if (item.item_type === 'season') {
    const idx = item.title.indexOf(' - ')
    if (idx !== -1) {
      return `${item.title.slice(0, idx)}${year} - ${item.title.slice(idx + 3)}`
    }
  }
  return `${item.title}${year}`
}

export function titleMismatchesFilename(item: LibraryItemResponse): boolean {
  if (!item.original_title) return false
  const norm = (s: string) => s.trim().toLowerCase()
  return norm(item.title) !== norm(item.original_title)
}

// Narrower than LibraryItemResponse on purpose — UploadJob carries these same
// 4 fields (from its linked library item) to build the identical Origen deep
// link Biblioteca's own column uses, without needing a full library item.
interface DeepLinkable {
  instance_id?: number | null
  instance_type?: string | null
  tmdb_id?: string | null
  title_slug?: string | null
}

export function buildDeepLink(item: DeepLinkable, instances: InstanceSafeResponse[]): string | null {
  if (!item.instance_id) return null
  const instance = instances.find(i => i.id === item.instance_id)
  if (!instance) return null
  if (item.instance_type === 'radarr' && item.tmdb_id) {
    return `${instance.url}/movie/${item.tmdb_id}`
  }
  if (item.instance_type === 'sonarr' && item.title_slug) {
    return `${instance.url}/series/${item.title_slug}`
  }
  return null
}

// TMDB serves resized posters via a size segment in the path
// (…/t/p/w185/…). Items are stored with the full-size "original" URL, which is
// multiple MB each and painfully slow to load in a grid. Rewrite to a small
// size per view: thumbnails (w92/w154), grid cards (w342), detail (w500).
export type PosterSize = 'w92' | 'w154' | 'w185' | 'w342' | 'w500'
export function posterUrl(url: string | null | undefined, size: PosterSize = 'w342'): string | undefined {
  if (!url) return undefined
  return url.replace(/\/t\/p\/(original|w\d+)\//, `/t/p/${size}/`)
}

// Public page for an external ID so the user can open it in TMDb/IMDb/TheTVDB/MAL.
export function idVerifyUrl(kind: 'tmdb' | 'imdb' | 'tvdb' | 'mal', id: string | null | undefined, isTv: boolean): string | null {
  if (!id) return null
  const digits = id.replace(/\D+/g, '')
  if (!digits) return null
  switch (kind) {
    case 'tmdb': return `https://www.themoviedb.org/${isTv ? 'tv' : 'movie'}/${digits}`
    case 'imdb': return `https://www.imdb.com/title/tt${digits.padStart(7, '0')}/`
    case 'tvdb': return `https://thetvdb.com/dereferrer/series/${digits}`
    case 'mal':  return `https://myanimelist.net/anime/${digits}`
  }
}
