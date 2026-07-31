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

// A season with EVERY episode Disponible can still fail
// build_season_pack_plan()'s per-episode consistency check (codec/audio/
// idiomas/resolución/source must all match) — the season row's own rollup
// fields (services/library.py's _update_season_rollup, populated at sync
// time) are None precisely when episodes disagree on one of them, so this is
// the same signal wherever a "Subir" trigger needs it (the upload wizard's
// multi-season picker, and the season's own action button), without
// duplicating the check or running the heavier per-episode plan just to grey
// out a button/card.
//
// Subtitles are NOT in this list: eMuwarez takes a pack whose episodes carry
// different subtitle tracks, and doesn't need them at all when the audio is
// already Castilian, so they get the looser has_spanish_ok check below instead
// of being required to match. Mirrors season_pack.py's
// _CONSISTENCY_FIELDS/_spanish_errors.
// Lo único que un pack exige que coincida en todos sus capítulos. Copia de
// season_pack._CONSISTENCY_FIELDS (el frontend no puede llamar a Python): si
// allí cambia, aquí también. Antes eran cinco campos; el resto dejó de
// bloquear y ahora se resume en el nombre del pack.
const SEASON_CONSISTENCY_FIELDS: { key: keyof LibraryItemResponse; label: string }[] = [
  { key: 'resolution', label: 'la resolución' },
]

function seasonInconsistentField(item: LibraryItemResponse) {
  return SEASON_CONSISTENCY_FIELDS.find(f => !item[f.key])
}

// 1 = every held episode carries Castilian, in its audio or its subtitles.
// 0 or null both block the pack: null means we never read some episode's
// tracks, and "we didn't look" is not evidence that the rule is met.
function seasonMissingSpanish(item: LibraryItemResponse): boolean {
  return item.has_spanish_ok !== 1
}

export function isSeasonReady(item: LibraryItemResponse): boolean {
  if (item.item_type !== 'season') return true
  return item.local_status === 'Disponible'
    && !seasonInconsistentField(item)
    && !seasonMissingSpanish(item)
}

// An episode uploaded ON ITS OWN answers only for itself: you have to hold the
// file, and it has to carry Castilian somewhere. The season pack's rules —
// every episode agreeing on codec/audio/resolution/source, the whole season
// present — deliberately do NOT apply here, and that is the entire point of
// the per-episode mode: those rules exist because a pack ships ONE release
// name for everything inside it, while each episode ships its own, which can
// state its own codec and audio truthfully.
export function episodeNotReadyReason(item: LibraryItemResponse): string | null {
  if (item.local_status !== 'Disponible' && item.local_status !== 'Subido') {
    return `No se puede subir: el capítulo está "${item.local_status}", no lo tienes en disco.`
  }
  if (item.has_spanish_ok !== 1) {
    return item.has_spanish_ok === 0
      ? 'No se puede subir: no tiene castellano ni en el audio ni en los subtítulos.'
      : 'No se puede subir: no se han podido leer sus pistas, así que no se puede confirmar que tenga castellano.'
  }
  return null
}

// null when the season IS ready (or isn't a season) — a truthy reason string
// otherwise, for a disabled button/card's tooltip.
export function seasonNotReadyReason(item: LibraryItemResponse): string | null {
  if (item.item_type !== 'season') return null
  if (item.local_status !== 'Disponible') return null // caller already has its own "incomplete" message
  const field = seasonInconsistentField(item)
  if (field) {
    return `Los capítulos de esta temporada no coinciden en ${field.label}. Revísalos antes de subir el pack.`
  }
  if (seasonMissingSpanish(item)) {
    return 'Algún capítulo de esta temporada no tiene castellano ni en el audio ni en los subtítulos. eMuwarez lo exige en todos para aceptar el pack.'
  }
  return null
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
