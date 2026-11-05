// @vitest-environment jsdom
// La fila de Biblioteca: cada dato filtrable en su columna y, bajo el título, solo tipo, códec e idiomas.
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { InstanceSafeResponse, LibraryItemResponse } from '../../types/api'
import { LibraryTreeRow } from '../LibraryTreeRow'
import { especificaciones } from '../LineaDeCalidad'
import { desmontar, montar } from './dom'

vi.mock('../../api/library', () => ({ getLibrary: vi.fn() }))

afterEach(desmontar)

function elemento(parcial: Partial<LibraryItemResponse>): LibraryItemResponse {
  return {
    id: 1, item_type: 'movie', title: 'Dune (2021)', display_title: null, year: 2021, original_title: null,
    instance_type: 'radarr', instance_name: 'Radarr 4K', instance_id: 7, external_id: null, tmdb_id: '438631', imdb_id: null,
    tvdb_id: null, mal_id: null, title_slug: null, season_number: null, episode_number: null, parent_id: null,
    path: null, quality: null, resolution: '1080p', source: 'WEB-DL', provider: 'NF', provider_label: 'NF',
    video_codec: 'HEVC', audio_codec: null, audio_languages: 'es,en', has_spanish_audio: 1, has_spanish_subs: 1,
    has_spanish_ok: 1, subtitle_languages: null, size_bytes: 3 * 1024 ** 3, local_status: 'Disponible',
    request_status: '', nomenclature_status: '', updated_at: null, release_group: 'FLUX',
    ...parcial,
  } as LibraryItemResponse
}

const INSTANCIAS = [{ id: 7, type: 'radarr', name: 'Radarr 4K', url: 'http://radarr:7878' }] as InstanceSafeResponse[]

async function montarFila(item: LibraryItemResponse, instances: InstanceSafeResponse[] = INSTANCIAS) {
  await montar(
    <table><tbody>
      <LibraryTreeRow item={item} depth={0} instances={instances} onSelect={() => {}} onAction={() => {}} />
    </tbody></table>,
  )
}

const celdas = () => [...document.querySelectorAll<HTMLTableCellElement>('tr.bib-fila > td')]

describe('especificaciones', () => {
  it('une tipo, códec e idiomas del audio, en ese orden', () => {
    expect(especificaciones(elemento({}))).toEqual(['Película', 'HEVC', 'es,en'])
  })

  it('se salta lo que no se sabe', () => {
    expect(especificaciones(elemento({ audio_languages: null }))).toEqual(['Película', 'HEVC'])
  })
})

describe('LibraryTreeRow', () => {
  it('bajo el título solo lleva lo que no se filtra: tipo, códec e idiomas', async () => {
    await montarFila(elemento({}))
    const bajo = document.querySelector('.bib-titulo-caja .bib-spec-texto')!.textContent!
    expect(bajo).toBe('Película · HEVC · es,en')
    for (const dato of ['1080p', 'WEB-DL', 'NF', 'FLUX', 'Radarr']) expect(bajo).not.toContain(dato)
  })

  it('tiene doce celdas, una por columna, y el título no lleva grupo ni origen', async () => {
    await montarFila(elemento({}))
    expect(celdas()).toHaveLength(12)
    expect(celdas()[0].querySelector('.bib-rg-ninguno, .value-chip, a')).toBeNull()
  })

  it('cada dato filtrable va en su propia celda, en el orden de las cabeceras', async () => {
    await montarFila(elemento({}))
    const c = celdas()
    expect(c[1].textContent).toBe('Radarr 4K')           // Origen
    expect(c[4].textContent).toBe('1080p')               // Resolución
    expect(c[5].textContent).toBe('NF')                  // Proveedor
    expect(c[6].textContent).toBe('WEB-DL')              // Fuente
    expect(c[7].textContent).toBe('FLUX')                // Grupo
  })

  it('el origen enlaza a su instancia cuando se sabe dónde está', async () => {
    await montarFila(elemento({}))
    const enlace = celdas()[1].querySelector<HTMLAnchorElement>('a')!
    expect(enlace.getAttribute('href')).toBe('http://radarr:7878/movie/438631')
    expect(enlace.textContent).toBe('Radarr 4K')
  })

  it('sin enlace posible deja el origen como texto', async () => {
    await montarFila(elemento({}), [])
    expect(celdas()[1].querySelector('a')).toBeNull()
    expect(celdas()[1].textContent).toBe('Radarr 4K')
  })

  it('sin origen, resolución, proveedor ni source pone un guion en cada celda', async () => {
    await montarFila(elemento({ instance_type: null, instance_name: null, resolution: null, provider: null, provider_label: null, source: null }))
    for (const i of [1, 4, 5, 6]) expect(celdas()[i].textContent).toBe('—')
  })

  it('con grupo de release lo pone en una insignia en la columna Grupo', async () => {
    await montarFila(elemento({}))
    expect(celdas()[7].querySelector('.value-chip')!.textContent).toBe('FLUX')
  })

  it('sin grupo de release dice «sin grupo» en vez de dejar un hueco', async () => {
    await montarFila(elemento({ release_group: null }))
    expect(celdas()[7].textContent).toBe('sin grupo')
    expect(celdas()[7].querySelector('.value-chip')).toBeNull()
  })

  it('una serie con varios grupos los junta en «Varios»', async () => {
    await montarFila(elemento({ item_type: 'series', release_group: null, release_groups: ['FLUX', 'NTb'] }))
    expect(celdas()[7].textContent).toBe('Varios (2)')
  })

  it('el póster pide w154, como el del Panel', async () => {
    await montarFila(elemento({ poster_url: 'https://image.tmdb.org/t/p/w500/abc.jpg' }))
    expect(document.querySelector('.poster-thumb.bib-miniatura')).not.toBeNull()
    expect(document.querySelector<HTMLImageElement>('.bib-miniatura img')!.getAttribute('src')).toContain('w154')
  })
})
