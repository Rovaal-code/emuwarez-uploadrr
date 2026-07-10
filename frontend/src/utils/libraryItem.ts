import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'

export function titleMismatchesFilename(item: LibraryItemResponse): boolean {
  if (!item.original_title) return false
  const norm = (s: string) => s.trim().toLowerCase()
  return norm(item.title) !== norm(item.original_title)
}

export function buildDeepLink(item: LibraryItemResponse, instances: InstanceSafeResponse[]): string | null {
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
