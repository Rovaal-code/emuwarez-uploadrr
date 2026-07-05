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
