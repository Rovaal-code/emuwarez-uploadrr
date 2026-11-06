// @vitest-environment jsdom
/**
 * El asistente de subida de punta a punta, con el servidor simulado: lo que pide, lo que enseña y lo que encola
 * en cada camino (película, pack de temporada, varias temporadas, varios capítulos), y cómo se cierra.
 */
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/nomenclature', () => ({
  getEmuSources: vi.fn(), getEmuProviders: vi.fn(), getNomenclatureFields: vi.fn(),
  previewNomenclatureFields: vi.fn(), saveNomenclatureFields: vi.fn(),
  previewTrackRemux: vi.fn(), applyTrackRemux: vi.fn(),
}))
vi.mock('../../api/uploads', () => ({
  queueUpload: vi.fn(), getExistingJobForItem: vi.fn(), runUploadChecks: vi.fn(), getUploadChecksProgress: vi.fn(),
}))
vi.mock('../../api/library', () => ({
  getLibrary: vi.fn(), getMediaInfoReport: vi.fn(), suggestProvider: vi.fn(),
  getEmuComparison: vi.fn(), getEmuSyncStatus: vi.fn(), getLibraryItem: vi.fn(),
}))
vi.mock('../../api/requests', () => ({ getRequestDetail: vi.fn() }))
vi.mock('../../api/seasonPack', () => ({
  previewSeasonPack: vi.fn(), getSeasonPlanProgress: vi.fn(), getSeasonEpisodeNames: vi.fn(),
  cancelSeasonPackPreview: vi.fn(), getSeasonEpisodeMediaInfo: vi.fn(), getSeasonEpisodeRemuxPreview: vi.fn(),
  previewSeasonPackFields: vi.fn(), getSeasonPackAudio: vi.fn(),
}))
vi.mock('../../api/eventos', () => ({ seguirProgreso: vi.fn(() => () => {}) }))
vi.mock('../../api/settings', () => ({ fetchSettings: vi.fn() }))

import * as nom from '../../api/nomenclature'
import * as subidas from '../../api/uploads'
import * as biblioteca from '../../api/library'
import * as temporada from '../../api/seasonPack'
import { getRequestDetail } from '../../api/requests'
import { fetchSettings } from '../../api/settings'
import type { TrackRemuxPreview } from '../../api/nomenclature'
import type { LibraryItemResponse, SeasonPackPlanResponse, UploadJob } from '../../types/api'
import { UploadWizardModal } from '../UploadWizardModal'
import { boton, campo, tarjeta, desmontar, diferida, elegir, escribir, esperar, montar, pulsar, texto } from './dom'

const m = vi.mocked

/** El modal abierto encima de los demás (los de MediaInfo, pistas y nombres se abren sobre el asistente). */
const dialogoDeArriba = () => [...document.querySelectorAll<HTMLElement>('[role="dialog"]')].pop()!

/** Las pestañas del paso «Nombre y pistas» (Nomenclatura, Pistas, MediaInfo). */
const pestana = (nombre: string) =>
  [...document.querySelectorAll<HTMLElement>('[role="tab"]')].find(t => t.textContent?.startsWith(nombre))
const abrirPestana = async (nombre: string) => { await pulsar(await esperar(() => pestana(nombre))) }

function elemento(parcial: Partial<LibraryItemResponse>): LibraryItemResponse {
  return {
    id: 1, item_type: 'movie', title: 'Dune', display_title: null, year: 2021, original_title: null,
    instance_type: null, instance_name: null, instance_id: null, external_id: null, tmdb_id: null, imdb_id: null,
    tvdb_id: null, mal_id: null, title_slug: null, season_number: null, episode_number: null, parent_id: null,
    path: null, quality: null, resolution: '1080p', source: null, provider: null, provider_label: null,
    video_codec: 'x264', audio_codec: null, audio_languages: null, has_spanish_audio: 1, has_spanish_subs: 1,
    has_spanish_ok: 1, subtitle_languages: null, size_bytes: null, local_status: 'Disponible',
    request_status: '', nomenclature_status: '', updated_at: null,
    ...parcial,
  } as LibraryItemResponse
}

const PELICULA = elemento({ id: 10 })
const TEMPORADA = elemento({ id: 20, item_type: 'season', title: 'Serie - Temporada 1', season_number: 1 })
const SERIE = elemento({ id: 30, item_type: 'series', title: 'Serie' })
const T1 = elemento({ id: 31, item_type: 'season', title: 'Serie - Temporada 1', season_number: 1, parent_id: 30 })
const T2 = elemento({ id: 32, item_type: 'season', title: 'Serie - Temporada 2', season_number: 2, parent_id: 30 })
const E1 = elemento({ id: 21, item_type: 'episode', title: 'Serie S01E01 - Piloto', season_number: 1, episode_number: 1, parent_id: 20 })
const E2 = elemento({ id: 22, item_type: 'episode', title: 'Serie S01E02 - Segundo', season_number: 1, episode_number: 2, parent_id: 20 })

const CAMPOS = {
  title: 'Dune', year: '2021', resolution: '1080p', source: 'WEB-DL', provider: 'AMZN', video_codec: 'x264',
  audio_summary: 'Castellano DD 5.1', subs: 'SUBS', tag: 'GRP',
}

function respuestaCampos(extra: Partial<typeof CAMPOS> = {}) {
  return {
    fields: { ...CAMPOS, ...extra }, torrent_name: '', internal_mkv_title: '', blocked: false,
    title_options: [
      { value: 'Dune', kind: 'spanish', label: 'Español' },
      { value: 'Dune: Part One', kind: 'english', label: 'Original' },
    ],
  }
}

const PISTAS: TrackRemuxPreview = {
  status: 'preview', errors: [], warnings: [], track_mode: 'reorder_rename',
  ordered_tracks: [
    { id: 0, type: 'video', language: 'und', current_name: '', new_name: 'Vídeo', default_after: true },
    { id: 1, type: 'audio', language: 'spa', current_name: 'Spanish', new_name: 'Castellano DD 5.1', default_after: true },
    { id: 2, type: 'audio', language: 'und', current_name: '', new_name: 'DD 2.0', default_after: false, sin_idioma: true },
  ],
  tracks: [
    { id: 0, type: 'video', language: 'und' }, { id: 1, type: 'audio', language: 'spa' },
    { id: 2, type: 'audio', language: 'und' },
  ],
  idiomas_elegibles: [{ code: 'spa', label: 'Castellano' }, { code: 'eng', label: 'Inglés' }],
} as unknown as TrackRemuxPreview

const LISTO = { ready: true, checks: [{ id: 'renameable', label: 'Se puede renombrar', status: 'pass', message: '' }] }
const ENTORNO = { ready: true, checks: [{ id: 'emuwarez', label: 'eMuwarez responde', status: 'pass', message: '' }] }

function plan(extra: Partial<SeasonPackPlanResponse> = {}): SeasonPackPlanResponse {
  return {
    status: 'valid', errors: [], warnings: [], season_pack_title: 'Serie (2020) S01 1080p WEB-DL DD 5.1 x264-GRP',
    episodes: [{}, {}] as SeasonPackPlanResponse['episodes'],
    series_title: 'Serie', year: 2020, season_number: 1, resolution: '1080p', source: 'WEB-DL', provider: 'AMZN',
    video_codec: 'x264', audio_summary: 'DD 5.1', subtitle_summary: 'SUBS', release_tag: 'GRP',
    pistas_sin_idioma: [{ posicion: 1, pista: 'DD 5.1', capitulos: [1, 2] }],
    idiomas_elegibles: [{ code: 'spa', label: 'Castellano' }, { code: 'eng', label: 'Inglés' }],
    idiomas_audio: {},
    ...extra,
  }
}

// Todas las subidas de una tanda llevan el mismo lote (12 hex) como 7.º argumento de queueUpload.
function mismoLote() {
  const lotes = m(subidas.queueUpload).mock.calls.map(c => c[6])
  expect(lotes.length).toBeGreaterThan(0)
  expect(lotes[0]).toMatch(/^[0-9a-f]{12}$/)
  expect(new Set(lotes).size).toBe(1)
}

const onClose = vi.fn()
const onDone = vi.fn()
const onNavigate = vi.fn()

function abrir(item: LibraryItemResponse, extra: Partial<Parameters<typeof UploadWizardModal>[0]> = {}) {
  return montar(<UploadWizardModal item={item} onClose={onClose} onDone={onDone} onNavigate={onNavigate} {...extra} />)
}

beforeEach(() => {
  vi.clearAllMocks()
  m(fetchSettings).mockResolvedValue({ upload_tags: ['GRP', 'OTRO'] } as Awaited<ReturnType<typeof fetchSettings>>)
  m(nom.getEmuSources).mockResolvedValue({ sources: [{ code: 'WEB-DL', label: 'WEB-DL' }, { code: 'BluRay', label: 'BluRay' }] } as never)
  m(nom.getEmuProviders).mockResolvedValue({ providers: [{ code: 'AMZN', name: 'Amazon' }, { code: 'NF', name: 'Netflix' }] } as never)
  m(nom.getNomenclatureFields).mockResolvedValue(respuestaCampos() as never)
  m(nom.previewNomenclatureFields).mockImplementation(async (_id, f) => ({
    torrent_name: `${f.title} ${f.source}${f.provider ? ` ${f.provider}` : ''} [${f.tag}]`,
    internal_mkv_title: `${f.title}.mkv`,
  }) as never)
  m(nom.saveNomenclatureFields).mockResolvedValue({} as never)
  m(nom.previewTrackRemux).mockResolvedValue(PISTAS)
  // El Resumen: catálogo sin nada, sin petición en la ficha.
  m(biblioteca.getEmuComparison).mockResolvedValue({ available: true, message: null, matches: [], in_catalog: 0 })
  m(biblioteca.getEmuSyncStatus).mockResolvedValue({ last_sync_at: null } as never)
  m(biblioteca.getLibraryItem).mockResolvedValue(elemento({ peticion: null }))
  m(subidas.getExistingJobForItem).mockResolvedValue(null)
  m(subidas.runUploadChecks).mockImplementation(async (_id, alcance) => (alcance === 'environment' ? ENTORNO : LISTO) as never)
  m(subidas.getUploadChecksProgress).mockResolvedValue({ checks: [] } as never)
  m(subidas.queueUpload).mockResolvedValue({ status: 'queued', job: { id: 99 } } as never)
  m(temporada.previewSeasonPack).mockResolvedValue(plan())
  m(temporada.getSeasonPlanProgress).mockResolvedValue({ done: 0, total: 0, current_title: null })
  m(temporada.previewSeasonPackFields).mockImplementation(async (_id, f) => ({
    torrent_name: `${f.title} S01 ${f.source} ${f.audio_summary} [${f.tag}]`,
  }) as never)
  m(temporada.cancelSeasonPackPreview).mockResolvedValue(undefined as never)
})

afterEach(desmontar)

describe('película', () => {
  it('carga la nomenclatura, comprueba y encola con lo elegido', async () => {
    await abrir(PELICULA)
    await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
    expect(nom.getNomenclatureFields).toHaveBeenCalledWith(10)
    expect(nom.previewTrackRemux).toHaveBeenCalledWith(10)
    expect(texto()).toContain('Dune.mkv')

    await elegir(campo('Tag'), 'OTRO')
    await esperar(() => texto().includes('Dune WEB-DL AMZN [OTRO]'))

    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ Todo listo para subir'))
    expect(nom.saveNomenclatureFields).toHaveBeenCalledWith(10, expect.objectContaining({ tag: 'OTRO' }))
    expect(subidas.runUploadChecks).toHaveBeenCalledWith(10, undefined, undefined)
    expect(texto()).toContain('¿Seguro que quieres subir «Dune» a eMuwarez?')

    await pulsar(boton('Subir a eMuwarez'))
    await esperar(() => onClose.mock.calls.length > 0)
    expect(subidas.queueUpload).toHaveBeenCalledWith(
      10, {}, LISTO, { ordered_tracks: PISTAS.ordered_tracks }, undefined, undefined)
    expect(onDone).toHaveBeenCalled()
    expect(onNavigate).toHaveBeenCalledWith('uploads')
  })

  it('un source que no es WEB-DL quita el proveedor', async () => {
    await abrir(PELICULA)
    await esperar(() => campo('Proveedor'))
    await elegir(campo('Source'), 'BluRay')
    await esperar(() => texto().includes('Dune BluRay [GRP]'))
    expect(campo('Proveedor')).toBeUndefined()
  })

  it('WEB-DL sin proveedor lo pide a TMDb una vez', async () => {
    m(nom.getNomenclatureFields).mockResolvedValue(respuestaCampos({ provider: undefined }) as never)
    m(biblioteca.suggestProvider).mockResolvedValue({ suggested: 'NF' } as never)
    await abrir(PELICULA)
    await esperar(() => texto().includes('Dune WEB-DL NF [GRP]'))
    expect(biblioteca.suggestProvider).toHaveBeenCalledTimes(1)
    expect(campo('Proveedor')!.value).toBe('NF')
  })

  it('las ediciones de «Ver Pistas» viajan a la cola', async () => {
    await abrir(PELICULA)
    await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
    await abrirPestana('Pistas')
    await esperar(() => document.querySelector('table input.form-input'))
    const nombres = [...document.querySelectorAll<HTMLInputElement>('table input.form-input')]
    await escribir(nombres[1], 'Castellano')

    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ Todo listo para subir'))
    await pulsar(boton('Subir a eMuwarez'))
    await esperar(() => m(subidas.queueUpload).mock.calls.length > 0)
    const [, ediciones, , foto] = m(subidas.queueUpload).mock.calls[0]
    expect(ediciones).toEqual({ 1: { new_name: 'Castellano' } })
    expect((foto!.ordered_tracks[1] as { new_name: string }).new_name).toBe('Castellano')
  })

  it('el idioma de una pista sin idioma recalcula el audio y Continuar espera', async () => {
    const recalculo = diferida<unknown>()
    m(nom.getNomenclatureFields).mockImplementation(async (_id, idiomas) =>
      (idiomas ? recalculo.promesa : respuestaCampos()) as never)
    m(nom.applyTrackRemux).mockResolvedValue(PISTAS as never)
    await abrir(PELICULA)
    await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
    await abrirPestana('Pistas')
    const selector = await esperar(() => document.querySelector<HTMLSelectElement>('table select'))
    await elegir(selector, 'eng')
    expect(nom.getNomenclatureFields).toHaveBeenLastCalledWith(10, { 2: 'eng' })
    expect(nom.applyTrackRemux).toHaveBeenCalledWith(10, { dryRun: true, overrides: { 2: { language: 'eng' } } })
    await abrirPestana('Nomenclatura')
    expect(boton('Continuar')!.disabled).toBe(true)

    recalculo.resolver(respuestaCampos({ audio_summary: 'Castellano DD 5.1 / Inglés DD 2.0' }))
    await esperar(() => campo<HTMLInputElement>('Audio')!.value === 'Castellano DD 5.1 / Inglés DD 2.0')
    await esperar(() => !boton('Continuar')!.disabled)
  })

  it('una subida en curso del mismo contenido bloquea Continuar', async () => {
    m(subidas.getExistingJobForItem).mockResolvedValue({ id: 5, status: 'running' } as UploadJob)
    await abrir(PELICULA)
    await esperar(() => texto().includes('Ya hay una subida en curso para este contenido'))
    await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
    expect(boton('Continuar')!.disabled).toBe(true)
  })
})

describe('cerrar', () => {
  it('sin tocar nada cierra a la primera', async () => {
    await abrir(PELICULA)
    await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
    await pulsar(document.querySelector('[aria-label="Cerrar"]') ?? undefined)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('con algo cambiado pregunta antes de descartar', async () => {
    await abrir(PELICULA)
    await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
    await elegir(campo('Tag'), 'OTRO')
    await pulsar(document.querySelector('[aria-label="Cerrar"]') ?? undefined)
    expect(onClose).not.toHaveBeenCalled()
    expect(texto()).toContain('¿Descartar los cambios?')
    await pulsar(boton('Cerrar y descartar'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('cerrar mientras se prepara el pack se lo dice al servidor', async () => {
    m(biblioteca.getLibrary).mockResolvedValue({ items: [E1, E2], total: 2 } as never)
    m(temporada.previewSeasonPack).mockReturnValue(new Promise(() => {}))
    await abrir(TEMPORADA)
    await pulsar(await esperar(() => tarjeta('Temporada entera')))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('Generando Nomenclatura para eMuwarez…'))
    await pulsar(document.querySelector('[aria-label="Cerrar"]') ?? undefined)
    expect(temporada.cancelSeasonPackPreview).toHaveBeenCalledWith(20)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('pack de temporada', () => {
  beforeEach(() => {
    m(biblioteca.getLibrary).mockResolvedValue({ items: [E1, E2], total: 2 } as never)
  })

  it('elige el modo, prepara el pack y encola con el idioma confirmado', async () => {
    m(temporada.getSeasonPackAudio).mockResolvedValue({
      audio_summary: 'Castellano DD 5.1', custom: false, audio_warning: null, pistas_sin_idioma: [],
      idiomas_audio: { 1: 'spa' },
    } as never)
    await abrir(TEMPORADA)
    await esperar(() => tarjeta('Temporada entera'))
    expect(boton('Continuar')!.disabled).toBe(true)
    await pulsar(tarjeta('Temporada entera'))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('Serie S01 WEB-DL DD 5.1 [GRP]'))
    expect(temporada.previewSeasonPack).toHaveBeenCalledWith(20, undefined, undefined)
    expect(texto()).toContain('✓ 2 capítulo(s) listos, coherentes entre sí')

    await elegir(campo('Pista de audio 1'), 'spa')
    expect(temporada.getSeasonPackAudio).toHaveBeenCalledWith(20, { 1: 'spa' })
    await esperar(() => texto().includes('Serie S01 WEB-DL Castellano DD 5.1 [GRP]'))

    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ Todo listo para subir'))
    expect(nom.saveNomenclatureFields).not.toHaveBeenCalled()
    expect(subidas.runUploadChecks).toHaveBeenCalledWith(20, undefined, undefined)
    expect(texto()).toContain('2 capítulos en una carpeta')

    await pulsar(boton('Subir a eMuwarez'))
    await esperar(() => onClose.mock.calls.length > 0)
    expect(subidas.queueUpload).toHaveBeenCalledWith(
      20, {}, LISTO, null,
      { source: 'WEB-DL', tag: 'GRP', title: 'Serie', provider: undefined, idiomas: { 1: 'spa' } },
      undefined)
  })

  it('«Ver nombre de todos los capítulos» pide los nombres con lo elegido', async () => {
    m(temporada.getSeasonEpisodeNames).mockResolvedValue({ episodes: [
      { episode_id: 21, display_title: 'E01', torrent_name: 'Serie S01E01 [GRP]', internal_mkv_title: 'Serie.S01E01' },
      { episode_id: 22, display_title: 'E02', torrent_name: 'Serie S01E02 [GRP]', internal_mkv_title: 'Serie.S01E02' },
    ] } as never)
    await abrir(TEMPORADA, { preselect: { season: 1 } })
    await pulsar(await esperar(() => boton('Continuar')))
    await esperar(() => boton('Ver nombre de todos los capítulos'))
    await elegir(campo('Tag'), 'OTRO')
    await pulsar(boton('Ver nombre de todos los capítulos'))
    await esperar(() => texto().includes('Serie S01E01 [GRP]'))
    expect(temporada.getSeasonEpisodeNames).toHaveBeenCalledWith(
      20, { source: 'WEB-DL', provider: 'AMZN', tag: 'OTRO', idiomas: undefined })
    await elegir(dialogoDeArriba().querySelector('select') ?? undefined, '22')
    await esperar(() => texto().includes('Serie S01E02 [GRP]'))
  })

  describe('abiertos mientras se recalcula el idioma del pack', () => {
    // Se puede abrir «Ver nombre…» o «Ver Pistas» con el recálculo en vuelo: lo que piden entonces lleva el
    // idioma de antes y se descarta al confirmarse el nuevo. Tienen que volver a pedirse solos, no quedarse vacíos.
    async function cambiarIdiomaYAbrir(abrirDetalle: () => Promise<void>) {
      const audio = diferida<unknown>()
      m(temporada.getSeasonPackAudio).mockReturnValue(audio.promesa as never)
      await abrir(TEMPORADA, { preselect: { season: 1 } })
      await pulsar(await esperar(() => boton('Continuar')))
      await esperar(() => boton('Ver nombre de todos los capítulos'))
      await elegir(campo('Pista de audio 1'), 'spa')
      await abrirDetalle()
      await esperar(() => texto().includes('del capítulo viejo'))
      audio.resolver({
        audio_summary: 'Castellano DD 5.1', custom: false, audio_warning: null, pistas_sin_idioma: [],
        idiomas_audio: { 1: 'spa' },
      })
    }

    it('«Ver nombre de todos los capítulos» se recarga con el idioma confirmado', async () => {
      m(temporada.getSeasonEpisodeNames).mockImplementation(async (_id, ov) => ({ episodes: [{
        episode_id: 21, display_title: 'E01', internal_mkv_title: 'Serie.S01E01',
        torrent_name: ov?.idiomas ? 'Serie S01E01 Castellano del capítulo nuevo' : 'Serie S01E01 del capítulo viejo',
      }] }) as never)
      await cambiarIdiomaYAbrir(async () => { await pulsar(boton('Ver nombre de todos los capítulos')) })
      await esperar(() => texto().includes('Serie S01E01 Castellano del capítulo nuevo'))
      expect(temporada.getSeasonEpisodeNames).toHaveBeenLastCalledWith(
        20, { source: 'WEB-DL', provider: 'AMZN', tag: 'GRP', idiomas: { 1: 'spa' } })
    })

    it('«Ver Pistas» se recarga con el idioma confirmado', async () => {
      m(temporada.getSeasonEpisodeRemuxPreview).mockImplementation(async (_id, idiomas) => ({ episodes: [{
        episode_id: 21, display_title: 'E01',
        plan: { status: 'preview', errors: [], warnings: [], ordered_tracks: [{
          id: 1, type: 'audio', language: 'spa', current_name: '', default_after: true,
          new_name: idiomas ? 'Castellano del capítulo nuevo' : 'Pista del capítulo viejo',
        }] },
      }] }) as never)
      await cambiarIdiomaYAbrir(() => abrirPestana('Pistas'))
      await esperar(() => texto().includes('Castellano del capítulo nuevo'))
      expect(temporada.getSeasonEpisodeRemuxPreview).toHaveBeenLastCalledWith(20, { 1: 'spa' })
    })
  })

  it('un plan bloqueado por proveedores distintos deja elegir uno y lo vuelve a pedir', async () => {
    m(temporada.previewSeasonPack)
      .mockResolvedValueOnce(plan({ status: 'blocked', errors: ['Proveedores distintos.'], provider_conflict: ['AMZN', 'NF'] }))
      .mockResolvedValueOnce(plan({ provider: 'NF' }))
    await abrir(TEMPORADA, { preselect: { season: 1 } })
    await pulsar(await esperar(() => boton('Continuar')))
    await esperar(() => texto().includes('Proveedores distintos.'))
    await elegir(campo('Proveedor'), 'NF')
    await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
    expect(temporada.previewSeasonPack).toHaveBeenLastCalledWith(20, 'NF', undefined)
  })
})

describe('varios capítulos de una temporada', () => {
  beforeEach(() => {
    m(biblioteca.getLibrary).mockResolvedValue({ items: [E1, E2], total: 2 } as never)
    m(nom.getNomenclatureFields).mockImplementation(async id => respuestaCampos({ title: 'Serie', tag: `G${id}` }) as never)
  })

  it('genera la nomenclatura de todos, comprueba el entorno una vez y los sube uno a uno', async () => {
    await abrir(TEMPORADA)
    await pulsar(await esperar(() => tarjeta('Selección de capítulos')))
    await pulsar(boton('Continuar'))
    expect(texto()).toContain('Selecciona al menos un capítulo')
    await pulsar(boton('E01'))
    await pulsar(boton('E02'))
    expect(texto()).toContain('2 seleccionado(s)')
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('Serie WEB-DL AMZN [G21]'))
    expect(nom.getNomenclatureFields).toHaveBeenCalledWith(21)
    expect(nom.getNomenclatureFields).toHaveBeenCalledWith(22)

    await elegir(document.querySelector<HTMLSelectElement>('.modal-body > div > select') ?? undefined, '22')
    await esperar(() => texto().includes('Serie WEB-DL AMZN [G22]'))

    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ Todo listo: 2 capítulos'))
    expect(m(subidas.runUploadChecks).mock.calls).toEqual([
      [21, 'environment'], [21, 'content', undefined], [22, 'content', undefined],
    ])

    await pulsar(boton('Subir todos'))
    await esperar(() => texto().includes('2 de 2 capítulo(s) encolado(s)'))
    expect(nom.saveNomenclatureFields).toHaveBeenCalledWith(21, expect.objectContaining({ title: 'Serie', tag: 'G21' }))
    expect(nom.saveNomenclatureFields).toHaveBeenCalledWith(22, expect.objectContaining({ title: 'Serie', tag: 'G22' }))
    expect(m(subidas.queueUpload).mock.calls.map(c => c[0])).toEqual([21, 22])
    expect(m(subidas.queueUpload).mock.calls[0][2]).toEqual({ ready: true, checks: [...LISTO.checks, ...ENTORNO.checks] })
    mismoLote()

    await pulsar(boton('Ir a Subidas'))
    expect(onNavigate).toHaveBeenCalledWith('uploads')
    expect(onClose).toHaveBeenCalled()
  })
})

describe('varias temporadas de una serie', () => {
  beforeEach(() => {
    m(biblioteca.getLibrary).mockResolvedValue({ items: [T1, T2], total: 2 } as never)
  })

  it('marca las temporadas, recorre sus packs y sube todas saltando la que falla', async () => {
    m(subidas.runUploadChecks).mockImplementation(async (id, alcance) => {
      if (alcance === 'environment') return ENTORNO as never
      return (id === 32
        ? { ready: false, checks: [{ id: 'season_pack', label: 'Pack', status: 'fail', message: 'Falta un capítulo' }] }
        : LISTO) as never
    })
    await abrir(SERIE, { preselect: { season: 1 } })
    await esperar(() => boton('Temporada 1'))
    expect(texto()).toContain('Elige qué temporada(s) de Serie subir.')
    await pulsar(boton('Temporada 2'))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
    expect(temporada.previewSeasonPack).toHaveBeenCalledWith(31, undefined, undefined)

    await elegir(document.querySelector<HTMLSelectElement>('.modal-body > div > select') ?? undefined, '32')
    await esperar(() => m(temporada.previewSeasonPack).mock.calls.some(c => c[0] === 32))
    await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))

    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✗ 1 de 2 no se puede subir'))
    expect(texto()).toContain('Falta un capítulo')
    expect(texto()).toContain('Se saltarán. El resto se subirá igualmente.')

    await pulsar(boton('Subir todas'))
    await esperar(() => texto().includes('1 de 2 temporada(s) encolada(s)'))
    expect(m(subidas.queueUpload).mock.calls.map(c => c[0])).toEqual([31])
    expect(m(subidas.queueUpload).mock.calls[0][4]).toEqual({ source: 'WEB-DL', provider: undefined, tag: 'GRP', title: 'Serie' })
    expect(m(subidas.queueUpload).mock.calls[0][5]).toBeUndefined()
    mismoLote()
  })

  it('cambiar el Proveedor en el paso 1 vuelve a comprobar el contenido de esa temporada', async () => {
    await abrir(SERIE, { preselect: { season: 1 } })
    await pulsar(await esperar(() => boton('Temporada 2')))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ Todo listo: 2 temporadas'))
    await pulsar(boton('← Volver'))
    await elegir(await esperar(() => campo<HTMLSelectElement>('Proveedor')), 'NF')
    await pulsar(boton('Continuar'))
    await esperar(() => m(subidas.runUploadChecks).mock.calls.some(c => c[0] === 31 && c[2] === 'NF'))
    await esperar(() => texto().includes('✓ Todo listo: 2 temporadas'))
    // Un pack se comprueba con lo editado (Source, Tag y el Título de la serie, común a todas) para que su nombre sea el real.
    const pack = { source: 'WEB-DL', tag: 'GRP', title: 'Serie' }
    expect(m(subidas.runUploadChecks).mock.calls).toEqual([
      [31, 'environment'], [31, 'content', undefined, pack], [32, 'content', undefined, { title: 'Serie' }], [31, 'content', 'NF', pack],
    ])
  })

  it('si falla la comprobación con el Proveedor nuevo, no se sube con la del anterior', async () => {
    m(subidas.runUploadChecks).mockImplementation(async (id, alcance, proveedor) => {
      if (alcance === 'environment') return ENTORNO as never
      if (id === 31 && proveedor === 'NF') throw new Error('Sin conexión')
      return LISTO as never
    })
    await abrir(SERIE, { preselect: { season: 1 } })
    await pulsar(await esperar(() => boton('Temporada 2')))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ Todo listo: 2 temporadas'))
    await pulsar(boton('← Volver'))
    await elegir(await esperar(() => campo<HTMLSelectElement>('Proveedor')), 'NF')
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('Sin conexión'))
    expect(boton('Subir todas')!.disabled).toBe(true)
  })

  it('una pasada abandonada que responde tarde no pisa la nueva', async () => {
    const vieja = diferida<unknown>()
    let veces = 0
    m(subidas.runUploadChecks).mockImplementation(async (id, alcance) => {
      if (alcance === 'environment') return ENTORNO as never
      if (id === 32 && veces++ === 0) return vieja.promesa as never
      return LISTO as never
    })
    await abrir(SERIE, { preselect: { season: 1 } })
    await pulsar(await esperar(() => boton('Temporada 2')))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
    await pulsar(boton('Continuar'))
    await esperar(() => veces === 1)
    await pulsar(boton('← Volver'))
    await pulsar(await esperar(() => boton('Continuar')))
    await esperar(() => texto().includes('✓ Todo listo: 2 temporadas'))
    await act(async () => {
      vieja.resolver({ ready: false, checks: [{ id: 'season_pack', label: 'Pack', status: 'fail', message: 'Respuesta vieja' }] })
    })
    expect(texto()).toContain('✓ Todo listo: 2 temporadas')
    expect(texto()).not.toContain('Respuesta vieja')
  })

  it('sin marcar ninguna no avanza', async () => {
    await abrir(SERIE)
    await esperar(() => boton('Temporada 1'))
    await pulsar(boton('Continuar'))
    expect(texto()).toContain('Selecciona al menos una temporada')
  })
})

// Lo que pasa cuando eMuwarez o la red fallan, o una respuesta llega tarde (#139).
describe('fallos de red y respuestas tardías', () => {
  const FALLO = { ready: false, checks: [{ id: 'emuwarez', label: 'eMuwarez responde', status: 'fail', message: 'eMuwarez no responde' }] }

  describe('una película', () => {
    // Dos pasadas de comprobaciones: la primera sigue en vuelo cuando se vuelve al paso 1 y se pide la segunda.
    async function dosPasadas() {
      const vieja = diferida<unknown>()
      const nueva = diferida<unknown>()
      m(subidas.runUploadChecks).mockReturnValueOnce(vieja.promesa as never).mockReturnValueOnce(nueva.promesa as never)
      await abrir(PELICULA)
      await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
      await pulsar(boton('Continuar'))
      await pulsar(await esperar(() => boton('← Volver')))
      await pulsar(await esperar(() => boton('Continuar')))
      await esperar(() => m(subidas.runUploadChecks).mock.calls.length === 2)
      return { vieja, nueva }
    }

    it('la pasada vieja que acaba antes no termina la nueva', async () => {
      const { vieja, nueva } = await dosPasadas()
      await act(async () => { vieja.resolver(LISTO) })
      expect(texto()).not.toContain('Todo listo')
      expect(boton('Subir a eMuwarez')!.disabled).toBe(true)
      nueva.resolver(FALLO)
      await esperar(() => texto().includes('✗ La subida no se puede realizar'))
    })

    it('la pasada vieja que acaba después no habilita la subida', async () => {
      const { vieja, nueva } = await dosPasadas()
      nueva.resolver(FALLO)
      await esperar(() => texto().includes('✗ La subida no se puede realizar'))
      await act(async () => { vieja.resolver(LISTO) })
      expect(texto()).not.toContain('Todo listo')
      expect(texto()).toContain('✗ La subida no se puede realizar')
      expect(boton('Subir a eMuwarez')!.disabled).toBe(true)
    })
  })

  describe('si la petición de comprobaciones no llega', () => {
    it('una película enseña el error y «Volver a comprobar» lo repite', async () => {
      m(subidas.runUploadChecks).mockRejectedValueOnce(new Error('Sin conexión'))
      await abrir(PELICULA)
      await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✗ No se pudieron completar las comprobaciones: Sin conexión'))
      expect(texto()).not.toContain('Todo listo')
      expect(boton('Subir a eMuwarez')!.disabled).toBe(true)
      await pulsar(await esperar(() => boton('↻ Volver a comprobar')))
      await esperar(() => texto().includes('✓ Todo listo para subir'))
      expect(texto()).not.toContain('No se pudieron completar')
      expect(boton('Subir a eMuwarez')!.disabled).toBe(false)
    })

    it('un pack de temporada también', async () => {
      m(biblioteca.getLibrary).mockResolvedValue({ items: [E1, E2], total: 2 } as never)
      m(subidas.runUploadChecks).mockRejectedValueOnce(new Error('Sin conexión'))
      await abrir(TEMPORADA)
      await pulsar(await esperar(() => tarjeta('Temporada entera')))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('Serie S01 WEB-DL DD 5.1 [GRP]'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✗ No se pudieron completar las comprobaciones: Sin conexión'))
      expect(boton('Subir a eMuwarez')!.disabled).toBe(true)
      await pulsar(await esperar(() => boton('↻ Volver a comprobar')))
      await esperar(() => texto().includes('✓ Todo listo para subir'))
    })
  })

  describe('varios capítulos', () => {
    beforeEach(() => {
      m(biblioteca.getLibrary).mockResolvedValue({ items: [E1, E2], total: 2 } as never)
      m(nom.getNomenclatureFields).mockImplementation(async id => respuestaCampos({ title: 'Serie', tag: `G${id}` }) as never)
    })

    const selectorCapitulo = () => document.querySelector<HTMLSelectElement>('.modal-body > div > select') ?? undefined

    async function elegirDosCapitulos() {
      await abrir(TEMPORADA)
      await pulsar(await esperar(() => tarjeta('Selección de capítulos')))
      await pulsar(boton('E01'))
      await pulsar(boton('E02'))
      await pulsar(boton('Continuar'))
    }

    it('si no llegan los sources, la precarga avisa y «Reintentar» la repite entera', async () => {
      m(nom.getEmuSources).mockRejectedValueOnce(new Error('Sin conexión'))
      await elegirDosCapitulos()
      await esperar(() => texto().includes('Sin conexión') && boton('↻ Reintentar'))
      await pulsar(boton('↻ Reintentar'))
      await esperar(() => texto().includes('Serie WEB-DL AMZN [G21]'))
      expect(nom.getNomenclatureFields).toHaveBeenCalledWith(22)
      await elegir(selectorCapitulo(), '22')
      await esperar(() => texto().includes('Serie WEB-DL AMZN [G22]'))
    })

    it('si falla un capítulo, «Reintentar» lo vuelve a generar y no queda el fallo guardado', async () => {
      m(nom.getNomenclatureFields).mockRejectedValueOnce(new Error('Sin conexión'))
      await elegirDosCapitulos()
      await pulsar(await esperar(() => texto().includes('Sin conexión') && boton('↻ Reintentar')))
      await esperar(() => texto().includes('Serie WEB-DL AMZN [G21]'))
      await elegir(selectorCapitulo(), '22')
      await esperar(() => texto().includes('Serie WEB-DL AMZN [G22]'))
      await elegir(selectorCapitulo(), '21')
      await esperar(() => texto().includes('Serie WEB-DL AMZN [G21]'))
      expect(texto()).not.toContain('Sin conexión')
      // El que salió bien no se vuelve a pedir: un fallo nuevo lo dejaría bloqueado.
      expect(m(nom.getNomenclatureFields).mock.calls.filter(c => c[0] === 22)).toHaveLength(1)
    })

    it('un capítulo sin nomenclatura se salta aunque sus comprobaciones pasen', async () => {
      m(nom.getNomenclatureFields).mockImplementation(async id => (id === 22
        ? { fields: {}, torrent_name: '', internal_mkv_title: '', blocked: true, error: 'Sin audio detectado' }
        : respuestaCampos({ title: 'Serie', tag: `G${id}` })) as never)
      await elegirDosCapitulos()
      await esperar(() => texto().includes('Serie WEB-DL AMZN [G21]'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ Todo listo: 2 capítulos'))
      await pulsar(boton('Subir todos'))
      await esperar(() => texto().includes('1 de 2 capítulo(s) encolado(s)'))
      expect(texto()).toContain('Sin audio detectado')
      expect(m(subidas.queueUpload).mock.calls.map(c => c[0])).toEqual([21])
      expect(m(nom.saveNomenclatureFields).mock.calls.map(c => c[0])).not.toContain(22)
      mismoLote()
    })

    // El entorno falla la primera vez y responde bien después.
    function entornoQueFallaUnaVez(fallo: () => Promise<unknown>) {
      let veces = 0
      m(subidas.runUploadChecks).mockImplementation(async (_id, alcance) => {
        if (alcance !== 'environment') return LISTO as never
        return (veces++ === 0 ? fallo() : ENTORNO) as never
      })
    }

    it('un entorno fallido se puede volver a comprobar sin repetir el contenido', async () => {
      entornoQueFallaUnaVez(async () => FALLO)
      await elegirDosCapitulos()
      await esperar(() => texto().includes('Serie WEB-DL AMZN [G21]'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✗ La subida no se puede realizar'))
      expect(boton('Subir todos')!.disabled).toBe(true)
      await pulsar(await esperar(() => boton('↻ Volver a comprobar')))
      await esperar(() => texto().includes('✓ Todo listo: 2 capítulos'))
      expect(m(subidas.runUploadChecks).mock.calls).toEqual([
        [21, 'environment'], [21, 'content', undefined], [22, 'content', undefined], [21, 'environment'],
      ])
    })

    it('volver al paso 1 y entrar otra vez repite el entorno fallido y conserva lo editado', async () => {
      entornoQueFallaUnaVez(async () => FALLO)
      await elegirDosCapitulos()
      await esperar(() => texto().includes('Serie WEB-DL AMZN [G21]'))
      await elegir(campo('Tag'), 'OTRO')
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✗ La subida no se puede realizar'))
      await pulsar(boton('← Volver'))
      await pulsar(await esperar(() => boton('Continuar')))
      await esperar(() => texto().includes('✓ Todo listo: 2 capítulos'))
      await pulsar(boton('Subir todos'))
      await esperar(() => texto().includes('2 de 2 capítulo(s) encolado(s)'))
      expect(nom.saveNomenclatureFields).toHaveBeenCalledWith(21, expect.objectContaining({ tag: 'OTRO' }))
    })

    it('si la petición del entorno no llega, no dice «Todo listo» y deja reintentar', async () => {
      entornoQueFallaUnaVez(() => Promise.reject(new Error('Sin conexión')))
      await elegirDosCapitulos()
      await esperar(() => texto().includes('Serie WEB-DL AMZN [G21]'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('Sin conexión'))
      expect(texto()).not.toContain('Todo listo')
      expect(boton('Subir todos')!.disabled).toBe(true)
      await pulsar(await esperar(() => boton('↻ Volver a comprobar')))
      await esperar(() => texto().includes('✓ Todo listo: 2 capítulos'))
    })

    it('si la de un capítulo no llega, no dice «Todo listo» y al reintentar solo pide la que falta', async () => {
      let veces = 0
      m(subidas.runUploadChecks).mockImplementation(async (id, alcance) => {
        if (alcance === 'environment') return ENTORNO as never
        if (id === 22 && veces++ === 0) throw new Error('Sin conexión')
        return LISTO as never
      })
      await elegirDosCapitulos()
      await esperar(() => texto().includes('Serie WEB-DL AMZN [G21]'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('Sin conexión'))
      expect(texto()).not.toContain('Todo listo')
      expect(boton('Subir todos')!.disabled).toBe(true)
      await pulsar(await esperar(() => boton('↻ Volver a comprobar')))
      await esperar(() => texto().includes('✓ Todo listo: 2 capítulos'))
      expect(m(subidas.runUploadChecks).mock.calls).toEqual([
        [21, 'environment'], [21, 'content', undefined], [22, 'content', undefined], [22, 'content', undefined],
      ])
    })
  })
})

describe('los pasos y el Resumen', () => {
  const pasos = () => [...document.querySelectorAll<HTMLElement>('.asist-pasos li')]
  const textos = () => pasos().map(p => p.textContent?.replace(/\s+/g, ' ').trim())
  const actual = () => document.querySelector<HTMLElement>('.asist-pasos [aria-current="step"]')
  /** Lo que dice el Resumen de un dato («Pistas», «Copia»…): el texto de su <dd>. */
  const dato = (nombre: string) => {
    const dt = [...document.querySelectorAll('.asist-datos dt')].find(d => d.textContent === nombre)
    return dt?.nextElementSibling?.textContent ?? ''
  }

  async function alResumenDePelicula(extra: Parameters<typeof abrir>[1] = {}) {
    await abrir(PELICULA, extra)
    await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ Todo listo para subir'))
  }

  describe('el indicador de pasos', () => {
    it('una película tiene dos pasos y no hay «Contenido»', async () => {
      await abrir(PELICULA)
      await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
      expect(textos()).toEqual(['1 · Nombre y pistas', '2 · Resumen'])
      expect(actual()?.textContent).toContain('Nombre y pistas')
      expect(document.querySelector('nav.asist-pasos')?.getAttribute('aria-label')).toBe('Pasos de la subida')
    })

    it('al pasar al Resumen el primero queda hecho, el Resumen es el actual y recibe el foco', async () => {
      await alResumenDePelicula()
      expect(textos()).toEqual(['✓ 1 · Nombre y pistas (hecho)', '2 · Resumen'])
      expect(actual()?.textContent).toContain('Resumen')
      expect(document.activeElement).toBe(actual())
    })

    it('una serie añade «Contenido» al principio y lo marca hecho en cuanto se elige', async () => {
      m(biblioteca.getLibrary).mockResolvedValue({ items: [T1, T2], total: 2 } as never)
      await abrir(SERIE, { preselect: { season: 1 } })
      await esperar(() => boton('Temporada 1'))
      expect(textos()).toEqual(['1 · Contenido', '2 · Nombre y pistas', '3 · Resumen'])
      expect(actual()?.textContent).toContain('Contenido')
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
      expect(textos()).toEqual(['✓ 1 · Contenido (hecho)', '2 · Nombre y pistas', '3 · Resumen'])
      expect(actual()?.textContent).toContain('Nombre y pistas')
    })
  })

  describe('una película', () => {
    it('enseña lo que se sube tal como lo recibirá eMuwarez', async () => {
      await alResumenDePelicula()
      expect(document.querySelector('.asist-nombre-torrent')?.textContent).toBe('Dune WEB-DL AMZN [GRP]')
      expect(dato('Ficheros')).toBe('1 fichero')
      expect(dato('Categoría')).toBe('Película · WEB-DL · 1080p')
      expect(dato('Petición')).toBe('Ninguna abierta para esta película')
      expect(dato('Copia')).toContain('Se decide al preparar los ficheros')
      // Con el nombre y la calidad de lo que se sube, no con lo que dijo Radarr.
      expect(biblioteca.getEmuComparison).toHaveBeenCalledWith(10, { resolution: '1080p', source: 'WEB-DL' })
      expect(boton('← Volver')).toBeDefined()
      expect(boton('Subir a eMuwarez')!.disabled).toBe(false)
    })

    it('usa el tamaño de la copia y el tipo de enlace que dijo la comprobación', async () => {
      m(subidas.runUploadChecks).mockResolvedValue({
        ready: true, checks: [{ id: 'carpeta_subida', label: 'Se puede preparar la carpeta de subida', status: 'ok', message: '/data/uploads (enlace duro)' }],
      } as never)
      await abrir(elemento({ id: 10, size_bytes: 4_500_000_000 }))
      await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
      await pulsar(boton('Continuar'))
      await esperar(() => dato('Copia').includes('Enlace duro'))
      expect(dato('Ficheros')).toBe('1 fichero · 4,2 GB')
      expect(dato('Copia')).toContain('sin espacio extra')
    })

    it('las pistas dicen el modo y lo que se editó a mano', async () => {
      m(nom.previewTrackRemux).mockResolvedValue({
        ...PISTAS, track_mode: 'reordenar_y_renombrar',
        ordered_tracks: PISTAS.ordered_tracks!.map(t => (t.id === 1 ? { ...t, changed: true } : { ...t, changed: false })),
      } as never)
      await abrir(PELICULA)
      await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
      await abrirPestana('Pistas')
      await esperar(() => document.querySelector('table input.form-input'))
      await escribir([...document.querySelectorAll<HTMLInputElement>('table input.form-input')][2], 'Inglés')
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ Todo listo para subir'))
      expect(dato('Pistas')).toBe('Reordenar y renombrar · 2 pistas cambian · 1 editada a mano')
      expect(dato('Copia')).toContain('copia reflink')
    })

    it('con el modo «Ninguno» el original no se toca', async () => {
      m(nom.previewTrackRemux).mockResolvedValue({ ...PISTAS, track_mode: 'ninguno' } as never)
      await alResumenDePelicula()
      expect(dato('Pistas')).toBe('Sin cambios (Ninguno) · el original no se toca')
      expect(dato('Copia')).not.toContain('reflink')
    })

    it('si se abrió desde una petición dice cuál cubre y cuánto paga', async () => {
      m(getRequestDetail).mockResolvedValue({ title: 'Dune (2021)', points: 1200 } as never)
      await alResumenDePelicula({ requestId: 5 })
      await esperar(() => dato('Petición').includes('Cubre'))
      expect(dato('Petición')).toBe('Cubre «Dune (2021)» · 1200 pts')
      expect(getRequestDetail).toHaveBeenCalledWith(5)
    })

    it('una petición abierta que la subida no cubre se avisa', async () => {
      m(biblioteca.getLibraryItem).mockResolvedValue(elemento({ peticion: { id: 7, title: 'Dune 4K' } as never }))
      await alResumenDePelicula()
      await esperar(() => dato('Petición').includes('Hay una abierta'))
      expect(dato('Petición')).toContain('«Dune 4K»')
      expect(document.querySelector('.asist-aviso-dato')).not.toBeNull()
    })

    it('«En eMuwarez ya hay» pone mejor, igual o peor a cada torrent del catálogo local', async () => {
      const hace3h = new Date(Date.now() - 3 * 3600_000).toISOString()
      m(biblioteca.getEmuSyncStatus).mockResolvedValue({ last_sync_at: hace3h } as never)
      m(biblioteca.getEmuComparison).mockResolvedValue({
        available: true, message: null, in_catalog: 1, matches: [
          { name: 'Dune 2021 720p HDTV', resolution: '720p', source: 'HDTV', codec: null, has_spanish: 1, size: 1, veredicto: 'mejor' },
          { name: 'Dune 2021 1080p WEB-DL', resolution: '1080p', source: 'WEB-DL', codec: null, has_spanish: 1, size: 1, veredicto: 'igual' },
          { name: 'Dune 2021 2160p BluRay', resolution: '2160p', source: 'BluRay', codec: null, has_spanish: 1, size: 1, veredicto: 'peor' },
        ],
      })
      await alResumenDePelicula()
      const filas = await esperar(() => {
        const f = [...document.querySelectorAll('.asist-tabla-yahay tbody tr')]
        return f.length === 3 ? f.map(r => [...r.querySelectorAll('td')].map(c => c.textContent)) : null
      })
      expect(filas).toEqual([
        ['Dune 2021 720p HDTV', '720p HDTV', 'mejor'],
        ['Dune 2021 1080p WEB-DL', '1080p WEB-DL', 'igual'],
        ['Dune 2021 2160p BluRay', '2160p BluRay', 'peor'],
      ])
      expect(texto()).toContain('Del catálogo local, sincronizado hace 3 h. No cuenta como permiso: revisa las reglas de trumps.')
      // Con una calidad igual a alguna, la conclusión dice que sería un duplicado.
      expect(document.querySelector('[data-testid="conclusion-duplicados"]')!.textContent).toContain('duplicado')
    })

    it('si lo tuyo mejora todo lo que hay, la conclusión dice que puede ser un trump', async () => {
      m(biblioteca.getEmuComparison).mockResolvedValue({
        available: true, message: null, in_catalog: 1, matches: [
          { name: 'Dune 2021 720p HDTV', resolution: '720p', source: 'HDTV', codec: null, has_spanish: 1, size: 1, veredicto: 'mejor' },
        ],
      })
      await alResumenDePelicula()
      const c = await esperar(() => document.querySelector('[data-testid="conclusion-duplicados"]'))
      expect(c.textContent).toContain('puede ser un trump')
    })

    it('sin nada en el catálogo lo dice', async () => {
      await alResumenDePelicula()
      await esperar(() => texto().includes('Nada de esto está en eMuwarez todavía.'))
    })

    it('sin catálogo local sincronizado no afirma que sea único', async () => {
      m(biblioteca.getEmuComparison).mockResolvedValue({ available: false, message: 'Sincroniza con eMuwarez para ver la comparación.', matches: [] })
      await alResumenDePelicula()
      await esperar(() => texto().includes('Sin catálogo local: sincroniza con eMuwarez'))
      expect(texto()).not.toContain('Nada de esto está en eMuwarez')
    })

    it('si el catálogo no responde, el resto del Resumen sigue ahí', async () => {
      m(biblioteca.getEmuComparison).mockRejectedValue(new Error('500'))
      await alResumenDePelicula()
      await esperar(() => texto().includes('No se pudo leer el catálogo local.'))
      expect(dato('Categoría')).toBe('Película · WEB-DL · 1080p')
    })

    it('si una comprobación falla se ve el Resumen pero no se puede subir', async () => {
      m(subidas.runUploadChecks).mockResolvedValue({
        ready: false, checks: [{ id: 'emuwarez', label: 'eMuwarez no disponible', status: 'fail', message: 'Sin clave' }],
      } as never)
      await abrir(PELICULA)
      await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✗ La subida no se puede realizar'))
      expect(dato('Categoría')).toBe('Película · WEB-DL · 1080p')
      expect(boton('Subir a eMuwarez')!.disabled).toBe(true)
      expect(document.querySelector('[role="status"]')?.textContent).toContain('✗ La subida no se puede realizar')
    })

    it('«← Volver» regresa al paso de nombre y pistas', async () => {
      await alResumenDePelicula()
      await pulsar(boton('← Volver'))
      expect(campo('Tag')).toBeDefined()
      expect(textos()).toEqual(['1 · Nombre y pistas', '2 · Resumen'])
    })
  })

  describe('un pack de temporada', () => {
    it('cuenta los capítulos y la carpeta, y la categoría es la de una serie', async () => {
      await abrir(TEMPORADA, { preselect: { season: 1 } })
      await pulsar(await esperar(() => boton('Continuar')))
      await esperar(() => texto().includes('Serie S01 WEB-DL DD 5.1 [GRP]'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ Todo listo para subir'))
      expect(textos()).toEqual(['✓ 1 · Contenido (hecho)', '✓ 2 · Nombre y pistas (hecho)', '3 · Resumen'])
      expect(document.querySelector('.asist-nombre-torrent')?.textContent).toBe('Serie S01 WEB-DL DD 5.1 [GRP]')
      expect(dato('Ficheros')).toBe('2 capítulos en una carpeta')
      expect(dato('Categoría')).toBe('Serie · WEB-DL · 1080p')
      expect(dato('Petición')).toBe('Ninguna abierta para esta temporada')
      expect(dato('Pistas')).toBe('Solo renombrar')
      expect(biblioteca.getEmuComparison).toHaveBeenCalledWith(20, { resolution: '1080p', source: 'WEB-DL' })
    })
  })

  describe('una tanda', () => {
    it('varios capítulos: los lista, cuenta cuáles no están en eMuwarez y pide el catálogo de cada uno', async () => {
      m(biblioteca.getLibrary).mockResolvedValue({ items: [E1, E2], total: 2 } as never)
      m(nom.getNomenclatureFields).mockImplementation(async id => respuestaCampos({ title: 'Serie', tag: `G${id}` }) as never)
      m(biblioteca.getEmuComparison).mockImplementation(async id => ({
        available: true, message: null, in_catalog: id === 21 ? 1 : 0,
        matches: id === 21
          ? [{ name: 'Serie S01E01 1080p', resolution: '1080p', source: 'WEB-DL', codec: null, has_spanish: 1, size: 1, veredicto: 'igual' }]
          : [],
      }))
      m(getRequestDetail).mockResolvedValue({ title: 'Serie S01', points: null } as never)
      await abrir(TEMPORADA, { preselect: { season: 1 }, requestId: 8 })
      await pulsar(await esperar(() => tarjeta('Selección de capítulos')))
      await pulsar(boton('E01'))
      await pulsar(boton('E02'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('Serie WEB-DL AMZN [G21]'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ Todo listo: 2 capítulos'))

      expect([...document.querySelectorAll('.asist-lista-subida li')].length).toBe(2)
      expect(dato('Ficheros')).toBe('2 capítulos')
      expect(dato('Categoría')).toBe('Serie')
      await esperar(() => dato('Petición').includes('Cubre'))
      expect(dato('Petición')).toBe('Cubre «Serie S01»')
      await esperar(() => texto().includes('1 de 2 no están en eMuwarez.'))
      expect(m(biblioteca.getEmuComparison).mock.calls).toEqual([[21, undefined], [22, undefined]])
      expect(textos()).toEqual(['✓ 1 · Contenido (hecho)', '✓ 2 · Nombre y pistas (hecho)', '3 · Resumen'])
    })

    it('varias temporadas sin petición: no afirma que no haya otra abierta', async () => {
      m(biblioteca.getLibrary).mockResolvedValue({ items: [T1, T2], total: 2 } as never)
      await abrir(SERIE, { preselect: { season: 1 } })
      await pulsar(await esperar(() => boton('Temporada 2')))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ Todo listo: 2 temporadas'))
      expect(dato('Ficheros')).toBe('2 temporadas')
      await esperar(() => dato('Petición') === 'Ninguna enlazada')
      expect(biblioteca.getLibraryItem).not.toHaveBeenCalled()
    })
  })
})

// Nomenclatura, Pistas y MediaInfo viven como pestañas del paso «Nombre y pistas», no como modales encima.
describe('las pestañas del paso «Nombre y pistas»', () => {
  const INFORME = { available: true, message: null, rows: [{ field: 'Contenedor', mediainfo: 'Matroska', emu: 'MKV' }] }
  const pestanas = () => [...document.querySelectorAll<HTMLElement>('[role="tab"]')]
  const seleccionada = () => pestanas().find(t => t.getAttribute('aria-selected') === 'true')?.textContent?.trim()
  const dialogos = () => document.querySelectorAll('[role="dialog"]').length
  const tecla = async (el: Element, key: string) => {
    await act(async () => { el.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true })) })
  }
  async function alPaso1() {
    m(biblioteca.getMediaInfoReport).mockResolvedValue(INFORME as never)
    await abrir(PELICULA)
    await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
  }

  it('son tres pestañas del paso y no abren ningún modal', async () => {
    await alPaso1()
    expect(document.querySelector('[role="tablist"]')?.getAttribute('aria-label')).toBe('Detalle del archivo')
    await esperar(() => pestanas()[1]?.textContent?.includes('1 sin idioma'))
    expect(pestanas().map(t => t.textContent?.trim())).toEqual(['Nomenclatura', 'Pistas: 1 sin idioma', 'MediaInfo'])
    expect(seleccionada()).toBe('Nomenclatura')
    await abrirPestana('Pistas')
    await esperar(() => document.querySelector('table'))
    await abrirPestana('MediaInfo')
    await esperar(() => texto().includes('Matroska'))
    expect(dialogos()).toBe(1)
    expect(boton('Ver Pistas')).toBeUndefined()
    expect(boton('Ver MediaInfo')).toBeUndefined()
  })

  it('el panel va enlazado a su pestaña y solo hay un panel', async () => {
    await alPaso1()
    await abrirPestana('Pistas')
    const activa = pestana('Pistas')!
    const paneles = document.querySelectorAll('[role="tabpanel"]')
    expect(paneles.length).toBe(1)
    expect(activa.getAttribute('aria-controls')).toBe(paneles[0].id)
    expect(paneles[0].getAttribute('aria-labelledby')).toBe(activa.id)
    // Solo la activa entra en el orden de Tab.
    expect(pestanas().map(t => t.tabIndex)).toEqual([-1, 0, -1])
  })

  it('las flechas, Inicio y Fin mueven el foco y abren la pestaña', async () => {
    await alPaso1()
    await esperar(() => pestanas()[1]?.textContent?.includes('1 sin idioma'))
    await tecla(pestanas()[0], 'ArrowRight')
    expect(seleccionada()).toBe('Pistas: 1 sin idioma')
    expect(document.activeElement).toBe(pestanas()[1])
    await tecla(pestanas()[1], 'End')
    expect(seleccionada()).toBe('MediaInfo')
    expect(document.activeElement).toBe(pestanas()[2])
    await tecla(pestanas()[2], 'ArrowRight')
    expect(seleccionada()).toBe('Nomenclatura')
    await tecla(pestanas()[0], 'ArrowLeft')
    expect(seleccionada()).toBe('MediaInfo')
    await tecla(pestanas()[2], 'Home')
    expect(seleccionada()).toBe('Nomenclatura')
    // Otras teclas no hacen nada.
    await tecla(pestanas()[0], 'a')
    expect(seleccionada()).toBe('Nomenclatura')
  })

  it('cambiar de pestaña no pierde lo editado ni repite lo ya cargado', async () => {
    await alPaso1()
    await elegir(campo('Tag'), 'OTRO')
    await abrirPestana('Pistas')
    const nombres = await esperar(() => {
      const l = [...document.querySelectorAll<HTMLInputElement>('table input.form-input')]
      return l.length ? l : null
    })
    await escribir(nombres[1], 'Castellano')
    await abrirPestana('MediaInfo')
    await esperar(() => texto().includes('Matroska'))
    await abrirPestana('Pistas')
    expect([...document.querySelectorAll<HTMLInputElement>('table input.form-input')][1].value).toBe('Castellano')
    await abrirPestana('Nomenclatura')
    expect(campo('Tag')!.value).toBe('OTRO')
    await abrirPestana('MediaInfo')
    expect(biblioteca.getMediaInfoReport).toHaveBeenCalledTimes(1)
    expect(nom.previewTrackRemux).toHaveBeenCalledTimes(1)
    // Y lo editado en Pistas llega a la cola.
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ Todo listo para subir'))
    await pulsar(boton('Subir a eMuwarez'))
    await esperar(() => m(subidas.queueUpload).mock.calls.length > 0)
    expect(m(subidas.queueUpload).mock.calls[0][1]).toEqual({ 1: { new_name: 'Castellano' } })
  })

  it('el nombre del torrent sigue a la vista en las tres pestañas', async () => {
    await alPaso1()
    for (const nombre of ['Pistas', 'MediaInfo', 'Nomenclatura']) {
      await abrirPestana(nombre)
      expect(texto()).toContain('Dune WEB-DL AMZN [GRP]')
    }
  })

  it('si MediaInfo falla, volver a la pestaña lo pide otra vez', async () => {
    await alPaso1()
    m(biblioteca.getMediaInfoReport).mockReset()
    m(biblioteca.getMediaInfoReport).mockRejectedValueOnce(new Error('Sin lectura')).mockResolvedValue(INFORME as never)
    await abrirPestana('MediaInfo')
    await esperar(() => texto().includes('✗ Sin lectura'))
    await abrirPestana('Nomenclatura')
    await abrirPestana('MediaInfo')
    await esperar(() => texto().includes('Matroska'))
    expect(biblioteca.getMediaInfoReport).toHaveBeenCalledTimes(2)
  })

  it('en un pack de temporada cada pestaña pide sus capítulos una sola vez', async () => {
    m(temporada.getSeasonEpisodeMediaInfo).mockResolvedValue({ episodes: [{ episode_id: 21, display_title: 'E01', report: INFORME }] } as never)
    m(temporada.getSeasonEpisodeRemuxPreview).mockResolvedValue({ episodes: [{
      episode_id: 21, display_title: 'E01',
      plan: { status: 'preview', errors: [], warnings: [], track_mode: 'reorder_rename', ordered_tracks: [{
        id: 1, type: 'audio', language: 'spa', current_name: '', default_after: true, new_name: 'Castellano del capítulo',
      }] },
    }] } as never)
    await abrir(TEMPORADA, { preselect: { season: 1 } })
    await pulsar(await esperar(() => boton('Continuar')))
    await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
    expect(pestanas().map(t => t.textContent?.trim())).toEqual(['Nomenclatura', 'Pistas: 1 sin idioma', 'MediaInfo'])
    await abrirPestana('MediaInfo')
    await esperar(() => texto().includes('Matroska'))
    await abrirPestana('Pistas')
    await esperar(() => texto().includes('Castellano del capítulo'))
    await abrirPestana('MediaInfo')
    await abrirPestana('Nomenclatura')
    expect(texto()).toContain('✓ 2 capítulo(s) listos')
    expect(temporada.getSeasonEpisodeMediaInfo).toHaveBeenCalledTimes(1)
    expect(temporada.getSeasonEpisodeRemuxPreview).toHaveBeenCalledTimes(1)
    expect(dialogos()).toBe(1)
  })

  it('en una tanda de capítulos las pistas se ven pero no se editan', async () => {
    m(biblioteca.getLibrary).mockResolvedValue({ items: [E1, E2], total: 2 } as never)
    m(nom.getNomenclatureFields).mockImplementation(async id => respuestaCampos({ title: 'Serie', tag: `G${id}` }) as never)
    await abrir(TEMPORADA)
    await pulsar(await esperar(() => tarjeta('Selección de capítulos')))
    await pulsar(boton('E01'))
    await pulsar(boton('E02'))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('Serie WEB-DL AMZN [G21]'))
    await abrirPestana('Pistas')
    await esperar(() => texto().includes('Al subir varios capítulos a la vez'))
    expect(document.querySelector('table input.form-input')).toBeNull()
  })
})

// El pie del asistente queda fuera del cuerpo que hace scroll: se ve siempre, a cualquier alto de ventana.
describe('el marco: cuerpo con scroll y pie siempre a la vista', () => {
  const marco = () => document.querySelector<HTMLElement>('.asist-marco')!
  const pieFueraDelCuerpo = () => {
    const pie = marco().querySelector('.asist-pie')
    const cuerpo = marco().querySelector('.asist-cuerpo')
    return !!pie && !!cuerpo && !cuerpo.contains(pie) && pie.parentElement === cuerpo.parentElement
  }

  it('el panel es el marco, el cuerpo del paso es lo que se desplaza y el pie va aparte', async () => {
    await abrir(PELICULA)
    await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
    expect(marco().classList.contains('modal-panel')).toBe(true)
    expect(marco().querySelectorAll('.asist-cuerpo').length).toBe(1)
    expect(pieFueraDelCuerpo()).toBe(true)
  })

  it('el pie del paso 1 está ya mientras carga, con Continuar apagado', async () => {
    const campos = diferida<unknown>()
    m(nom.getNomenclatureFields).mockReturnValue(campos.promesa as never)
    await abrir(PELICULA)
    await esperar(() => texto().includes('Generando Nomenclatura'))
    expect(pieFueraDelCuerpo()).toBe(true)
    expect(boton('Continuar')!.disabled).toBe(true)
    await act(async () => { campos.resolver(respuestaCampos()) })
    await esperar(() => !boton('Continuar')!.disabled)
  })

  it('el pie está en los tres pasos de una serie', async () => {
    m(biblioteca.getLibrary).mockResolvedValue({ items: [T1, T2], total: 2 } as never)
    await abrir(SERIE, { preselect: { season: 1 } })
    await esperar(() => boton('Temporada 1'))
    expect(pieFueraDelCuerpo()).toBe(true)
    await pulsar(boton('Temporada 2'))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
    expect(pieFueraDelCuerpo()).toBe(true)
    expect(boton('Volver a la selección')).toBeDefined()
    await pulsar(boton('Continuar'))
    await esperar(() => boton('Subir todas'))
    expect(pieFueraDelCuerpo()).toBe(true)
  })

  it('el veredicto de las comprobaciones va en el pie, junto a «Subir», y no en el cuerpo que se desplaza', async () => {
    await abrir(PELICULA)
    await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
    await pulsar(boton('Continuar'))
    await esperar(() => marco().querySelector('.asist-pie [role="status"]')?.textContent === '✓ Todo listo para subir')
    expect(marco().querySelector('.asist-cuerpo')!.textContent).not.toContain('Todo listo')
  })

  it('el fallo al encolar también se ve en el pie', async () => {
    m(subidas.queueUpload).mockResolvedValue({ status: 'blocked', errors: ['qBittorrent no responde.'] } as never)
    await abrir(PELICULA)
    await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
    await pulsar(boton('Continuar'))
    await esperar(() => !boton('Subir a eMuwarez')!.disabled)
    await pulsar(boton('Subir a eMuwarez'))
    await esperar(() => marco().querySelector('.asist-pie [role="status"]')?.textContent?.includes('✗ No se pudo encolar la subida'))
    expect(marco().querySelector('.asist-pie [role="status"]')!.textContent).toContain('qBittorrent no responde.')
  })

  it('el veredicto de una tanda también va en el pie', async () => {
    m(biblioteca.getLibrary).mockResolvedValue({ items: [T1, T2], total: 2 } as never)
    await abrir(SERIE, { preselect: { season: 1 } })
    await pulsar(await esperar(() => boton('Temporada 2')))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
    await pulsar(boton('Continuar'))
    await esperar(() => marco().querySelector('.asist-pie [role="status"]')?.textContent === '✓ Todo listo: 2 temporadas')
  })

  it('con pestañas el panel mantiene su alto; en los demás pasos se ajusta al contenido', async () => {
    await abrir(PELICULA)
    await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
    expect(marco().classList.contains('asist-alto-fijo')).toBe(true)
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ Todo listo para subir'))
    expect(marco().classList.contains('asist-alto-fijo')).toBe(false)
  })

  it('los modales que se abren encima no son el marco: siguen haciendo scroll como siempre', async () => {
    m(temporada.getSeasonEpisodeNames).mockResolvedValue({ episodes: [{ episode_id: 21, display_title: 'E01', torrent_name: 'A', internal_mkv_title: 'B' }] } as never)
    await abrir(TEMPORADA, { preselect: { season: 1 } })
    await pulsar(await esperar(() => boton('Continuar')))
    await pulsar(await esperar(() => boton('Ver nombre de todos los capítulos')))
    await esperar(() => document.querySelectorAll('[role="dialog"]').length === 2)
    expect(dialogoDeArriba().classList.contains('asist-marco')).toBe(false)
  })
})

// En una tanda el Resumen dice el nombre del torrent de cada elemento, no solo su título.
describe('el Resumen de una tanda lista el nombre de cada torrent', () => {
  const lista = () => [...document.querySelectorAll('.asist-lista-subida li')].map(li => (
    [...li.querySelectorAll('span')].map(x => x.textContent).join(' | ')))

  describe('temporadas', () => {
    beforeEach(() => { m(biblioteca.getLibrary).mockResolvedValue({ items: [T1, T2], total: 2 } as never) })

    async function alResumen() {
      await abrir(SERIE, { preselect: { season: 1 } })
      await pulsar(await esperar(() => boton('Temporada 2')))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
      await pulsar(boton('Continuar'))
    }

    it('usa el `nombre` que devuelven las comprobaciones de cada pack', async () => {
      m(subidas.runUploadChecks).mockImplementation(async (id, alcance) => (alcance === 'environment'
        ? ENTORNO : { ...LISTO, nombre: `Serie (2020) S0${id - 30} 1080p WEB-DL-GRP` }) as never)
      await alResumen()
      await esperar(() => texto().includes('✓ Todo listo: 2 temporadas'))
      expect(lista()).toEqual([
        'Serie (2021) - Temporada 1 | Serie (2020) S01 1080p WEB-DL-GRP',
        'Serie (2021) - Temporada 2 | Serie (2020) S02 1080p WEB-DL-GRP',
      ])
    })

    it('si un pack no da nombre, dice que no se podrá subir', async () => {
      m(subidas.runUploadChecks).mockImplementation(async (id, alcance) => {
        if (alcance === 'environment') return ENTORNO as never
        return (id === 32
          ? { ready: false, nombre: null, checks: [{ id: 'season_pack', label: 'Pack', status: 'fail', message: 'Falta un capítulo' }] }
          : { ...LISTO, nombre: 'Serie (2020) S01 1080p WEB-DL-GRP' }) as never
      })
      await alResumen()
      await esperar(() => texto().includes('✗ 1 de 2 no se puede subir'))
      expect(lista()).toEqual([
        'Serie (2021) - Temporada 1 | Serie (2020) S01 1080p WEB-DL-GRP',
        'Serie (2021) - Temporada 2 | Sin nombre: este elemento no se podrá subir',
      ])
    })

    it('el pack se comprueba con lo editado a mano, para que su nombre sea el que saldrá', async () => {
      await abrir(SERIE, { preselect: { season: 1 } })
      await pulsar(await esperar(() => boton('Temporada 2')))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
      await elegir(campo('Tag'), 'OTRO')
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ Todo listo: 2 temporadas'))
      const deLaPrimera = m(subidas.runUploadChecks).mock.calls.find(c => c[0] === 31 && c[1] === 'content')!
      expect(deLaPrimera[3]).toEqual({ source: 'WEB-DL', tag: 'OTRO', title: 'Serie' })
      // Volver, cambiar el Tag y entrar otra vez: lo comprobado con el Tag de antes ya no vale.
      await pulsar(boton('← Volver'))
      await elegir(await esperar(() => campo('Tag')), 'GRP')
      await pulsar(boton('Continuar'))
      await esperar(() => m(subidas.runUploadChecks).mock.calls.some(c => c[0] === 31 && c[3]?.tag === 'GRP'))
    })

    it('una película suelta no cambia: su nombre sigue saliendo de la nomenclatura', async () => {
      await abrir(PELICULA)
      await esperar(() => texto().includes('Dune WEB-DL AMZN [GRP]'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ Todo listo para subir'))
      expect(document.querySelector('.asist-lista-subida')).toBeNull()
      expect(document.querySelector('.asist-nombre-torrent')?.textContent).toBe('Dune WEB-DL AMZN [GRP]')
      expect(m(subidas.runUploadChecks).mock.calls[0]).toEqual([10, undefined, undefined])
    })
  })

  describe('capítulos', () => {
    beforeEach(() => {
      m(biblioteca.getLibrary).mockResolvedValue({ items: [E1, E2], total: 2 } as never)
      m(nom.getNomenclatureFields).mockImplementation(async id => respuestaCampos({ title: 'Serie', tag: `G${id}` }) as never)
    })

    async function alResumen() {
      await abrir(TEMPORADA)
      await pulsar(await esperar(() => tarjeta('Selección de capítulos')))
      await pulsar(boton('E01'))
      await pulsar(boton('E02'))
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('Serie WEB-DL AMZN [G21]'))
    }

    it('calcula el de cada uno con lo generado y lo editado', async () => {
      await alResumen()
      await elegir(campo('Tag'), 'OTRO')
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ Todo listo: 2 capítulos'))
      await esperar(() => lista().length === 2 && lista().every(l => !l.includes('Calculando')))
      expect(lista()).toEqual([
        'Serie (2021) - S01E01 | Serie WEB-DL AMZN [OTRO]',
        'Serie (2021) - S01E02 | Serie WEB-DL AMZN [G22]',
      ])
    })

    it('un capítulo con la nomenclatura bloqueada sale sin nombre', async () => {
      m(nom.getNomenclatureFields).mockImplementation(async id => (id === 22
        ? { fields: {}, torrent_name: '', internal_mkv_title: '', blocked: true, error: 'Sin acceso al archivo' }
        : respuestaCampos({ title: 'Serie', tag: `G${id}` })) as never)
      await alResumen()
      await pulsar(boton('Continuar'))
      await esperar(() => texto().includes('✓ Todo listo: 2 capítulos'))
      await esperar(() => lista().length === 2 && lista().every(l => !l.includes('Calculando')))
      expect(lista()).toEqual([
        'Serie (2021) - S01E01 | Serie WEB-DL AMZN [G21]',
        'Serie (2021) - S01E02 | Sin nombre: este elemento no se podrá subir',
      ])
    })

    it('si falla el cálculo de uno, ese sale sin nombre y el otro no se ve afectado', async () => {
      await alResumen()
      m(nom.previewNomenclatureFields).mockImplementation(async (id, f) => {
        if (id === 22) throw new Error('Sin conexión')
        return { torrent_name: `${f.title} ${f.source} [${f.tag}]`, internal_mkv_title: 'x' } as never
      })
      await pulsar(boton('Continuar'))
      await esperar(() => lista().length === 2 && lista().every(l => !l.includes('Calculando')))
      expect(lista()).toEqual([
        'Serie (2021) - S01E01 | Serie WEB-DL [G21]',
        'Serie (2021) - S01E02 | Sin nombre: este elemento no se podrá subir',
      ])
    })
  })
})
