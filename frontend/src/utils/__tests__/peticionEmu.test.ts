/**
 * El enlace al formulario de crear petición de eMuwarez. UNIT3D le aplica
 * urldecode() al título después de decodificar la URL, así que un título con
 * "+" o "%" llegaba cambiado si se codificaba una sola vez.
 */
import { describe, it, expect } from 'vitest'
import { urlCrearPeticion } from '../peticionEmu'

const ids = { imdb: '', tmdb: '', tvdb: '', mal: '' }

// Lo que hace Laravel: $request->title y después urldecode().
const tituloEnUnit3d = (url: string) =>
  decodeURIComponent(new URL(url).searchParams.get('title')!.replace(/\+/g, ' '))

describe('el enlace para crear una petición', () => {
  it('una película lleva categoría 1 y tmdb_movie_id', () => {
    const url = new URL(urlCrearPeticion({ ...ids, category: 'movie', title: 'Dune (2021)', imdb: '1160419', tmdb: '438631' }))
    expect(url.origin + url.pathname).toBe('https://emu-warez.com/requests/create')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      category_id: '1', title: encodeURIComponent('Dune (2021)'), imdb: '1160419', tmdb_movie_id: '438631',
    })
  })

  it('una serie lleva categoría 2, tmdb_tv_id, tvdb y mal', () => {
    const url = new URL(urlCrearPeticion({ category: 'tv', title: 'Frieren (2023)', imdb: '22248376', tmdb: '209867', tvdb: '424536', mal: '52991' }))
    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      category_id: '2', tmdb_tv_id: '209867', tvdb: '424536', mal: '52991',
    })
    expect(url.searchParams.has('tmdb_movie_id')).toBe(false)
  })

  it('un documental lleva categoría 4', () => {
    expect(new URL(urlCrearPeticion({ ...ids, category: 'doc', title: 'X' })).searchParams.get('category_id')).toBe('4')
  })

  it('omite los ids que faltan', () => {
    const url = new URL(urlCrearPeticion({ ...ids, category: 'movie', title: 'X' }))
    expect([...url.searchParams.keys()]).toEqual(['category_id', 'title'])
  })

  it('el título llega intacto tras el urldecode de UNIT3D', () => {
    const title = 'Love + Death 100% (2023) - S01E02'
    expect(tituloEnUnit3d(urlCrearPeticion({ ...ids, category: 'tv', title }))).toBe(title)
  })
})
