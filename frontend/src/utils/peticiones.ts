import type { RequestItemResponse } from '../types/api'

// El título de una petición en una lista: el mismo en Peticiones y en el carril
// «Peticiones listas para subir» del Panel.
//
// The raw eMuwarez title is whatever the requester typed there — for a
// season/episode-scoped request it doesn't reliably say WHICH one, so the
// suffix is appended here, same format as the one this app itself builds
// when creating a petición (RequestFormModal): " - Temporada X" / " - SxxExx".
// Skipped if the title already ends in something matching that pattern (the
// requester already spelled it out on eMuwarez's own site).
// The year (when matched to a library item) is inserted right after `base`,
// before the " - Temporada X"/" - SxxEyy" suffix — same "Serie (Año) - …"
// convention as every other table/dedicated page (see DetailTitleText,
// which the callers wrap this in for the muted-gray styling).
export function requestDisplayTitle(item: Pick<RequestItemResponse,
  'title' | 'library_year' | 'req_scope' | 'req_season' | 'req_episode'>): string {
  const base = item.title || ''
  const year = item.library_year ? ` (${item.library_year})` : ''
  if (item.req_scope === 'season' && item.req_season != null && !/temporada\s*\d+\s*$/i.test(base)) {
    return `${base}${year} - Temporada ${item.req_season}`
  }
  if (item.req_scope === 'episode' && item.req_season != null && item.req_episode != null && !/S\d{1,2}E\d{1,3}\s*$/i.test(base)) {
    const code = `S${String(item.req_season).padStart(2, '0')}E${String(item.req_episode).padStart(2, '0')}`
    return `${base}${year} - ${code}`
  }
  return `${base}${year}`
}
