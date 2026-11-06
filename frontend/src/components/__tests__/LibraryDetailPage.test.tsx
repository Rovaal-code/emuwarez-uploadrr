// @vitest-environment jsdom
// La ficha de Biblioteca: un dato técnico que falta se ve igual en toda la tarjeta (un «—» suelto, sin ficha).
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LibraryItemResponse } from '../../types/api'
import { LibraryDetailPage } from '../LibraryDetailPage'
import { desmontar, montar } from './dom'

vi.mock('../../api/library', () => ({ getLibraryItem: vi.fn(), getLibrary: vi.fn(), getEmuComparison: vi.fn() }))
vi.mock('../EmuComparisonSection', () => ({ EmuFieldChip: () => null }))

afterEach(desmontar)

function pelicula(parcial: Partial<LibraryItemResponse>): LibraryItemResponse {
  return {
    id: 1, item_type: 'movie', title: 'Dune (2021)', display_title: null, year: 2021, original_title: null,
    instance_type: 'radarr', instance_name: 'Radarr', instance_id: 7, external_id: null, tmdb_id: null, imdb_id: null,
    tvdb_id: null, mal_id: null, title_slug: null, season_number: null, episode_number: null, parent_id: null,
    path: null, quality: null, resolution: '1080p', source: null, provider: null, provider_label: null,
    video_codec: null, audio_codec: null, audio_languages: null, has_spanish_audio: 0, has_spanish_subs: 0,
    has_spanish_ok: 0, subtitle_languages: null, size_bytes: null, local_status: 'Disponible',
    request_status: 'Sin petición', nomenclature_status: '', updated_at: null, release_group: null,
    ...parcial,
  } as LibraryItemResponse
}

async function montarFicha(item: LibraryItemResponse) {
  await montar(<LibraryDetailPage item={item} instances={[]} onBack={() => {}} onSelect={() => {}} onAction={() => {}} />)
}

/** El valor de la fila `etiqueta` de la ficha. */
function valor(etiqueta: string) {
  const fila = [...document.querySelectorAll('.detcard-fila')]
    .find(f => f.querySelector('.detcard-fila-etiqueta')?.textContent?.trim() === etiqueta)
  return fila!.querySelector('.detcard-fila-valor')!
}

describe('Tamaño en Información técnica', () => {
  it('sin tamaño es un «—» suelto, como el resto de datos que faltan, y no una ficha con icono', async () => {
    await montarFicha(pelicula({ size_bytes: null }))
    expect(valor('Tamaño').querySelector('.value-chip')).toBeNull()
    expect(valor('Tamaño').textContent).toBe('—')
    expect(valor('Source').querySelector('.value-chip')).toBeNull()
  })

  it('con tamaño, su ficha con el valor', async () => {
    await montarFicha(pelicula({ size_bytes: 3 * 1024 ** 3 }))
    expect(valor('Tamaño').querySelector('.value-chip')?.textContent).toBe('3,0 GB')
  })
})
