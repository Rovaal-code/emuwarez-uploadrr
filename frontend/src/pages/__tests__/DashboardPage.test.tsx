// @vitest-environment jsdom
/**
 * El Panel con el servidor simulado: los dos carriles y la banda de avisos con datos y vacíos, la franja de cinco
 * números, la cuenta de eMuwarez en la cabecera y lo que hace «Subir» (abrir el asistente sobre la fila de la petición).
 * Y «Subir seleccionadas»: marcar filas de «Listo para subir» y subirlas juntas con el modal de «Subir por lotes»
 * (el de verdad), cada una con su petición.
 */
import { act, useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/dashboard', () => ({ getDashboardSummary: vi.fn(), getDashboardRecommendations: vi.fn() }))
vi.mock('../../api/uploads', () => ({
  getUploads: vi.fn(), getUploadJob: vi.fn(), queueLote: vi.fn(), runUploadChecks: vi.fn(),
  getUploadChecksProgress: vi.fn(),
}))
vi.mock('../../api/nomenclature', () => ({ getNomenclatureFields: vi.fn(), previewNomenclatureFields: vi.fn() }))
vi.mock('../../api/settings', () => ({ fetchSettings: vi.fn() }))
vi.mock('../../api/maintenance', () => ({ getVersionInfo: vi.fn() }))
vi.mock('../../api/library', () => ({
  getLibraryItem: vi.fn(), getLibrary: vi.fn(), getEmuComparison: vi.fn(), suggestProvider: vi.fn(),
}))
vi.mock('../../api/eventos', () => ({
  suscribirse: vi.fn(() => () => {}), canalVivo: vi.fn(() => true), observarCanal: vi.fn(() => () => {}),
  seguirProgreso: vi.fn(() => () => {}),
}))
// La cuenta de eMuwarez: sin perfil no pinta nada (como el componente real); con perfil, un hueco reconocible.
const cuenta = vi.hoisted(() => ({ hayPerfil: false }))
vi.mock('../../components/CuentaEmu', () => ({
  CuentaEmu: () => (cuenta.hayPerfil ? <section data-testid="cuenta">Ratio 17,31</section> : null),
}))
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
import { getEmuComparison, getLibrary, getLibraryItem } from '../../api/library'
import { getNomenclatureFields } from '../../api/nomenclature'
import { getVersionInfo } from '../../api/maintenance'
import { fetchSettings } from '../../api/settings'
import { getUploadJob, getUploads, queueLote, runUploadChecks } from '../../api/uploads'
import { suscribirse } from '../../api/eventos'
import { SeccionVisible } from '../../context/SeccionVisible'
import { SyncContext } from '../../context/SyncContext'
import type { DashboardSummaryResponse, LibraryItemResponse, UploadJob } from '../../types/api'
import { boton, desmontar, elegir, esperar, montar, pulsar, texto } from '../../components/__tests__/dom'
import { DashboardPage } from '../DashboardPage'
import { recortarEnCurso } from '../../components/hoy/CarrilEnCurso'

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

let fijarVisible: (v: boolean) => void = () => {}
function Envoltorio() {
  const [visible, setVisible] = useState(true)
  fijarVisible = setVisible
  return (
    <SyncContext.Provider value={{ lastInvalidatedAt: 0, startAllSync: vi.fn(), isAnySyncing: false, todoPendiente: false } as never}>
      <SeccionVisible visible={visible}><DashboardPage onNavigate={navegar} /></SeccionVisible>
    </SyncContext.Provider>
  )
}

async function pagina() {
  await montar(<Envoltorio />)
  await esperar(() => document.querySelector('.panel-carriles'))
}

const carril = (titulo: string) =>
  [...document.querySelectorAll('section.panel-carril')].find(s => s.querySelector('h2')?.textContent === titulo)!
const banda = () => document.querySelector('section.panel-atencion')!
const filas = (titulo: string) => [...carril(titulo).querySelectorAll('.panel-item')]
const botonDe = (donde: Element, nombre: string) =>
  [...donde.querySelectorAll('button')].find(b => b.textContent?.trim() === nombre)

beforeEach(() => {
  cuenta.hayPerfil = false
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

describe('Panel', () => {
  it('con más de 100 subidas, la que sube sigue en «En curso» aunque no esté entre las 100 más nuevas', async () => {
    // Las 100 más nuevas son de un lote en cola; la que sube es más vieja y solo llega con la petición de las vivas.
    const enCola = Array.from({ length: 100 }, (_, i) =>
      trabajo({ id: 1000 + i, status: 'queued', title: `Cola ${i}`, queue_position: i + 1 }))
    const subiendo = trabajo({ id: 7, status: 'running', title: 'Papillon (1973)', started_at: new Date().toISOString() })
    vi.mocked(getUploads).mockImplementation(async q => (q?.status ? [subiendo, ...enCola] : enCola))
    await pagina()
    await esperar(() => carril('En curso').textContent?.includes('Papillon (1973)'))
    expect(vi.mocked(getUploads).mock.calls.some(([q]) => q?.status === 'queued,staging,preparing,running')).toBe(true)
  })

  it('la vieja que termina fuera de las 100 más nuevas se despide con su estado; la fallida llega con las fallidas', async () => {
    const enCola = Array.from({ length: 100 }, (_, i) =>
      trabajo({ id: 1000 + i, status: 'queued', title: `Cola ${i}`, queue_position: i + 1 }))
    const subiendo = (id: number, title: string) =>
      trabajo({ id, status: 'running', title, started_at: new Date().toISOString() })
    const acabada = (id: number, status: string, title: string, extra: Partial<UploadJob> = {}) =>
      trabajo({ id, status, title, finished_at: new Date().toISOString(), ...extra })
    let termino = false
    vi.mocked(getUploads).mockImplementation(async q => {
      if (q?.status === 'failed') return termino ? [acabada(7, 'failed', 'Papillon (1973)', { error_message: 'Duplicado' })] : []
      if (q?.status) return termino ? enCola : [subiendo(7, 'Papillon (1973)'), subiendo(8, 'Ran (1985)'), ...enCola]
      return enCola
    })
    vi.mocked(getUploadJob).mockImplementation(async id => {
      if (id === 8) return acabada(8, 'completed', 'Ran (1985)')
      throw new Error('404')
    })
    await pagina()
    await esperar(() => carril('En curso').textContent?.includes('Ran (1985)'))
    expect(getUploadJob).not.toHaveBeenCalled()

    // Terminan: ya no están entre las vivas ni entre las 100 más nuevas. Llega el aviso de la subida.
    termino = true
    await act(async () => {
      for (const [tipo, cb] of vi.mocked(suscribirse).mock.calls) if (tipo === 'subida-estado') (cb as () => void)()
    })
    await esperar(() => vi.mocked(getUploadJob).mock.calls.length > 0)
    // La fallida llega con la lista de fallidas; solo se pide sola la completada.
    expect(vi.mocked(getUploadJob).mock.calls.map(([id]) => id)).toEqual([8])
    // Ya no cuentan como vivas (94 en cola fuera de las 6 filas), pero las dos se quedan despidiéndose.
    await esperar(() => carril('En curso').textContent?.includes('+94 en cola'))
    expect(carril('En curso').textContent).toContain('Ran (1985)')
    expect(carril('En curso').textContent).toContain('Papillon (1973)')
  })

  it('con datos: los dos carriles en su orden y la franja de cinco números', async () => {
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

    expect(document.querySelector('.page-title')!.textContent).toBe('Panel')
    expect(texto()).not.toContain('Hoy')
    expect([...document.querySelectorAll('section.panel-carril h2')].map(h => h.textContent))
      .toEqual(['Listo para subir', 'En curso'])

    // Las peticiones salen en el orden del servidor (por recompensa), con su línea de datos y su recompensa.
    const peticiones = filas('Listo para subir')
    expect(peticiones.map(f => f.querySelector('.panel-item-titulo')!.textContent)).toEqual(['La bola negra (2026)', 'Kill Bill (2011)'])
    expect(peticiones[0].textContent).toContain('Película · 1080p WEB-DL · castellano (audio) · 6,0 GB')
    expect(peticiones[0].textContent).toContain('120.000')
    expect(carril('Listo para subir').textContent).toContain('2 peticiones')

    // En curso: la que trabaja antes que la que espera.
    const subidas = [...carril('En curso').querySelectorAll('.upload-row-title')].map(t => t.textContent)
    expect(subidas).toEqual(['Dragon Ball Daima · Temporada 1', 'Papillon (1973)'])
    expect(carril('En curso').textContent).toContain('1 subiendo · 1 en cola')

    // La franja: cinco tarjetas de las globales, con miles a la española y solo «En disco» en verde.
    const franja = document.querySelector('.panel-franja')!
    expect(franja.getAttribute('aria-label')).toBe('Cifras de la biblioteca y de las peticiones')
    const tarjetas = [...franja.querySelectorAll('.stat-card')]
    expect(tarjetas.map(c => [c.querySelector('.stat-card-label')!.textContent, c.querySelector('.stat-card-value')!.textContent]))
      .toEqual([['En biblioteca', '51.372'], ['En disco', '15.861'], ['Únicos sin subir', '283'], ['Peticiones abiertas', '322'], ['Tus subidas', '14']])
    expect(tarjetas.map(c => c.querySelectorAll('.stat-card-icon svg').length)).toEqual([1, 1, 1, 1, 1])
    expect(tarjetas.map(c => c.getAttribute('aria-label')))
      .toEqual(['En biblioteca: 51.372', 'En disco: 15.861', 'Únicos sin subir: 283', 'Peticiones abiertas: 322', 'Tus subidas: 14'])
    // El color de estado va en el icono; la cifra, en el color del texto.
    expect(tarjetas.map(c => (c.querySelector('.stat-card-icon') as HTMLElement).style.color))
      .toEqual(['', 'var(--color-available)', '', '', ''])
    expect(tarjetas.map(c => (c.querySelector('.stat-card-value') as HTMLElement).style.color)).toEqual(['', '', '', '', ''])
  })

  it('vacío: la franja sigue con sus cinco tarjetas, a cero', async () => {
    vi.mocked(getDashboardSummary).mockResolvedValue(resumen({
      library_total: 0, available: 0, unique_content: 0, requests_total: 0, uploads_completed: 0, radarr_items: 0, sonarr_items: 0,
    }))
    await pagina()
    expect([...document.querySelectorAll('.panel-franja .stat-card-value')].map(v => v.textContent)).toEqual(['0', '0', '0', '0', '0'])
  })

  it('vacío: dice qué falta en cada carril y la banda de avisos es una sola línea', async () => {
    await pagina()
    expect(carril('Listo para subir').textContent).toContain('Ninguna petición lista')
    expect(carril('En curso').textContent).toContain('Sin subidas en curso')
    expect(document.querySelector('.panel-mas')).toBeNull()
    expect(banda().textContent).toBe('Todo en orden')
    expect(banda().classList.contains('panel-atencion-vacia')).toBe(true)
    expect(banda().getAttribute('aria-live')).toBe('polite')
    expect(banda().querySelector('h2, .panel-aviso, button')).toBeNull()
  })

  it('si no se pueden pedir las recomendaciones lo dice, en vez de «Ninguna petición lista», y reintenta', async () => {
    vi.mocked(getDashboardRecommendations).mockRejectedValueOnce(new Error('503'))
    await pagina()
    await esperar(() => carril('Listo para subir').querySelector('.empty-state-body')?.textContent?.includes('No se pudieron cargar'))
    expect(carril('Listo para subir').textContent).not.toContain('Ninguna petición lista')
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [rec({ id: 5, content_name: 'Drive', rec_request_id: 9, rec_points: 10 })] })
    await pulsar(botonDe(carril('Listo para subir'), 'Reintentar')!)
    await esperar(() => filas('Listo para subir').length === 1)
    expect(carril('Listo para subir').textContent).not.toContain('No se pudieron cargar')
  })

  // Una recarga que falla (la que lanza «tarea-terminada») no borra lo cargado: avisa encima y deja la lista.
  const recargar = async () => {
    await act(async () => {
      for (const [tipo, cb] of vi.mocked(suscribirse).mock.calls) if (tipo === 'tarea-terminada') (cb as () => void)()
    })
  }

  it('una recarga que falla con peticiones ya cargadas avisa encima y deja la lista, con Reintentar', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [rec({ id: 5, content_name: 'Drive', rec_request_id: 9, rec_points: 10 })] })
    await pagina()
    await esperar(() => filas('Listo para subir').length === 1)

    vi.mocked(getDashboardRecommendations).mockRejectedValue(new Error('503'))
    await recargar()
    await esperar(() => carril('Listo para subir').querySelector('.panel-aviso-carga'))
    expect(carril('Listo para subir').querySelector('.panel-aviso-carga')!.textContent).toContain('No se pudieron cargar')
    expect(carril('Listo para subir').querySelector('.empty-state')).toBeNull()
    expect(filas('Listo para subir')).toHaveLength(1)

    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [rec({ id: 5, content_name: 'Drive', rec_request_id: 9, rec_points: 10 })] })
    await pulsar(botonDe(carril('Listo para subir').querySelector('.panel-aviso-carga')!, 'Reintentar')!)
    await esperar(() => !carril('Listo para subir').querySelector('.panel-aviso-carga'))
    expect(filas('Listo para subir')).toHaveLength(1)
  })

  it('si fallan y solo quedan otras ideas, avisa y no dice «Ninguna petición lista»', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [rec({ id: 20, rec_group: 2, content_name: 'Único (2001)' })] })
    await pagina()
    await esperar(() => document.querySelector('.panel-mas'))
    expect(carril('Listo para subir').textContent).toContain('Ninguna petición lista')

    vi.mocked(getDashboardRecommendations).mockRejectedValue(new Error('503'))
    await recargar()
    await esperar(() => carril('Listo para subir').querySelector('.panel-aviso-carga'))
    expect(carril('Listo para subir').textContent).not.toContain('Ninguna petición lista')
    expect(document.querySelector('.panel-mas')).not.toBeNull()
  })

  it('la recompensa de una petición lleva su etiqueta para el lector de pantalla', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [rec({ id: 5, content_name: 'Drive', rec_request_id: 9, rec_points: 1200 })] })
    await pagina()
    await esperar(() => filas('Listo para subir').length === 1)
    expect(filas('Listo para subir')[0].querySelector('.panel-item-accion')!.textContent).toContain('Recompensa: 1200')
  })

  it('la cuenta de eMuwarez va en la cabecera, entre el título y «Sincronizar todo»; sin perfil no sale nada', async () => {
    await pagina()
    expect(document.querySelector('[data-testid="cuenta"]')).toBeNull()
    await desmontar()

    cuenta.hayPerfil = true
    await pagina()
    const cabecera = document.querySelector('.panel-cabecera')!
    expect([...cabecera.children].map(c => c.className || c.getAttribute('data-testid')))
      .toEqual(['page-title', 'cuenta', 'panel-sincronizar'])
    // «Sincronizar todo» y la línea de la última sincronización, juntos a la derecha.
    expect(cabecera.querySelector('.panel-sincronizar')!.textContent).toContain('Sincronizar todo')
    expect(cabecera.querySelector('.panel-sincronizacion')!.textContent).toBe('Aún no se ha sincronizado')
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
    await esperar(() => banda().querySelectorAll('.panel-aviso').length === 3)

    const avisos = [...banda().querySelectorAll('.panel-aviso')].map(a => a.textContent)
    expect(avisos[0]).toContain('Radarr up no responde')
    expect(avisos[0]).toContain('Biblioteca de hace 26 h · se sincroniza sola al volver')
    expect(avisos[1]).toContain('Subida fallida · Youjo Senki S01E12')
    expect(avisos[1]).toContain('Duplicado en eMuwarez')
    expect(avisos[2]).toContain('Versión nueva 0.14.1 publicada')
    expect(texto()).not.toContain('Configurado')
    expect(banda().querySelector('h2')!.textContent).toBe('Necesita atención 3')
    expect(banda().querySelector('button')).toBeNull()

    // «Ver motivo» abre esa subida en Subidas.
    const ver = [...banda().querySelectorAll('a[href]')].find(l => l.textContent === 'Ver motivo')!
    expect(ver.getAttribute('href')).toBe('/uploads/9')
    await pulsar(ver)
    expect(sessionStorage.getItem('emuwarez_open_upload')).toBe('9')
    expect(navegar).toHaveBeenCalledWith('uploads')
  })

  it('con más de cuatro avisos enseña cuatro y «y N más» despliega el resto', async () => {
    vi.mocked(getDashboardSummary).mockResolvedValue(resumen({
      instancias_caidas: [
        { id: 3, nombre: 'Radarr up', tipo: 'radarr', ultima_sincronizacion: null },
        { id: 4, nombre: 'Sonarr up', tipo: 'sonarr', ultima_sincronizacion: null },
      ],
    }))
    vi.mocked(getUploads).mockResolvedValue([1, 2, 3].map(n =>
      trabajo({ id: 20 + n, status: 'failed', title: `Fallida ${n}`, error_message: 'Motivo', finished_at: new Date().toISOString() })))
    vi.mocked(getVersionInfo).mockResolvedValue({ version: '0.14.0', estado: 'hay_novedad', ultima: { version: '0.14.1' } })
    await pagina()
    await esperar(() => banda().querySelector('.panel-atencion-mas'))

    expect(banda().querySelectorAll('.panel-aviso')).toHaveLength(4)
    const mas = banda().querySelector('.panel-atencion-mas')!
    expect(mas.textContent).toBe('y 2 más')
    await pulsar(mas)
    expect(banda().querySelectorAll('.panel-aviso')).toHaveLength(6)
    expect(banda().querySelector('.panel-atencion-mas')!.textContent).toBe('Ver menos')
  })

  describe('Recientes', () => {
    const hace = (dias: number) => new Date(Date.now() - dias * 24 * 3600e3).toISOString()
    const terminada = (id: number, status: string, dias: number, extra: Partial<UploadJob> = {}) =>
      trabajo({ id, status, title: `Subida ${id}`, finished_at: hace(dias), ...extra })
    const recientes = () => carril('En curso').querySelector('ul[aria-labelledby]')!

    it('enseña las terminadas de cada estado con su antigüedad, insignia y duración, y cada fila abre su detalle', async () => {
      vi.mocked(getUploads).mockResolvedValue([
        terminada(1, 'completed', 2, { duration_seconds: 260 }),
        terminada(2, 'failed', 1, { error_message: 'Duplicado' }),
        terminada(3, 'cancelled', 4),
      ])
      await pagina()
      await esperar(() => carril('En curso').querySelector('ul[aria-labelledby]'))

      expect(carril('En curso').querySelector('h3')!.textContent).toBe('Recientes')
      expect(recientes().getAttribute('aria-labelledby')).toBe(carril('En curso').querySelector('h3')!.id)
      const filas = [...recientes().querySelectorAll('li')]
      expect(filas.map(f => f.querySelector('.upload-row-title')!.textContent)).toEqual(['Subida 2', 'Subida 1', 'Subida 3'])
      expect(filas.map(f => f.querySelector('.badge')!.textContent)).toEqual(['Fallido', 'Completado', 'Cancelado'])
      expect(filas.map(f => f.querySelector('.panel-fila-tiempo')!.textContent)).toEqual(['hace 1 día', 'hace 2 días', 'hace 4 días'])
      expect(filas[1].querySelector('.panel-fila-duracion')!.textContent).toBe('en 4m 20s')
      expect(filas[0].querySelector('.panel-fila-duracion')).toBeNull()
      expect(filas.every(f => f.querySelector('.panel-poster'))).toBe(true)

      expect(filas.map(f => f.querySelector('a.upload-row')!.getAttribute('href'))).toEqual(['/uploads/2', '/uploads/1', '/uploads/3'])
      await pulsar(filas[1].querySelector('a[href]')!)
      expect(sessionStorage.getItem('emuwarez_open_upload')).toBe('1')
      expect(navegar).toHaveBeenCalledWith('uploads')
    })

    it('una fallida enseña la primera línea de su motivo en la propia fila; las demás, nada', async () => {
      vi.mocked(getUploads).mockResolvedValue([
        terminada(1, 'failed', 1, { error_message: 'Duplicado en eMuwarez\nSegunda línea' }),
        terminada(2, 'completed', 2),
      ])
      await pagina()
      await esperar(() => recientes())
      const motivos = [...recientes().querySelectorAll('li')].map(f => f.querySelector('.panel-fila-motivo')?.textContent ?? null)
      expect(motivos).toEqual(['Duplicado en eMuwarez', null])
    })

    it('sin nada en curso, «Sin subidas en curso» es una línea discreta y Recientes ocupa el carril', async () => {
      vi.mocked(getUploads).mockResolvedValue([terminada(1, 'completed', 1)])
      await pagina()
      await esperar(() => recientes())
      expect(carril('En curso').querySelector('.empty-state')).toBeNull()
      expect(carril('En curso').querySelector('.panel-sin-curso')!.textContent).toBe('Sin subidas en curso')
      expect(carril('En curso').querySelector('.panel-carril-nota')).toBeNull()
    })

    it('con una en curso, esa va primero y Recientes detrás, sin repetirla', async () => {
      vi.mocked(getUploads).mockResolvedValue([
        terminada(1, 'completed', 1),
        trabajo({ id: 2, status: 'running', title: 'En marcha', progress_phase: 'hash_torrent', started_at: new Date().toISOString() }),
      ])
      await pagina()
      await esperar(() => recientes())
      const cuerpo = carril('En curso')
      expect([...cuerpo.querySelectorAll('.upload-row-title')].map(t => t.textContent)).toEqual(['En marcha', 'Subida 1'])
      expect(cuerpo.querySelector('.panel-sin-curso')).toBeNull()
      expect(cuerpo.querySelectorAll('ul li')).toHaveLength(1)
      expect(cuerpo.querySelector('h3')!.compareDocumentPosition(cuerpo.querySelector('.upload-row')!))
        .toBe(Node.DOCUMENT_POSITION_PRECEDING)
      expect(cuerpo.textContent).toContain('1 subiendo')
    })

    it('sin ninguna subida: el vacío de siempre, sin «Recientes»', async () => {
      await pagina()
      expect(carril('En curso').querySelector('.empty-state')).not.toBeNull()
      expect(carril('En curso').querySelector('h3')).toBeNull()
      expect(carril('En curso').querySelector('ul')).toBeNull()
    })

    it('enseña como mucho cinco y sin los fallos ya reintentados', async () => {
      vi.mocked(getUploads).mockResolvedValue([
        ...[1, 2, 3, 4, 5, 6].map(n => terminada(n, 'completed', n)),
        terminada(7, 'failed', 0.5),
        terminada(8, 'completed', 0.2, { retry_of_job_id: 7 }),
      ])
      await pagina()
      await esperar(() => recientes())
      expect([...recientes().querySelectorAll('.upload-row-title')].map(t => t.textContent))
        .toEqual(['Subida 8', 'Subida 1', 'Subida 2', 'Subida 3', 'Subida 4'])
    })
  })

  it('un solo aviso ocupa todo el ancho de la banda, con su acción a la derecha', async () => {
    vi.mocked(getVersionInfo).mockResolvedValue({ version: '0.14.0', estado: 'hay_novedad', ultima: { version: '0.14.1' } })
    await pagina()
    await esperar(() => banda().querySelector('.panel-aviso'))
    const avisos = [...banda().querySelectorAll('.panel-aviso')]
    expect(avisos).toHaveLength(1)
    expect(avisos[0].classList.contains('panel-aviso-ancho')).toBe(true)
  })

  it('con un número impar de avisos solo el último ocupa todo el ancho', async () => {
    vi.mocked(getDashboardSummary).mockResolvedValue(resumen({
      instancias_caidas: [{ id: 3, nombre: 'Radarr up', tipo: 'radarr', ultima_sincronizacion: null }],
    }))
    vi.mocked(getUploads).mockResolvedValue([
      trabajo({ id: 9, status: 'failed', title: 'Fallida', error_message: 'Motivo', finished_at: new Date().toISOString() }),
    ])
    vi.mocked(getVersionInfo).mockResolvedValue({ version: '0.14.0', estado: 'hay_novedad', ultima: { version: '0.14.1' } })
    await pagina()
    await esperar(() => banda().querySelectorAll('.panel-aviso').length === 3)
    expect([...banda().querySelectorAll('.panel-aviso')].map(a => a.classList.contains('panel-aviso-ancho')))
      .toEqual([false, false, true])
  })

  it('con un número par de avisos ninguno ocupa todo el ancho', async () => {
    vi.mocked(getDashboardSummary).mockResolvedValue(resumen({
      instancias_caidas: [{ id: 3, nombre: 'Radarr up', tipo: 'radarr', ultima_sincronizacion: null }],
    }))
    vi.mocked(getVersionInfo).mockResolvedValue({ version: '0.14.0', estado: 'hay_novedad', ultima: { version: '0.14.1' } })
    await pagina()
    await esperar(() => banda().querySelectorAll('.panel-aviso').length === 2)
    expect(banda().querySelector('.panel-aviso-ancho')).toBeNull()
  })

  describe('grupo de release e idiomas en «Listo para subir»', () => {
    const meta = (i: number) => filas('Listo para subir')[i].querySelector('.panel-item-meta')!

    it('con grupo e idiomas: el grupo en su chip, el audio, los subtítulos y «Ver petición», en la segunda línea', async () => {
      vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [
        rec({ id: 1, rec_request_id: 11, rec_points: 9, content_name: 'Con datos', release_group: 'Ryodan',
          audio_languages: ['ESP', 'ING'], subtitle_languages: ['ESP'], resolution: '1080p', source: 'WEB-DL', size_bytes: 6 * 1024 ** 3 }),
      ] })
      await pagina()
      const fila = filas('Listo para subir')[0]
      // La primera línea sigue siendo la de siempre; el grupo no se mezcla con ella.
      expect(fila.querySelector('.panel-item-spec')!.textContent).toBe('Película · 1080p WEB-DL · 6,0 GB')
      expect(meta(0).querySelector('.panel-rg')!.textContent).toBe('Grupo de release: Ryodan')
      expect(meta(0).querySelector('.panel-rg-texto')!.textContent).toBe('Ryodan')
      const idiomas = [...meta(0).querySelectorAll('.detcard-plano')].map(p => p.textContent)
      expect(idiomas).toEqual(['Audio: ESP, ING', 'Subtítulos: ESP'])
      expect(meta(0).querySelector('a[href]')!.textContent).toBe('Ver petición')
    })

    it('sin grupo ni idiomas no sale nada en su lugar, solo «Ver petición»', async () => {
      vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [
        rec({ id: 1, rec_request_id: 11, rec_points: 9, release_group: null, audio_languages: [], subtitle_languages: [] }),
        rec({ id: 2, rec_request_id: 12, rec_points: 8, release_group: '  ' }),
      ] })
      await pagina()
      for (const i of [0, 1]) {
        expect(meta(i).querySelector('.panel-rg')).toBeNull()
        expect(meta(i).querySelector('.detcard-plano')).toBeNull()
        expect(meta(i).textContent).toBe('Ver petición')
      }
      expect(texto()).not.toContain('—')
    })

    it('con solo el grupo, o solo el audio, enseña únicamente lo que hay', async () => {
      vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [
        rec({ id: 1, rec_request_id: 11, rec_points: 9, release_group: 'Ryodan' }),
        rec({ id: 2, rec_request_id: 12, rec_points: 8, audio_languages: ['ESP'] }),
      ] })
      await pagina()
      expect(meta(0).querySelector('.panel-rg')).not.toBeNull()
      expect(meta(0).querySelector('.detcard-plano')).toBeNull()
      expect(meta(1).querySelector('.panel-rg')).toBeNull()
      expect([...meta(1).querySelectorAll('.detcard-plano')].map(p => p.textContent)).toEqual(['Audio: ESP'])
    })

    it('una idea sin petición ni datos no pinta la segunda línea; con grupo, sí', async () => {
      vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [
        rec({ id: 20, rec_group: 2, content_name: 'Sin datos (2001)' }),
        rec({ id: 21, rec_group: 2, content_name: 'Con grupo (2002)', release_group: 'Ryodan' }),
      ] })
      await pagina()
      const ideas = [...document.querySelectorAll('details.panel-mas .panel-item')]
      expect(ideas[0].querySelector('.panel-item-meta')).toBeNull()
      expect(ideas[1].querySelector('.panel-rg-texto')!.textContent).toBe('Ryodan')
    })
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
    const verPeticion = [...fila.querySelectorAll('a[href]')].find(l => l.textContent === 'Ver petición')!
    expect(verPeticion.getAttribute('href')).toBe('/requests/77')
    expect(fila.querySelector('a.panel-item-titulo')!.getAttribute('href')).toBe('/library/5')
    await pulsar(verPeticion)
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

  it('«Mejoras posibles» (grupo 4) enseña lo que aporta tu copia y «Subir» abre el asistente sin petición', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [
      rec({ id: 40, rec_group: 4, content_name: 'Mejorable (2003)',
        rec_aportes: [{ dim: 'resolucion', detail: '2160p' }, { dim: 'idioma', detail: 'ESP' }] }),
    ] })
    await pagina()
    const mas = document.querySelector('details.panel-mas')!
    expect(mas.textContent).toContain('Mejoras posibles')
    const fila = [...mas.querySelectorAll('.panel-item')].find(f => f.textContent!.includes('Mejorable (2003)'))!
    expect([...fila.querySelectorAll('.panel-aporte')].map(a => a.textContent)).toEqual(['Resolución 2160p', 'Castellano'])
    await pulsar(botonDe(fila, 'Subir'))
    await esperar(() => document.querySelector('[data-testid="asistente"]'))
    expect(JSON.parse(document.querySelector('[data-testid="asistente"]')!.textContent!))
      .toEqual({ id: 40, preselect: null, requestId: null })
  })

  it('una tanda de 10: «En curso» enseña 6 filas vivas, la que sube primero, y «+4 en cola»', async () => {
    vi.mocked(getUploads).mockResolvedValue([
      ...Array.from({ length: 9 }, (_, i) => trabajo({ id: 20 + i, status: 'queued', title: `Capítulo ${i + 2}`, queue_position: i + 1 })),
      trabajo({ id: 10, status: 'running', title: 'Capítulo 1', started_at: new Date().toISOString() }),
    ])
    await pagina()
    await esperar(() => carril('En curso').querySelectorAll('.upload-row').length > 0)

    const subidas = [...carril('En curso').querySelectorAll('.upload-row-title')].map(t => t.textContent)
    expect(subidas).toEqual(['Capítulo 1', 'Capítulo 2', 'Capítulo 3', 'Capítulo 4', 'Capítulo 5', 'Capítulo 6'])
    // La nota sigue contando todas; la línea de debajo, las que no caben.
    expect(carril('En curso').textContent).toContain('1 subiendo · 9 en cola')
    const mas = carril('En curso').querySelector('.panel-en-curso-mas')!
    expect(mas.textContent).toBe('+4 en cola · Ver todas las subidas')
    // El enlace no se repite al pie.
    expect(carril('En curso').querySelector('.panel-pie')).toBeNull()
    await pulsar(mas.querySelector('a[href]')!)
    expect(navegar).toHaveBeenCalledWith('uploads')
  })

  it('con 6 vivas o menos no hay línea «+N en cola»', async () => {
    vi.mocked(getUploads).mockResolvedValue(
      Array.from({ length: 6 }, (_, i) => trabajo({ id: 20 + i, status: 'queued', title: `Capítulo ${i + 1}`, queue_position: i + 1 })))
    await pagina()
    await esperar(() => carril('En curso').querySelectorAll('.upload-row').length === 6)
    expect(carril('En curso').querySelector('.panel-en-curso-mas')).toBeNull()
  })

  it('«Ver todas las subidas» abre Subidas', async () => {
    await pagina()
    await pulsar([...carril('En curso').querySelectorAll('a[href]')].find(l => l.textContent === 'Ver todas las subidas'))
    expect(navegar).toHaveBeenCalledWith('uploads')
  })

  it('la cabecera lleva un solo botón de sincronizar', async () => {
    await pagina()
    expect([...document.querySelectorAll('button')].filter(b => b.textContent!.includes('↻')).map(b => b.textContent))
      .toEqual(['↻ Sincronizar todo'])
  })
})

describe('el tope de filas vivas de «En curso»', () => {
  const fila = (id: number, status: string, yendose = false) => ({ job: trabajo({ id, status }), yendose })

  it('las que se despiden no cuentan ni se esconden', () => {
    const vivas = Array.from({ length: 8 }, (_, i) => fila(i + 1, i === 0 ? 'running' : 'queued'))
    const despidiendose = [fila(50, 'completed'), fila(51, 'failed', true)]
    const { visibles, ocultas } = recortarEnCurso([...vivas, ...despidiendose])
    expect(visibles.map(f => f.job.id)).toEqual([1, 2, 3, 4, 5, 6, 50, 51])
    expect(ocultas.map(f => f.job.id)).toEqual([7, 8])
  })

  it('sin pasarse del tope, todas tal cual', () => {
    const filas = [fila(1, 'running'), fila(2, 'completed')]
    expect(recortarEnCurso(filas)).toEqual({ visibles: filas, ocultas: [] })
  })
})

// ── «Subir seleccionadas» ───────────────────────────────────────────────────────────────────────────────────────

describe('«Subir seleccionadas» en «Listo para subir»', () => {
  const ficha = (id: number, extra: Partial<LibraryItemResponse>) => ({
    id, item_type: 'movie', title: `Ficha ${id}`, year: 2016, local_status: 'Disponible', has_spanish_ok: 1,
    resolution: '1080p', source: 'WEB-DL', video_codec: 'x264', ...extra,
  }) as LibraryItemResponse
  // La serie 5 (Lost) con sus temporadas 51 y 55, su capítulo 66; la temporada 77 de otra (Fargo); la película 20.
  const FICHAS: Record<number, LibraryItemResponse> = {
    5: ficha(5, { item_type: 'series', title: 'Lost' }),
    51: ficha(51, { item_type: 'season', title: 'Lost - Temporada 1', parent_id: 5, season_number: 1 }),
    55: ficha(55, { item_type: 'season', title: 'Lost - Temporada 2', parent_id: 5, season_number: 2 }),
    66: ficha(66, { item_type: 'episode', title: 'Lost S01E12', season_number: 1, episode_number: 12 }),
    77: ficha(77, { item_type: 'season', title: 'Fargo - Temporada 1', parent_id: 7, season_number: 1 }),
    20: ficha(20, { title: 'Única', source: 'BluRay' }),
  }
  const ENTORNO = { ready: true, checks: [{ id: 'emuwarez', label: 'eMuwarez responde', status: 'ok' as const, message: '' }] }

  const casillas = () => [...document.querySelectorAll<HTMLInputElement>('.panel-item input[type="checkbox"]')]
  const casilla = (titulo: string) => document.querySelector<HTMLInputElement>(`input[aria-label="Seleccionar «${titulo}»"]`)!
  const seleccionar = () => pulsar(botonDe(carril('Listo para subir'), 'Seleccionar'))
  const titulosLote = () => [...document.querySelectorAll('.lote-fila-titulo')].map(e => e.textContent)
  const peticionesLote = () => [...document.querySelectorAll('.lote-fila-peticion')].map(e => e.textContent)

  beforeEach(() => {
    vi.mocked(getLibraryItem).mockImplementation(async id => FICHAS[id] ?? fichaDe(id))
    vi.mocked(getLibrary).mockImplementation(async q => {
      const items = q!.parent_id === 5 ? [FICHAS[55], FICHAS[51]] : []
      return { items, total: items.length } as never
    })
    vi.mocked(runUploadChecks).mockImplementation(async (id, scope) => (scope === 'environment'
      ? ENTORNO
      : { ready: true, nombre: `Pack ${id}`, checks: [{ id: 'accesible', label: 'Fichero accesible', status: 'ok' as const, message: '' }] }))
    vi.mocked(getNomenclatureFields).mockImplementation(async id => ({
      fields: { source: 'BluRay', provider: null }, torrent_name: `Nombre ${id}`, internal_mkv_title: '', blocked: false,
    }) as never)
    vi.mocked(getEmuComparison).mockResolvedValue({ available: true, message: null, matches: [] })
    vi.mocked(queueLote).mockImplementation(async elementos => ({
      lote_id: '0123456789ab', encolados: elementos.length, saltados: 0,
      resultados: elementos.map((e, i) => ({ item_id: e.item_id, status: 'queued' as const, job_id: 100 + i, errors: [] })),
    }))
  })

  const PETICION_TEMPORADA = rec({
    id: 5, library_target_id: 55, item_type: 'season', season_number: 2, rec_request_id: 77, rec_points: 500,
    content_name: 'Lost (2016) - Temporada 2',
  })
  const PETICION_CAPITULO = rec({
    id: 5, library_target_id: 66, item_type: 'episode', season_number: 1, episode_number: 12, rec_request_id: 78,
    rec_points: 400, content_name: 'Lost (2016) - S01E12',
  })
  const UNICA = rec({ id: 20, rec_group: 2, content_name: 'Única (2016)' })

  it('«Seleccionar» pone casillas en las peticiones y en las otras ideas, no en las faltantes', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [
      PETICION_TEMPORADA, UNICA,
      rec({ id: 30, rec_group: 3, content_name: 'Faltante (2001)', missing_count: 2 }),
      rec({ id: 40, rec_group: 4, content_name: 'Mejora (2002)' }),
    ] })
    await pagina()
    expect(casillas()).toHaveLength(0)
    expect(document.querySelector('.lote-barra')).toBeNull()
    await seleccionar()
    expect(botonDe(carril('Listo para subir'), 'Seleccionar')!.getAttribute('aria-pressed')).toBe('true')
    expect(casillas().map(c => c.getAttribute('aria-label'))).toEqual([
      'Seleccionar «Lost (2016) - Temporada 2»', 'Seleccionar «Única (2016)»', 'Seleccionar «Mejora (2002)»',
    ])
    expect(texto()).toContain('Marca las peticiones o ideas que quieras subir juntas')
    expect(boton('Subir seleccionadas (0)')!.disabled).toBe(true)
    await pulsar(casilla('Lost (2016) - Temporada 2'))
    await pulsar(casilla('Mejora (2002)'))
    expect(texto()).toContain('2 seleccionadas')
    expect(boton('Subir seleccionadas (2)')!.disabled).toBe(false)
    // Apagarlo quita las casillas y lo marcado.
    await seleccionar()
    expect(casillas()).toHaveLength(0)
    await seleccionar()
    expect(casillas().filter(c => c.checked)).toHaveLength(0)
  })

  it('sube lo marcado como un lote: cada fila con su petición, la de capítulo como ese capítulo, la idea sin petición', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [PETICION_TEMPORADA, PETICION_CAPITULO, UNICA] })
    await pagina()
    await seleccionar()
    await pulsar(casilla('Lost (2016) - Temporada 2'))
    await pulsar(casilla('Lost (2016) - S01E12'))
    await pulsar(casilla('Única (2016)'))
    const cargasAntes = vi.mocked(getDashboardRecommendations).mock.calls.length
    await pulsar(boton('Subir seleccionadas (3)'))
    await esperar(() => document.querySelector('.lote-lista'))
    // La fila real de cada una, como «Subir»: la temporada y el capítulo de la petición, no la serie.
    expect(vi.mocked(getLibraryItem).mock.calls.map(c => c[0])).toEqual([55, 66, 20])
    expect(titulosLote()).toEqual(['Lost (2016) - Temporada 2', 'Lost (2016) - S01E12', 'Única (2016)'])
    expect(peticionesLote()).toEqual(['Petición #77', 'Petición #78'])

    await pulsar(boton('Continuar (3)'))
    await esperar(() => boton('Subir 3') && !boton('Subir 3')!.disabled)
    await pulsar(boton('Subir 3'))
    await esperar(() => texto().includes('3 de 3 encoladas'))
    expect(vi.mocked(queueLote).mock.calls[0][0].map(e => [e.item_id, e.request_item_id])).toEqual([
      [55, 77], [66, 78], [20, undefined],
    ])
    // Encolado: la selección se limpia, el modo se apaga y el Panel se recarga.
    expect(document.querySelector('.lote-barra')).toBeNull()
    expect(casillas()).toHaveLength(0)
    expect(vi.mocked(getDashboardRecommendations).mock.calls.length).toBeGreaterThan(cargasAntes)
    await seleccionar()
    expect(casillas().filter(c => c.checked)).toHaveLength(0)
  })

  it('una petición de serie entera sale como sus temporadas con la petición; dos sobre la misma fila, una con elección', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [
      rec({ id: 5, library_target_id: 5, item_type: 'series', rec_request_id: 90, rec_points: 900, content_name: 'Lost (2016)' }),
      rec({ id: 7, library_target_id: 77, item_type: 'season', season_number: 1, rec_request_id: 80, rec_points: 800, content_name: 'Fargo (2016) - Temporada 1' }),
      rec({ id: 7, library_target_id: 77, item_type: 'season', season_number: 1, rec_request_id: 81, rec_points: 700, content_name: 'Fargo (2016) - Temporada 1 (otra)' }),
    ] })
    await pagina()
    await seleccionar()
    for (const c of casillas()) await pulsar(c)
    expect(texto()).toContain('3 seleccionadas')
    await pulsar(boton('Subir seleccionadas (3)'))
    await esperar(() => document.querySelector('.lote-lista'))
    // La fila 77 se pide una vez aunque la cubran dos peticiones.
    expect(vi.mocked(getLibraryItem).mock.calls.map(c => c[0])).toEqual([5, 77])
    expect(titulosLote()).toEqual(['Lost (2016) - Temporada 1', 'Lost (2016) - Temporada 2', 'Fargo (2016) - Temporada 1'])
    expect(peticionesLote()).toEqual(['Petición #90', 'Petición #90'])
    const select = document.querySelector<HTMLSelectElement>('.lote-fila-peticion-elegir')!
    expect([...select.options].map(o => o.textContent)).toEqual(['Petición #80', 'Petición #81'])
    expect(select.value).toBe('80')
    await elegir(select, '81')

    await pulsar(boton('Continuar (3)'))
    await esperar(() => boton('Subir 3') && !boton('Subir 3')!.disabled)
    await pulsar(boton('Subir 3'))
    await esperar(() => texto().includes('3 de 3 encoladas'))
    expect(vi.mocked(queueLote).mock.calls[0][0].map(e => [e.item_id, e.request_item_id])).toEqual([
      [51, 90], [55, 90], [77, 81],
    ])
  })

  it('si alguna ya no está, lo dice y abre el lote con el resto', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [PETICION_TEMPORADA, UNICA] })
    vi.mocked(getLibraryItem).mockImplementation(async id => {
      if (id === 20) throw new Error('404')
      return FICHAS[id]
    })
    await pagina()
    await seleccionar()
    await pulsar(casilla('Lost (2016) - Temporada 2'))
    await pulsar(casilla('Única (2016)'))
    await pulsar(boton('Subir seleccionadas (2)'))
    await esperar(() => document.querySelector('.lote-lista'))
    expect(document.querySelector('[role="alert"]')!.textContent).toContain('No se pudo abrir «Única (2016)»')
    expect(titulosLote()).toEqual(['Lost (2016) - Temporada 2'])
  })

  it('salir del Panel limpia la selección y quita el modo', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [PETICION_TEMPORADA] })
    await pagina()
    await seleccionar()
    await pulsar(casilla('Lost (2016) - Temporada 2'))
    expect(texto()).toContain('1 seleccionada')
    await act(async () => { fijarVisible(false) })
    await act(async () => { fijarVisible(true) })
    expect(casillas()).toHaveLength(0)
    expect(document.querySelector('.lote-barra')).toBeNull()
    await seleccionar()
    expect(casilla('Lost (2016) - Temporada 2').checked).toBe(false)
  })

  it('salir mientras se piden las fichas no abre el lote al volver', async () => {
    vi.mocked(getDashboardRecommendations).mockResolvedValue({ items: [PETICION_TEMPORADA] })
    let soltar: () => void = () => {}
    vi.mocked(getLibraryItem).mockImplementation(id => new Promise(resolve => { soltar = () => resolve(FICHAS[id]) }))
    await pagina()
    await seleccionar()
    await pulsar(casilla('Lost (2016) - Temporada 2'))
    await pulsar(boton('Subir seleccionadas (1)'))
    await act(async () => { fijarVisible(false) })
    await act(async () => { soltar() })
    await act(async () => { fijarVisible(true) })
    expect(document.querySelector('.lote-lista')).toBeNull()
  })
})
