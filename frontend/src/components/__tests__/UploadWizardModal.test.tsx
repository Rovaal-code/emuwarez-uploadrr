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
vi.mock('../../api/library', () => ({ getLibrary: vi.fn(), getMediaInfoReport: vi.fn(), suggestProvider: vi.fn() }))
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
import { fetchSettings } from '../../api/settings'
import type { TrackRemuxPreview } from '../../api/nomenclature'
import type { LibraryItemResponse, SeasonPackPlanResponse, UploadJob } from '../../types/api'
import { UploadWizardModal } from '../UploadWizardModal'
import { boton, campo, tarjeta, desmontar, diferida, elegir, escribir, esperar, montar, pulsar, texto } from './dom'

const m = vi.mocked

/** El modal abierto encima de los demás (los de MediaInfo, pistas y nombres se abren sobre el asistente). */
const dialogoDeArriba = () => [...document.querySelectorAll<HTMLElement>('[role="dialog"]')].pop()!

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
    await pulsar(boton('Ver Pistas'))
    await esperar(() => texto().includes('Ordenación y Nombre de las Pistas'))
    const nombres = [...document.querySelectorAll<HTMLInputElement>('table input.form-input')]
    await escribir(nombres[1], 'Castellano')
    await pulsar(document.querySelector('[aria-label="Cerrar"]') ?? undefined)

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
    await pulsar(boton('Ver Pistas'))
    const selector = await esperar(() => document.querySelector<HTMLSelectElement>('table select'))
    await elegir(selector, 'eng')
    expect(nom.getNomenclatureFields).toHaveBeenLastCalledWith(10, { 2: 'eng' })
    expect(nom.applyTrackRemux).toHaveBeenCalledWith(10, { dryRun: true, overrides: { 2: { language: 'eng' } } })
    await pulsar(document.querySelector('[aria-label="Cerrar"]') ?? undefined)
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
    expect(texto()).toContain('Nombre final del torrent (pack de temporada)')

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
    async function cambiarIdiomaYAbrir(nombreBoton: string) {
      const audio = diferida<unknown>()
      m(temporada.getSeasonPackAudio).mockReturnValue(audio.promesa as never)
      await abrir(TEMPORADA, { preselect: { season: 1 } })
      await pulsar(await esperar(() => boton('Continuar')))
      await esperar(() => boton('Ver nombre de todos los capítulos'))
      await elegir(campo('Pista de audio 1'), 'spa')
      await pulsar(boton(nombreBoton))
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
      await cambiarIdiomaYAbrir('Ver nombre de todos los capítulos')
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
      await cambiarIdiomaYAbrir('Ver Pistas')
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
  })

  it('cambiar el Proveedor en el paso 1 vuelve a comprobar el contenido de esa temporada', async () => {
    await abrir(SERIE, { preselect: { season: 1 } })
    await pulsar(await esperar(() => boton('Temporada 2')))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ 2 capítulo(s) listos'))
    await pulsar(boton('Continuar'))
    await esperar(() => texto().includes('✓ Todo listo: 2 temporadas'))
    await pulsar(boton('Volver'))
    await elegir(await esperar(() => campo<HTMLSelectElement>('Proveedor')), 'NF')
    await pulsar(boton('Continuar'))
    await esperar(() => m(subidas.runUploadChecks).mock.calls.some(c => c[0] === 31 && c[2] === 'NF'))
    await esperar(() => texto().includes('✓ Todo listo: 2 temporadas'))
    expect(m(subidas.runUploadChecks).mock.calls).toEqual([
      [31, 'environment'], [31, 'content', undefined], [32, 'content', undefined], [31, 'content', 'NF'],
    ])
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
      await pulsar(await esperar(() => boton('Volver')))
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
      await pulsar(boton('Volver'))
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
