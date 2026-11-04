// @vitest-environment jsdom
// La fila de Biblioteca: línea de especificaciones bajo el título, grupo de release y origen, sin columnas repetidas.
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

describe('especificaciones', () => {
  it('une tipo, resolución, source, proveedor, códec e idiomas, en ese orden', () => {
    expect(especificaciones(elemento({}))).toEqual(['Película', '1080p', 'WEB-DL', 'NF', 'HEVC', 'es,en'])
  })

  it('se salta lo que no se sabe', () => {
    expect(especificaciones(elemento({ source: null, provider: null, provider_label: null, audio_languages: null })))
      .toEqual(['Película', '1080p', 'HEVC'])
  })
})

describe('LibraryTreeRow', () => {
  it('enseña la línea de calidad bajo el título', async () => {
    await montarFila(elemento({}))
    expect(document.querySelector('.bib-spec-texto')!.textContent).toBe('Película · 1080p · WEB-DL · NF · HEVC · es,en')
  })

  it('con grupo de release lo pone en una insignia junto al título', async () => {
    await montarFila(elemento({}))
    expect(document.querySelector('.bib-titulo-cab .bib-rg .value-chip')!.textContent).toBe('FLUX')
  })

  it('sin grupo de release dice «sin grupo» en vez de dejar un hueco', async () => {
    await montarFila(elemento({ release_group: null }))
    expect(document.querySelector('.bib-rg')!.textContent).toBe('sin grupo')
    expect(document.querySelector('.bib-rg .value-chip')).toBeNull()
  })

  it('una serie con varios grupos los junta en «Varios»', async () => {
    await montarFila(elemento({ item_type: 'series', release_group: null, release_groups: ['FLUX', 'NTb'] }))
    expect(document.querySelector('.bib-rg')!.textContent).toBe('Varios (2)')
  })

  it('el origen enlaza a su instancia cuando se sabe dónde está', async () => {
    await montarFila(elemento({}))
    const enlace = document.querySelector<HTMLAnchorElement>('a.bib-spec-origen')!
    expect(enlace.getAttribute('href')).toBe('http://radarr:7878/movie/438631')
    expect(enlace.textContent).toBe('Radarr 4K')
  })

  it('sin enlace posible deja el origen como texto', async () => {
    await montarFila(elemento({}), [])
    expect(document.querySelector('a.bib-spec-origen')).toBeNull()
    expect(document.querySelector('span.bib-spec-origen')!.textContent).toBe('Radarr 4K')
  })

  it('sin origen no pone nada en su sitio', async () => {
    await montarFila(elemento({ instance_type: null, instance_name: null }))
    expect(document.querySelector('.bib-spec-origen')).toBeNull()
  })

  it('tiene siete celdas: lo que se repetía en cada fila ya no tiene columna', async () => {
    await montarFila(elemento({}))
    expect(document.querySelectorAll('tr.bib-fila > td')).toHaveLength(7)
  })
})
