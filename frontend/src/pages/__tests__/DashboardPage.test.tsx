// @vitest-environment jsdom
/**
 * «Hoy» con el servidor simulado: los tres carriles con datos y vacíos, la franja de cinco números, y lo que hace
 * «Subir» (abrir el asistente sobre la fila de la petición, con la petición).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/dashboard', () => ({ getDashboardSummary: vi.fn(), getDashboardRecommendations: vi.fn() }))
vi.mock('../../api/uploads', () => ({ getUploads: vi.fn() }))
vi.mock('../../api/settings', () => ({ fetchSettings: vi.fn() }))
vi.mock('../../api/maintenance', () => ({ getVersionInfo: vi.fn() }))
vi.mock('../../api/library', () => ({ getLibraryItem: vi.fn() }))
vi.mock('../../api/eventos', () => ({
  suscribirse: vi.fn(() => () => {}), canalVivo: vi.fn(() => true), observarCanal: vi.fn(() => () => {}),
}))
vi.mock('../../components/CuentaEmu', () => ({ CuentaEmu: () => null }))
vi.mock('../../components/SyncCard', () => ({ SyncCard: () => <button>↻ Sincronizar todo</button> }))
vi.mock('../../components/UploadWizardModal', () => ({
  UploadWizardModal: (p: { item: { id: number }; preselect?: unknown; requestId?: number }) => (
    <div data-testid="asistente">{JSON.stringify({ id: p.item.id, preselect: p.preselect ?? null, requestId: p.requestId ?? null })}</div>
  ),
}))
vi.mock('../../components/RequestFormModal', () => ({
  RequestFormModal: (p: { item: { id: number } }) => <div data-testid="formulario">{p.item.id}</div>,
}))

import type { DashboardRecommendationItem } from '../../api/dashboard'
import { getDashboardRecommendations, getDashboardSummary } from '../../api/dashboard'
import { getLibraryItem } from '../../api/library'
import { getVersionInfo } from '../../api/maintenance'
import { fetchSettings } from '../../api/settings'
import { getUploads } from '../../api/uploads'
import { SeccionVisible } from '../../context/SeccionVisible'
import { SyncContext } from '../../context/SyncContext'
import type { DashboardSummaryResponse, LibraryItemResponse, UploadJob } from '../../types/api'
import { desmontar, esperar, montar, pulsar, texto } from '../../components/__tests__/dom'
import { DashboardPage } from '../DashboardPage'

const resumen = (extra: Partial<DashboardSummaryResponse> = {}): DashboardSummaryResponse => ({
  library_total: 51372, available: 15861, missing: 57, uploading: 0, completed: 0, unique_content: 283,
  uploads_completed: 14, radarr_items: 1, sonarr_items: 1, last_sync_at: null, next_sync_at: null,
  requests_total: 322, ...extra,
})
const rec = (extra: Partial<DashboardRecommendationItem>): DashboardRecommendationItem => ({
  id: 1, rec_group: 1, item_type: 'movie', title: 'T', content_name: 'T', year: null, poster_url: null,
  local_status: null, season_number: null, episode_number: null, size_bytes: null, resolution: null, source: null,
  instance_type: null, instance_id: null, tmdb_id: null, title_slug: null, missing_count: null,
  rec_request_id: null, rec_points: null, ...extra,
})
const trabajo = (extra: Partial<UploadJob>) => ({ id: 1, status: 'queued', ...extra } as UploadJob)

const navegar = vi.fn()
const fichaDe = (id: number) => ({ id, item_type: 'movie', title: `Ficha ${id}` }) as unknown as LibraryItemResponse

async function pagina() {
  await montar(
    <SyncContext.Provider value={{ lastInvalidatedAt: 0, startAllSync: vi.fn(), isAnySyncing: false, todoPendiente: false } as never}>
      <SeccionVisible visible><DashboardPage onNavigate={navegar} /></SeccionVisible>
    </SyncContext.Provider>,
  )
  await esperar(() => document.querySelector('.panel-carriles'))
}

const carril = (titulo: string) =>
  [...document.querySelectorAll('section.panel-carril')].find(s => s.querySelector('h2')?.textContent === titulo)!
const filas = (titulo: string) => [...carril(titulo).querySelectorAll('.panel-item')]
const botonDe = (donde: Element, nombre: string) =>
  [...donde.querySelectorAll('button')].find(b => b.textContent?.trim() === nombre)

beforeEach(() => {
  vi.mocked(getDashboardSummary).mockResolvedValue(resumen())
  vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [] })
  vi.mocked(getUploads).mockResolvedValue([])
  vi.mocked(fetchSettings).mockResolvedValue({ recent_activity_limit: 100 } as never)
  vi.mocked(getVersionInfo).mockResolvedValue({ version: '0.14.0', estado: 'al_dia', ultima: {} })
  vi.mocked(getLibraryItem).mockImplementation(async id => fichaDe(id))
  navegar.mockReset()
  sessionStorage.clear()
})
afterEach(desmontar)

describe('Hoy', () => {
  it('con datos: los tres carriles en su orden y la franja de cinco números', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [
      rec({ id: 1, content_name: 'La bola negra (2026)', rec_request_id: 11, rec_points: 120000, resolution: '1080p', source: 'WEB-DL', has_spanish_audio: 1, has_spanish_subs: 0, size_bytes: 6 * 1024 ** 3 }),
      rec({ id: 2, content_name: 'Kill Bill (2011)', rec_request_id: 12, rec_points: 10000 }),
    ] })
    vi.mocked(getUploads).mockResolvedValue([
      trabajo({ id: 7, status: 'queued', title: 'Papillon (1973)', queue_position: 1 }),
      trabajo({ id: 8, status: 'running', title: 'Dragon Ball Daima · Temporada 1', progress_phase: 'hash_torrent', started_at: new Date().toISOString() }),
    ])
    await pagina()
    await esperar(() => filas('En curso').length === 0 && carril('En curso').querySelectorAll('.upload-row').length === 2)

    expect(texto()).toContain('Hoy')
    expect([...document.querySelectorAll('section.panel-carril h2')].map(h => h.textContent))
      .toEqual(['Listo para subir', 'En curso', 'Necesita atención'])

    // Las peticiones salen en el orden del servidor (por recompensa), con su línea de datos y su recompensa.
    const peticiones = filas('Listo para subir')
    expect(peticiones.map(f => f.querySelector('.panel-item-titulo')!.textContent)).toEqual(['La bola negra (2026)', 'Kill Bill (2011)'])
    expect(peticiones[0].textContent).toContain('Película · 1080p WEB-DL · castellano (audio) · 6,0 GB')
    expect(peticiones[0].textContent).toContain('120.000')
    expect(carril('Listo para subir').textContent).toContain('2 peticiones')

    // En curso: la que trabaja antes que la que espera.
    const subidas = [...carril('En curso').querySelectorAll('.upload-row-title')].map(t => t.textContent)
    expect(subidas).toEqual(['Dragon Ball Daima · Temporada 1', 'Papillon (1973)'])
    expect(carril('En curso').textContent).toContain('1 subiendo · 1 en cola')

    // La franja: los cinco números del mockup, con miles a la española.
    const franja = [...document.querySelectorAll('.panel-franja-cifra')].map(c => c.textContent)
    expect(franja).toEqual(['en biblioteca51.372', 'en disco15.861', 'únicos sin subir283', 'peticiones abiertas322', 'tus subidas14'])
  })

  it('vacío: dice qué falta en cada carril y no inventa avisos', async () => {
    await pagina()
    expect(carril('Listo para subir').textContent).toContain('Ninguna petición lista')
    expect(carril('En curso').textContent).toContain('Sin subidas en curso')
    expect(carril('Necesita atención').textContent).toContain('Nada que revisar')
    expect(document.querySelector('.panel-mas')).toBeNull()
    expect(carril('Necesita atención').querySelector('.panel-aviso')).toBeNull()
  })

  it('«Necesita atención» enseña la instancia caída, la subida fallida y la versión nueva; nada en verde', async () => {
    vi.mocked(getDashboardSummary).mockResolvedValue(resumen({
      instancias_caidas: [{ id: 3, nombre: 'Radarr up', tipo: 'radarr', ultima_sincronizacion: new Date(Date.now() - 26 * 3600e3).toISOString() }],
    }))
    vi.mocked(getUploads).mockResolvedValue([
      trabajo({ id: 9, status: 'failed', title: 'Youjo Senki S01E12', error_message: 'Duplicado en eMuwarez', finished_at: new Date().toISOString() }),
    ])
    vi.mocked(getVersionInfo).mockResolvedValue({ version: '0.14.0', estado: 'hay_novedad', ultima: { version: '0.14.1' } })
    await pagina()
    await esperar(() => carril('Necesita atención').querySelectorAll('.panel-aviso').length === 3)

    const avisos = [...carril('Necesita atención').querySelectorAll('.panel-aviso')].map(a => a.textContent)
    expect(avisos[0]).toContain('Radarr up no responde')
    expect(avisos[0]).toContain('Biblioteca de hace 26 h · se sincroniza sola al volver')
    expect(avisos[1]).toContain('Subida fallida · Youjo Senki S01E12')
    expect(avisos[1]).toContain('Duplicado en eMuwarez')
    expect(avisos[2]).toContain('Versión nueva 0.14.1 publicada')
    expect(texto()).not.toContain('Configurado')
    expect(carril('Necesita atención').querySelector('.panel-carril-nota')!.textContent).toBe('3')

    // «Ver motivo» abre esa subida en Subidas.
    const ver = [...carril('Necesita atención').querySelectorAll('[role="link"]')].find(l => l.textContent === 'Ver motivo')!
    await pulsar(ver)
    expect(sessionStorage.getItem('emuwarez_open_upload')).toBe('9')
    expect(navegar).toHaveBeenCalledWith('uploads')
  })

  it('«Subir» abre el asistente sobre la temporada de la petición, con su selección y la petición', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [
      rec({ id: 5, library_target_id: 55, item_type: 'season', season_number: 2, episode_number: null, rec_request_id: 77, rec_points: 500, content_name: 'Serie (2016) - Temporada 2' }),
      rec({ id: 6, library_target_id: 66, item_type: 'episode', season_number: 1, episode_number: 12, rec_request_id: 78, rec_points: 400, content_name: 'Serie (2016) - S01E12' }),
    ] })
    await pagina()
    await pulsar(botonDe(filas('Listo para subir')[0], 'Subir'))
    await esperar(() => document.querySelector('[data-testid="asistente"]'))
    expect(vi.mocked(getLibraryItem)).toHaveBeenCalledWith(55)
    expect(JSON.parse(document.querySelector('[data-testid="asistente"]')!.textContent!))
      .toEqual({ id: 55, preselect: { season: 2, episode: null }, requestId: 77 })
  })

  it('«Subir» de un capítulo preselecciona también el capítulo', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [
      rec({ id: 6, library_target_id: 66, item_type: 'episode', season_number: 1, episode_number: 12, rec_request_id: 78, rec_points: 400 }),
    ] })
    await pagina()
    await pulsar(botonDe(filas('Listo para subir')[0], 'Subir'))
    await esperar(() => document.querySelector('[data-testid="asistente"]'))
    expect(JSON.parse(document.querySelector('[data-testid="asistente"]')!.textContent!).preselect).toEqual({ season: 1, episode: 12 })
  })

  it('si el contenido ya no está, «Subir» lo dice en vez de no hacer nada', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [rec({ id: 5, rec_request_id: 77, rec_points: 5 })] })
    vi.mocked(getLibraryItem).mockRejectedValue(new Error('404'))
    await pagina()
    await pulsar(botonDe(filas('Listo para subir')[0], 'Subir'))
    await esperar(() => document.querySelector('[role="alert"]'))
    expect(document.querySelector('[role="alert"]')!.textContent).toContain('No se pudo abrir ese contenido')
    expect(document.querySelector('[data-testid="asistente"]')).toBeNull()
  })

  it('«Ver petición» y el título llevan a Peticiones y a la ficha', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [rec({ id: 5, rec_request_id: 77, rec_points: 5, content_name: 'Pedida (2020)' })] })
    await pagina()
    const fila = filas('Listo para subir')[0]
    await pulsar([...fila.querySelectorAll('[role="link"]')].find(l => l.textContent === 'Ver petición'))
    expect(sessionStorage.getItem('emuwarez_open_request')).toBe('77')
    expect(navegar).toHaveBeenLastCalledWith('requests')

    await pulsar(fila.querySelector('.panel-item-titulo')!)
    expect(sessionStorage.getItem('emuwarez_open_library_item')).toBe('5')
    expect(navegar).toHaveBeenLastCalledWith('library')
  })

  it('los grupos 2 y 3 siguen a mano, plegados bajo las peticiones: «Subir» sin petición y «Pedir»', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [
      rec({ id: 1, rec_request_id: 11, rec_points: 9 }),
      rec({ id: 20, rec_group: 2, content_name: 'Único (2001)' }),
      rec({ id: 30, rec_group: 3, content_name: 'Faltante (2002)', missing_count: 3, item_type: 'season' }),
    ] })
    await pagina()
    const mas = document.querySelector('details.panel-mas')!
    expect(mas.textContent).toContain('Contenido único que puedes subir')
    expect(mas.textContent).toContain('Faltantes que podrías pedir a eMuwarez')
    expect(mas.textContent).toContain('faltan 3')
    // Solo la petición cuenta en «Listo para subir».
    expect(carril('Listo para subir').textContent).toContain('1 petición')

    const unico = [...mas.querySelectorAll('.panel-item')].find(f => f.textContent!.includes('Único (2001)'))!
    await pulsar(botonDe(unico, 'Subir'))
    await esperar(() => document.querySelector('[data-testid="asistente"]'))
    expect(JSON.parse(document.querySelector('[data-testid="asistente"]')!.textContent!))
      .toEqual({ id: 20, preselect: null, requestId: null })

    const faltante = [...mas.querySelectorAll('.panel-item')].find(f => f.textContent!.includes('Faltante (2002)'))!
    await pulsar(botonDe(faltante, 'Pedir'))
    await esperar(() => document.querySelector('[data-testid="formulario"]'))
    expect(document.querySelector('[data-testid="formulario"]')!.textContent).toBe('30')
  })

  it('«Ver todas las subidas» abre Subidas', async () => {
    await pagina()
    await pulsar([...carril('En curso').querySelectorAll('[role="link"]')].find(l => l.textContent === 'Ver todas las subidas'))
    expect(navegar).toHaveBeenCalledWith('uploads')
  })

  it('la cabecera lleva un solo botón de sincronizar', async () => {
    await pagina()
    expect([...document.querySelectorAll('button')].filter(b => b.textContent!.includes('↻')).map(b => b.textContent))
      .toEqual(['↻ Sincronizar todo'])
  })
})
