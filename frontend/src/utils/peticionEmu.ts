import { EMU_URL } from '../constants/emu'

// Ids de categoría de eMuwarez (EMU_CATEGORIAS en integrations/emu.py).
const CATEGORY_IDS: Record<string, string> = { movie: '1', tv: '2', doc: '4' }

/** El formulario de crear petición de eMuwarez, rellenado con los parámetros
 *  que lee RequestController@create de UNIT3D. Los ids van sin prefijo (el
 *  de IMDb sin "tt") y se omiten los que faltan. */
export function urlCrearPeticion(p: {
  category: string; title: string; imdb: string; tmdb: string; tvdb: string; mal: string
}): string {
  const isSeries = p.category !== 'movie'
  // El título va codificado dos veces, como en los enlaces del propio UNIT3D:
  // el controlador le aplica urldecode() además de la decodificación de la URL.
  const params = new URLSearchParams({ category_id: CATEGORY_IDS[p.category], title: encodeURIComponent(p.title) })
  if (p.imdb) params.set('imdb', p.imdb)
  if (p.tmdb) params.set(isSeries ? 'tmdb_tv_id' : 'tmdb_movie_id', p.tmdb)
  if (isSeries && p.tvdb) params.set('tvdb', p.tvdb)
  if (p.mal) params.set('mal', p.mal)
  return `${EMU_URL}/requests/create?${params}`
}
