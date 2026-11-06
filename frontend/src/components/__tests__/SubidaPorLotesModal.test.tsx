// @vitest-environment jsdom
/**
 * «Subir por lotes» con el servidor simulado: qué se comprueba y cuándo (nada en el paso 1; el entorno una vez y el
 * contenido por elemento en el paso 2), qué llega desmarcado o se salta y por qué, cuándo se habilita «Subir (N)»,
 * qué se manda a POST /uploads/lote y cómo se enseña lo que respondió. Y las series: cada una se cambia por sus
 * temporadas (packs) en el paso 1, y el Resumen de una temporada sale de sus comprobaciones.
 */
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/uploads', () => ({ queueLote: vi.fn(), runUploadChecks: vi.fn(), getUploadChecksProgress: vi.fn() }))
vi.mock('../../api/nomenclature', () => ({ getNomenclatureFields: vi.fn(), previewNomenclatureFields: vi.fn() }))
vi.mock('../../api/library', () => ({ getEmuComparison: vi.fn(), getLibrary: vi.fn(), suggestProvider: vi.fn() }))
vi.mock('../../api/settings', () => ({ fetchSettings: vi.fn() }))
vi.mock('../../api/eventos', () => ({ seguirProgreso: vi.fn(() => () => {}) }))

import * as subidas from '../../api/uploads'
import * as nom from '../../api/nomenclature'
import * as biblioteca from '../../api/library'
import { fetchSettings } from '../../api/settings'
import { ApiClientError } from '../../api/client'
import type { EmuComparison } from '../../api/library'
import type { LibraryItemResponse } from '../../types/api'
import type { EntradaLote } from '../../utils/lote'
import { SubidaPorLotesModal } from '../lote/SubidaPorLotesModal'
import { boton, desmontar, diferida, elegir, esperar, montar, pulsar, texto } from './dom'

const m = vi.mocked

const peli = (id: number, title: string, extra: Partial<LibraryItemResponse> = {}) => ({
  id, item_type: 'movie', title, year: 2021, local_status: 'Disponible', has_spanish_ok: 1,
  resolution: '1080p', source: 'BluRay', ...extra,
}) as LibraryItemResponse

const DUNE = peli(11, 'Dune')
const ALIEN = peli(12, 'Alien')
const HEAT = peli(13, 'Heat')

const CAMPOS = {
  title: 'X', year: '2021', resolution: '1080p', source: 'BluRay', provider: null, video_codec: 'x264',
  audio_summary: 'Castellano DD 5.1', subs: 'SUBS', tag: 'GRP',
}
const ENTORNO = { ready: true, checks: [{ id: 'emuwarez', label: 'eMuwarez responde', status: 'ok' as const, message: '' }] }
const LISTO = { ready: true, checks: [{ id: 'accesible', label: 'Fichero accesible', status: 'ok' as const, message: '' }] }
const SIN_NADA: EmuComparison = { available: true, message: null, matches: [] }

const nombreDe = (id: number) => `Peli ${id} (2021) 1080p BluRay x264-GRP`

const onClose = vi.fn()
const onDone = vi.fn()
const onNavigate = vi.fn()

async function abrir(seleccion: LibraryItemResponse[]) {
  await abrirEntradas(seleccion.map(item => ({ item })))
}

async function abrirEntradas(entradas: EntradaLote[]) {
  await montar(<SubidaPorLotesModal entradas={entradas} onClose={onClose} onDone={onDone} onNavigate={onNavigate} />)
}

const llamadas = (scope: 'environment' | 'content') => m(subidas.runUploadChecks).mock.calls.filter(c => c[1] === scope)
const fila = (id: number) => document.querySelector<HTMLTableRowElement>(`tr[data-item="${id}"]`)!
const incluir = (titulo: string) => document.querySelector<HTMLInputElement>(`input[aria-label="Incluir «${titulo}»"]`)!
const casillaPaso1 = (titulo: string) =>
  [...document.querySelectorAll<HTMLLabelElement>('.lote-fila label')].find(l => l.textContent?.startsWith(titulo))!.querySelector('input')!
const botonSubir = () => [...document.querySelectorAll('button')].find(b => /^Subir \(\d+\)$/.test(b.textContent ?? ''))
const escape = () => act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })) })

async function alResumen(n: number) {
  await pulsar(boton(`Continuar (${n})`))
  await esperar(() => texto().includes('Se subirán') && !document.querySelector('.asist-spinner-14'))
}

beforeEach(() => {
  m(subidas.runUploadChecks).mockImplementation(async (_id, scope) => (scope === 'environment' ? ENTORNO : LISTO))
  m(nom.getNomenclatureFields).mockImplementation(async id => ({
    fields: { ...CAMPOS }, torrent_name: nombreDe(id), internal_mkv_title: '', blocked: false,
  }))
  m(biblioteca.getEmuComparison).mockResolvedValue(SIN_NADA)
  m(fetchSettings).mockResolvedValue({ upload_max_concurrent: 1 } as never)
  m(subidas.queueLote).mockImplementation(async elementos => ({
    lote_id: '0123456789ab', encolados: elementos.length, saltados: 0,
    resultados: elementos.map((e, i) => ({ item_id: e.item_id, status: 'queued', job_id: 100 + i, errors: [] })),
  }))
})
afterEach(async () => {
  await desmontar()
  vi.clearAllMocks()
  sessionStorage.clear()
})

describe('qué se comprueba y cuándo', () => {
  it('un lote de una sola película se comprueba y se sube', async () => {
    await abrir([DUNE])
    await alResumen(1)
    expect(fila(11).textContent).toContain(nombreDe(11))
    expect(fila(11).textContent).toContain('No hay nada igual en eMuwarez.')
    expect(incluir('Dune').checked).toBe(true)
    expect(botonSubir()!.disabled).toBe(false)
    await pulsar(botonSubir())
    await esperar(() => texto().includes('1 de 1 encolada'))
    expect(subidas.queueLote).toHaveBeenCalledTimes(1)
  })

  it('nada se comprueba mientras se está en el paso 1; el entorno, una sola vez para todas', async () => {
    await abrir([DUNE, ALIEN, HEAT])
    expect(texto()).toContain('3 de 3 marcadas')
    expect(subidas.runUploadChecks).not.toHaveBeenCalled()
    expect(nom.getNomenclatureFields).not.toHaveBeenCalled()
    await alResumen(3)
    expect(llamadas('environment')).toHaveLength(1)
    expect(llamadas('content').map(c => c[0])).toEqual([11, 12, 13])
    expect(m(nom.getNomenclatureFields).mock.calls.map(c => c[0])).toEqual([11, 12, 13])
  })

  it('volver sin cambiar nada no repite; cambiar la selección lo vuelve a comprobar', async () => {
    await abrir([DUNE, ALIEN])
    await alResumen(2)
    await pulsar(boton('← Volver'))
    await alResumen(2)
    expect(llamadas('environment')).toHaveLength(1)
    expect(llamadas('content')).toHaveLength(2)

    await pulsar(boton('← Volver'))
    await pulsar(casillaPaso1('Alien'))
    expect(texto()).toContain('1 de 2 marcadas')
    await alResumen(1)
    expect(llamadas('environment')).toHaveLength(2)
    expect(llamadas('content').map(c => c[0])).toEqual([11, 12, 11])
    expect(document.querySelector('tr[data-item="12"]')).toBeNull()
  })

  it('una película sin castellano sale desmarcada y sin poder marcarse, con su motivo', async () => {
    await abrir([DUNE, peli(14, 'Sin castellano', { has_spanish_ok: 0 })])
    expect(casillaPaso1('Sin castellano').disabled).toBe(true)
    expect(casillaPaso1('Sin castellano').checked).toBe(false)
    expect(texto()).toContain('No tiene castellano ni en el audio ni en los subtítulos.')
    expect(boton('Continuar (1)')).toBeDefined()
  })
})

describe('qué llega desmarcado o se salta', () => {
  it('con la nomenclatura bloqueada se saltará y no se manda', async () => {
    m(nom.getNomenclatureFields).mockImplementation(async id => (id === 12
      ? { fields: {}, torrent_name: '', internal_mkv_title: '', blocked: true, error: 'MediaInfo no puede leer el fichero.' }
      : { fields: { ...CAMPOS }, torrent_name: nombreDe(id), internal_mkv_title: '', blocked: false }))
    await abrir([DUNE, ALIEN])
    await alResumen(2)
    expect(fila(12).textContent).toContain('MediaInfo no puede leer el fichero.')
    expect(fila(12).textContent).toContain('Se saltará')
    // Sin nombre, su «—» lleva una clase para que la tarjeta del móvil (sin cabecera) lo quite; el de la que sí lo
    // tiene, no. La celda de eMuwarez lleva la suya para su etiqueta.
    expect(fila(12).querySelector('.lote-nombre')!.classList.contains('lote-nombre-vacio')).toBe(true)
    expect(fila(11).querySelector('.lote-nombre')!.classList.contains('lote-nombre-vacio')).toBe(false)
    expect(fila(11).querySelector('td.lote-celda-emu')).not.toBeNull()
    expect(incluir('Alien').checked).toBe(false)
    expect(incluir('Alien').disabled).toBe(true)
    await pulsar(boton('Subir (1)'))
    await esperar(() => m(subidas.queueLote).mock.calls.length)
    expect(m(subidas.queueLote).mock.calls[0][0].map(e => e.item_id)).toEqual([11])
  })

  it('una pista sin idioma enseña el aviso y llega desmarcada, pero se puede marcar', async () => {
    m(nom.getNomenclatureFields).mockImplementation(async id => ({
      fields: { ...CAMPOS }, torrent_name: nombreDe(id), internal_mkv_title: '', blocked: false,
      audio_warning: id === 11 ? 'Una pista de audio no tiene idioma: el nombre no la incluye.' : null,
    }))
    await abrir([DUNE, ALIEN])
    await alResumen(2)
    expect(fila(11).textContent).toContain('Una pista de audio no tiene idioma')
    expect(incluir('Dune').checked).toBe(false)
    expect(incluir('Dune').disabled).toBe(false)
    expect(fila(11).textContent).toContain('Súbela suelta para elegir el idioma')
    expect(boton('Subir (1)')).toBeDefined()
    await pulsar(incluir('Dune'))
    expect(boton('Subir (2)')).toBeDefined()
  })

  it('un duplicado en eMuwarez llega desmarcado con su veredicto', async () => {
    m(biblioteca.getEmuComparison).mockImplementation(async id => (id === 12
      ? { available: true, message: null, matches: [{ name: 'Alien 1080p', resolution: '1080p', source: 'BluRay', codec: null, has_spanish: 1, size: null, veredicto: 'igual' }] }
      : SIN_NADA))
    await abrir([DUNE, ALIEN])
    await alResumen(2)
    expect(fila(12).textContent).toContain('la subida sería un duplicado')
    expect(incluir('Alien').checked).toBe(false)
    expect(incluir('Dune').checked).toBe(true)
    // Lo que compara es lo que irá en el nombre.
    expect(biblioteca.getEmuComparison).toHaveBeenCalledWith(12, { resolution: '1080p', source: 'BluRay' })
  })

  it('dos películas que saldrían con el mismo nombre se saltan las dos', async () => {
    m(nom.getNomenclatureFields).mockResolvedValue({ fields: { ...CAMPOS }, torrent_name: 'Igual', internal_mkv_title: '', blocked: false })
    await abrir([DUNE, ALIEN])
    await alResumen(2)
    expect(fila(11).textContent).toContain('mismo nombre')
    expect(incluir('Dune').disabled).toBe(true)
    expect(incluir('Alien').disabled).toBe(true)
    expect(botonSubir()!.disabled).toBe(true)
  })

  it('una que ya se salta por otro motivo no bloquea a la otra con el mismo nombre', async () => {
    m(nom.getNomenclatureFields).mockResolvedValue({ fields: { ...CAMPOS }, torrent_name: 'Igual', internal_mkv_title: '', blocked: false })
    const MAL = { ready: false, checks: [{ id: 'spanish', label: 'No tiene castellano', status: 'fail' as const, message: '' }] }
    m(subidas.runUploadChecks).mockImplementation(async (id, scope) =>
      scope === 'environment' ? ENTORNO : id === 12 ? MAL : LISTO)
    await abrir([DUNE, ALIEN])
    await alResumen(2)
    expect(fila(11).textContent).not.toContain('mismo nombre')
    expect(fila(12).textContent).toContain('No tiene castellano')
    expect(incluir('Dune').disabled).toBe(false)
    await esperar(() => botonSubir() && !botonSubir()!.disabled)
  })
})

describe('cuándo se habilita «Subir»', () => {
  it('no mientras falta una comprobación de contenido', async () => {
    const pendiente = diferida<typeof LISTO>()
    m(subidas.runUploadChecks).mockImplementation(async (id, scope) =>
      scope === 'environment' ? ENTORNO : id === 12 ? pendiente.promesa : LISTO)
    await abrir([DUNE, ALIEN])
    await pulsar(boton('Continuar (2)'))
    await esperar(() => fila(11)?.textContent?.includes('✓ Lista'))
    expect(fila(12).textContent).toContain('Comprobando…')
    expect(botonSubir()!.disabled).toBe(true)
    await act(async () => { pendiente.resolver(LISTO) })
    await esperar(() => botonSubir() && !botonSubir()!.disabled)
  })

  it('no con el entorno fallido, y «Volver a comprobar» lo repite', async () => {
    const MAL = { ready: false, checks: [{ id: 'qbittorrent', label: 'qBittorrent', status: 'fail' as const, message: 'No responde' }] }
    m(subidas.runUploadChecks).mockImplementation(async (_id, scope) => (scope === 'environment' ? MAL : LISTO))
    await abrir([DUNE])
    await alResumen(1)
    expect(texto()).toContain('✗ La subida no se puede realizar')
    expect(botonSubir()!.disabled).toBe(true)
    m(subidas.runUploadChecks).mockImplementation(async (_id, scope) => (scope === 'environment' ? ENTORNO : LISTO))
    await pulsar(boton('↻ Volver a comprobar'))
    await esperar(() => botonSubir() && !botonSubir()!.disabled)
    expect(llamadas('environment')).toHaveLength(2)
  })

  it('no con una comprobación de contenido fallida para todas', async () => {
    const FALLA = { ready: false, checks: [{ id: 'spanish', label: 'Castellano', status: 'fail' as const, message: 'Sin castellano' }] }
    m(subidas.runUploadChecks).mockImplementation(async (_id, scope) => (scope === 'environment' ? ENTORNO : FALLA))
    await abrir([DUNE])
    await alResumen(1)
    // Qué falló (la etiqueta) y el detalle, no solo el detalle.
    expect(fila(11).textContent).toContain('✗ Castellano: Sin castellano')
    expect(fila(11).textContent).toContain('Se saltará')
    expect(botonSubir()!.disabled).toBe(true)
    // «0 se subirán» no es una buena noticia: sin el verde de las cifras que sí lo son.
    expect(document.querySelector('.lote-cifra')!.textContent).toBe('0 se subirán')
    expect(document.querySelector('.lote-cifra')!.classList.contains('lote-cifra-bien')).toBe(false)
  })
})

describe('lo que se manda y lo que vuelve', () => {
  it('manda el orden del lote, las comprobaciones de cada una con las comunes y los campos completos', async () => {
    m(nom.getNomenclatureFields).mockImplementation(async id => ({
      fields: { ...CAMPOS, source: id === 12 ? 'WEB-DL' : 'BluRay' }, torrent_name: nombreDe(id), internal_mkv_title: '', blocked: false,
    }))
    m(biblioteca.suggestProvider).mockResolvedValue({ suggested: 'NF', tmdb_providers: ['NF'], reason: '' })
    m(nom.previewNomenclatureFields).mockResolvedValue({
      torrent_name: 'Alien (2021) 1080p NF WEB-DL x264-GRP', internal_mkv_title: '', fields: {}, provider_options: [],
    })
    await abrir([ALIEN, DUNE])
    await alResumen(2)
    expect(fila(12).textContent).toContain('Alien (2021) 1080p NF WEB-DL x264-GRP')
    // Solo a la WEB-DL sin proveedor se le sugiere.
    expect(biblioteca.suggestProvider).toHaveBeenCalledTimes(1)
    expect(biblioteca.suggestProvider).toHaveBeenCalledWith(12)
    await pulsar(boton('Subir (2)'))
    await esperar(() => texto().includes('2 de 2 encoladas'))
    const merged = { ready: true, checks: [...LISTO.checks, ...ENTORNO.checks] }
    expect(subidas.queueLote).toHaveBeenCalledWith([
      { item_id: 12, checks: merged, campos: { ...CAMPOS, source: 'WEB-DL', provider: 'NF' } },
      { item_id: 11, checks: merged },
    ])
  })

  it('con «Subidas en paralelo» a 0 avisa de que irán todas a la vez', async () => {
    m(fetchSettings).mockResolvedValue({ upload_max_concurrent: 0 } as never)
    await abrir([DUNE, ALIEN])
    await alResumen(2)
    expect(texto()).toContain('Sin límite: se lanzarán las 2 a la vez contra eMuwarez')
    // El nombre real de la sección y del campo, con las comillas del resto de la interfaz.
    expect(texto()).toContain('Configuración → Otros, «Máximo de subidas en paralelo»')
  })

  it('dice de cuántas en cuántas irán según el ajuste', async () => {
    m(fetchSettings).mockResolvedValue({ upload_max_concurrent: 2 } as never)
    await abrir([DUNE])
    await alResumen(1)
    expect(texto()).toContain('Se subirán de 2 en 2 según «Máximo de subidas en paralelo» (ahora: 2)')
  })

  it('un resultado parcial lista las saltadas con su motivo', async () => {
    m(subidas.queueLote).mockResolvedValue({
      lote_id: '0123456789ab', encolados: 1, saltados: 1,
      resultados: [
        { item_id: 11, status: 'queued', job_id: 100, errors: [] },
        { item_id: 12, status: 'blocked', job_id: null, errors: ['Ya hay una subida en curso para este contenido.'] },
      ],
    })
    await abrir([DUNE, ALIEN])
    await alResumen(2)
    await pulsar(boton('Subir (2)'))
    await esperar(() => texto().includes('1 de 2 encoladas'))
    expect(texto()).toContain('✗ Alien: Ya hay una subida en curso para este contenido.')
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('un 409 enseña sus motivos y no da nada por encolado', async () => {
    m(subidas.queueLote).mockRejectedValue(new ApiClientError('Conflict', 409, {
      detail: ['Falta la clave de la API de eMuwarez.', 'Falta la clave de TMDb.'],
    }))
    await abrir([DUNE])
    await alResumen(1)
    await pulsar(boton('Subir (1)'))
    await esperar(() => texto().includes('Falta la clave de TMDb.'))
    expect(texto()).toContain('Falta la clave de la API de eMuwarez.')
    expect(texto()).toContain('No se ha encolado nada')
    expect(onDone).not.toHaveBeenCalled()
    expect(boton('Subir (1)')).toBeDefined()
  })

  it('«Ver el lote en Subidas» lo deja apuntado y va a Subidas', async () => {
    await abrir([DUNE])
    await alResumen(1)
    await pulsar(boton('Subir (1)'))
    await pulsar(await esperar(() => boton('Ver el lote en Subidas')))
    expect(sessionStorage.getItem('emuwarez_open_lote')).toBe('0123456789ab')
    expect(onNavigate).toHaveBeenCalledWith('uploads')
    expect(onClose).toHaveBeenCalled()
  })

  it('Escape tras encolar cierra, y la selección ya se limpió', async () => {
    await abrir([DUNE])
    await alResumen(1)
    await pulsar(boton('Subir (1)'))
    await esperar(() => boton('Ver el lote en Subidas'))
    expect(onDone).toHaveBeenCalledTimes(1)
    await escape()
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('mientras se encola no se cierra', async () => {
    const respuesta = diferida<Awaited<ReturnType<typeof subidas.queueLote>>>()
    m(subidas.queueLote).mockReturnValue(respuesta.promesa)
    await abrir([DUNE])
    await alResumen(1)
    await pulsar(boton('Subir (1)'))
    expect(texto()).toContain('Encolando…')
    await escape()
    expect(onClose).not.toHaveBeenCalled()
    await act(async () => {
      respuesta.resolver({ lote_id: '0123456789ab', encolados: 1, saltados: 0, resultados: [{ item_id: 11, status: 'queued', job_id: 1, errors: [] }] })
    })
    await esperar(() => texto().includes('1 de 1 encolada'))
    await escape()
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

// ── Series y temporadas ─────────────────────────────────────────────────────────────────────────────────────────

const serie = (id: number, title: string) =>
  ({ id, item_type: 'series', title, year: 2020, local_status: 'Disponible', has_spanish_ok: 1 }) as LibraryItemResponse
const temporada = (id: number, de: LibraryItemResponse, n: number, extra: Partial<LibraryItemResponse> = {}) => ({
  id, item_type: 'season', title: `${de.title} - Temporada ${n}`, year: 2020, parent_id: de.id, season_number: n,
  local_status: 'Disponible', has_spanish_ok: 1, resolution: '1080p', video_codec: 'x264', source: 'WEB-DL', ...extra,
}) as LibraryItemResponse

const LOST = serie(100, 'Lost')
const FARGO = serie(200, 'Fargo')
// Lost: tres aptas para pack y una incompleta; Fargo: dos aptas. Las da getLibrary desordenadas.
const TEMPORADAS: Record<number, LibraryItemResponse[]> = {
  100: [temporada(103, LOST, 3), temporada(101, LOST, 1), temporada(102, LOST, 2),
        temporada(104, LOST, 4, { local_status: 'Parcial' })],
  200: [temporada(201, FARGO, 1), temporada(202, FARGO, 2)],
}
const packDe = (id: number) => `Pack ${id} S01 1080p WEB-DL x264-GRP`
const PACK_LISTO = (id: number) => ({ ...LISTO, nombre: packDe(id) })

const titulosPaso1 = () => [...document.querySelectorAll('.lote-fila-titulo')].map(e => e.textContent)
const temporadas = () => m(biblioteca.getLibrary).mock.calls.map(c => c[0])

describe('series y temporadas', () => {
  beforeEach(() => {
    m(biblioteca.getLibrary).mockImplementation(async q => {
      const items = TEMPORADAS[q!.parent_id as number] ?? []
      return { items, total: items.length } as never
    })
    m(subidas.runUploadChecks).mockImplementation(async (id, scope) =>
      scope === 'environment' ? ENTORNO : id > 100 ? PACK_LISTO(id) : LISTO)
  })

  it('dos series con 3 y 2 temporadas aptas dan 5 filas marcadas; la no apta, desmarcada con su motivo', async () => {
    await abrir([LOST, FARGO])
    await esperar(() => texto().includes('Continuar'))
    expect(temporadas()).toEqual([
      { parent_id: 100, type: 'season', limit: 500 }, { parent_id: 200, type: 'season', limit: 500 },
    ])
    expect(titulosPaso1()).toEqual([
      'Lost (2020) - Temporada 1', 'Lost (2020) - Temporada 2', 'Lost (2020) - Temporada 3',
      'Lost (2020) - Temporada 4', 'Fargo (2020) - Temporada 1', 'Fargo (2020) - Temporada 2',
    ])
    expect(texto()).toContain('5 de 6 marcadas')
    expect(casillaPaso1('Lost (2020) - Temporada 4').checked).toBe(false)
    expect(casillaPaso1('Lost (2020) - Temporada 4').disabled).toBe(true)
    expect(texto()).toContain('Temporada incompleta: no todos los capítulos están Disponibles.')
    expect(boton('Continuar (5)')).toBeDefined()
  })

  it('enseña el progreso mientras carga las temporadas, y no deja continuar', async () => {
    const lost = diferida<{ items: LibraryItemResponse[]; total: number }>()
    m(biblioteca.getLibrary).mockImplementation(async q => (q!.parent_id === 100
      ? lost.promesa
      : { items: TEMPORADAS[200], total: 2 }) as never)
    await abrir([LOST, FARGO])
    expect(texto()).toContain('Cargando las temporadas de las series marcadas (1 de 2)')
    expect(boton('Continuar (0)')).toBeUndefined()
    await act(async () => { lost.resolver({ items: TEMPORADAS[100], total: 4 }) })
    await esperar(() => boton('Continuar (5)'))
  })

  it('una serie y una de sus temporadas marcadas a la vez no la duplican', async () => {
    await abrir([TEMPORADAS[100][2], LOST])
    await esperar(() => texto().includes('Continuar'))
    expect(titulosPaso1()).toEqual([
      'Lost (2020) - Temporada 2', 'Lost (2020) - Temporada 1', 'Lost (2020) - Temporada 3', 'Lost (2020) - Temporada 4',
    ])
    expect(boton('Continuar (3)')).toBeDefined()
  })

  it('una serie que no se pudo cargar lo dice, y el resto sigue', async () => {
    m(biblioteca.getLibrary).mockRejectedValue(new Error('Sin conexión'))
    await abrir([LOST, DUNE])
    await esperar(() => texto().includes('Continuar'))
    expect(texto()).toContain('No se pudieron cargar las temporadas de «Lost»: Sin conexión')
    expect(titulosPaso1()).toEqual(['Dune (2021)'])
  })

  it('el tope de 50 cuenta después de expandir', async () => {
    const muchas = Array.from({ length: 49 }, (_, i) => temporada(1000 + i, LOST, i + 1))
    m(biblioteca.getLibrary).mockResolvedValue({ items: muchas, total: 49 } as never)
    await abrir([LOST, DUNE, ALIEN])
    await esperar(() => texto().includes('Continuar'))
    expect(texto()).toContain('50 de 51 marcadas')
    expect(boton('Continuar (50)')).toBeDefined()
    // Lleno: Alien, la última, llega desmarcada y no se puede marcar sin desmarcar otra.
    expect(casillaPaso1('Alien').checked).toBe(false)
    expect(casillaPaso1('Alien').disabled).toBe(true)
    await pulsar(casillaPaso1('Dune'))
    expect(casillaPaso1('Alien').disabled).toBe(false)
  })

  it('el Resumen de una temporada da el nombre del pack que dicen sus comprobaciones', async () => {
    await abrir([TEMPORADAS[100][1]])
    await alResumen(1)
    expect(fila(101).textContent).toContain(packDe(101))
    expect(fila(101).textContent).toContain('No hay nada igual en eMuwarez.')
    // Ni su nomenclatura ni su proveedor se miran aparte: los dice el plan del pack.
    expect(nom.getNomenclatureFields).not.toHaveBeenCalled()
    expect(biblioteca.suggestProvider).not.toHaveBeenCalled()
    expect(m(biblioteca.getEmuComparison).mock.calls).toEqual([[101, undefined]])
  })

  it('una temporada enseña los avisos de su plan, y con audio sin idioma llega desmarcada', async () => {
    m(subidas.runUploadChecks).mockImplementation(async (id, scope) => scope === 'environment' ? ENTORNO : {
      ...PACK_LISTO(id), avisos: ['Capítulo 2: el source no cuadra.', 'La pista 2 no tiene idioma.'], sin_idioma: true,
    })
    await abrir([TEMPORADAS[100][1]])
    await alResumen(1)
    expect(fila(101).textContent).toContain('Capítulo 2: el source no cuadra.')
    expect(fila(101).textContent).toContain('La pista 2 no tiene idioma.')
    expect(fila(101).querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked).toBe(false)
    expect(fila(101).textContent).toContain('Súbela suelta para elegir el idioma')
  })

  it('un lote mixto de película y temporada manda las dos en orden, sin campos ni proveedor en la temporada', async () => {
    m(nom.getNomenclatureFields).mockImplementation(async id => ({
      fields: { ...CAMPOS, source: 'WEB-DL' }, torrent_name: nombreDe(id), internal_mkv_title: '', blocked: false,
    }))
    m(biblioteca.suggestProvider).mockResolvedValue({ suggested: 'NF', tmdb_providers: ['NF'], reason: '' })
    m(nom.previewNomenclatureFields).mockResolvedValue({
      torrent_name: 'Dune (2021) 1080p NF WEB-DL x264-GRP', internal_mkv_title: '', fields: {}, provider_options: [],
    })
    await abrir([DUNE, TEMPORADAS[200][0]])
    await alResumen(2)
    expect(fila(11).textContent).toContain('Dune (2021) 1080p NF WEB-DL x264-GRP')
    expect(fila(201).textContent).toContain(packDe(201))
    await pulsar(boton('Subir (2)'))
    await esperar(() => texto().includes('2 de 2 encoladas'))
    const [enviados] = m(subidas.queueLote).mock.calls[0]
    expect(enviados.map(e => e.item_id)).toEqual([11, 201])
    expect(enviados[0].campos).toEqual({ ...CAMPOS, source: 'WEB-DL', provider: 'NF' })
    expect(enviados[1]).toEqual({
      item_id: 201, checks: { ready: true, checks: [...LISTO.checks, ...ENTORNO.checks] },
    })
  })

  it('un pack que no se puede preparar se salta con el motivo de su comprobación', async () => {
    const CONFLICTO = {
      ready: false, nombre: null, checks: [{
        id: 'season_pack', label: 'No se puede preparar el pack de temporada', status: 'fail' as const,
        message: 'Los capítulos vienen de proveedores distintos (AMZN, NF): elige uno en Proveedor.',
      }],
    }
    m(subidas.runUploadChecks).mockImplementation(async (id, scope) =>
      scope === 'environment' ? ENTORNO : id === 202 ? CONFLICTO : PACK_LISTO(id))
    await abrir([FARGO])
    await esperar(() => texto().includes('Continuar'))
    await alResumen(2)
    expect(fila(202).textContent).toContain('proveedores distintos (AMZN, NF)')
    expect(fila(202).textContent).toContain('Súbela suelta para elegirlo.')
    expect(fila(202).textContent).toContain('Se saltará')
    expect(incluir('Fargo - Temporada 2').disabled).toBe(true)
    expect(boton('Subir (1)')).toBeDefined()
  })

  it('dos temporadas que saldrían con el mismo nombre se saltan las dos', async () => {
    m(subidas.runUploadChecks).mockImplementation(async (_id, scope) =>
      scope === 'environment' ? ENTORNO : { ...LISTO, nombre: 'Fargo S01 1080p WEB-DL x264-GRP' })
    await abrir([FARGO])
    await esperar(() => texto().includes('Continuar'))
    await alResumen(2)
    expect(fila(201).textContent).toContain('Otro elemento del lote saldría con el mismo nombre.')
    expect(incluir('Fargo - Temporada 1').disabled).toBe(true)
    expect(incluir('Fargo - Temporada 2').disabled).toBe(true)
    expect(botonSubir()!.disabled).toBe(true)
  })
})

// ── Desde el Panel: con la petición de cada fila y su alcance ───────────────────────────────────────────────────

const capitulo = (id: number, de: LibraryItemResponse, temporadaN: number, n: number) => ({
  id, item_type: 'episode', title: `${de.title} S${String(temporadaN).padStart(2, '0')}E${String(n).padStart(2, '0')}`,
  year: 2020, season_number: temporadaN, episode_number: n, local_status: 'Disponible', has_spanish_ok: 1,
  resolution: '1080p', source: 'WEB-DL',
}) as LibraryItemResponse

const enviados = () => m(subidas.queueLote).mock.calls[0][0].map(e => ({ item_id: e.item_id, request_item_id: e.request_item_id }))
const peticionesPaso1 = () => [...document.querySelectorAll('.lote-fila-peticion')].map(e => e.textContent)

describe('desde el Panel', () => {
  beforeEach(() => {
    m(biblioteca.getLibrary).mockImplementation(async q => {
      const items = TEMPORADAS[q!.parent_id as number] ?? []
      return { items, total: items.length } as never
    })
    m(subidas.runUploadChecks).mockImplementation(async (id, scope) =>
      scope === 'environment' ? ENTORNO : id > 100 ? PACK_LISTO(id) : LISTO)
  })

  it('cada elemento lleva su petición; una de capítulo sube ese capítulo', async () => {
    await abrirEntradas([
      { item: DUNE, requestId: 77, alcance: { season: null, episode: null } },
      { item: capitulo(66, LOST, 1, 12), requestId: 78, alcance: { season: 1, episode: 12 } },
      { item: ALIEN },
    ])
    expect(titulosPaso1()).toEqual(['Dune (2021)', 'Lost (2020) - S01E12', 'Alien (2021)'])
    expect(peticionesPaso1()).toEqual(['Petición #77', 'Petición #78'])
    await alResumen(3)
    await pulsar(boton('Subir (3)'))
    await esperar(() => texto().includes('3 de 3 encoladas'))
    expect(enviados()).toEqual([
      { item_id: 11, request_item_id: 77 }, { item_id: 66, request_item_id: 78 }, { item_id: 12, request_item_id: undefined },
    ])
    // Sin petición no se manda la clave (como desde Biblioteca).
    expect('request_item_id' in m(subidas.queueLote).mock.calls[0][0][2]).toBe(false)
  })

  it('una petición de serie entera se cambia por sus temporadas, todas con la petición; una de temporada, solo esa', async () => {
    await abrirEntradas([
      { item: FARGO, requestId: 90, alcance: { season: null, episode: null } },
      { item: LOST, requestId: 91, alcance: { season: 2, episode: null } },
    ])
    await esperar(() => texto().includes('Continuar'))
    // Lost se carga una vez aunque la pidieran dos filas.
    expect(temporadas()).toEqual([
      { parent_id: 200, type: 'season', limit: 500 }, { parent_id: 100, type: 'season', limit: 500 },
    ])
    expect(titulosPaso1()).toEqual(['Fargo (2020) - Temporada 1', 'Fargo (2020) - Temporada 2', 'Lost (2020) - Temporada 2'])
    await alResumen(3)
    await pulsar(boton('Subir (3)'))
    await esperar(() => texto().includes('3 de 3 encoladas'))
    expect(enviados()).toEqual([
      { item_id: 201, request_item_id: 90 }, { item_id: 202, request_item_id: 90 }, { item_id: 102, request_item_id: 91 },
    ])
  })

  it('dos peticiones sobre el mismo elemento salen como una fila y se elige cuál se enlaza', async () => {
    const t1 = TEMPORADAS[200][0]
    await abrirEntradas([
      { item: t1, requestId: 80, alcance: { season: 1, episode: null } },
      { item: t1, requestId: 81, alcance: { season: 1, episode: null } },
    ])
    expect(titulosPaso1()).toEqual(['Fargo (2020) - Temporada 1'])
    const select = document.querySelector<HTMLSelectElement>('select[aria-label="Petición que se enlaza con «Fargo (2020) - Temporada 1»"]')!
    expect([...select.options].map(o => o.textContent)).toEqual(['Petición #80', 'Petición #81'])
    expect(select.value).toBe('80')
    await elegir(select, '81')
    await alResumen(1)
    await pulsar(boton('Subir (1)'))
    await esperar(() => texto().includes('1 de 1 encolada'))
    expect(enviados()).toEqual([{ item_id: 201, request_item_id: 81 }])
  })

  it('una petición de capítulo cuya fila no es el capítulo (no está en la biblioteca) no entra y lo dice', async () => {
    await abrirEntradas([
      { item: TEMPORADAS[200][1], requestId: 85, alcance: { season: 2, episode: 4 } },
      { item: DUNE },
    ])
    expect(texto()).toContain('«Fargo - Temporada 2»: la petición es del capítulo S02E04, que no está en la biblioteca.')
    expect(titulosPaso1()).toEqual(['Dune (2021)'])
  })
})
