/**
 * La lógica del Panel: cómo se reparten las recomendaciones en carriles, en qué orden salen las subidas en curso,
 * qué sube a «Necesita atención» y qué dicen las líneas de texto.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DashboardRecommendationItem } from '../../api/dashboard'
import type { UploadJob } from '../../types/api'
import {
  avisosDeAtencion, fallidasRecientes, lineaDeEspecificaciones, lineaSincronizacion, ordenarEnCurso,
  repartirRecomendaciones, textoDeAporte, FALLIDAS_MAX, FALLIDA_VIGENTE_MS,
} from '../hoy'

const rec = (extra: Partial<DashboardRecommendationItem>): DashboardRecommendationItem => ({
  id: 1, rec_group: 1, item_type: 'movie', title: 'T', content_name: 'T', year: null, poster_url: null,
  local_status: null, season_number: null, episode_number: null, size_bytes: null, resolution: null, source: null,
  instance_type: null, instance_id: null, tmdb_id: null, title_slug: null, missing_count: null,
  rec_request_id: null, rec_points: null, ...extra,
})
const job = (extra: Partial<UploadJob>) => ({ id: 1, status: 'queued', ...extra } as UploadJob)

describe('el reparto de las recomendaciones', () => {
  it('separa peticiones, únicos y faltantes sin cambiar el orden que da el servidor', () => {
    const items = [
      rec({ id: 1, rec_group: 1, rec_points: 900 }), rec({ id: 2, rec_group: 1, rec_points: 100 }),
      rec({ id: 3, rec_group: 2 }), rec({ id: 4, rec_group: 3 }), rec({ id: 5, rec_group: 2 }), rec({ id: 6, rec_group: 4 }),
    ]
    const r = repartirRecomendaciones(items)
    expect(r.peticiones.map(i => i.id)).toEqual([1, 2])
    expect(r.unicos.map(i => i.id)).toEqual([3, 5])
    expect(r.faltantes.map(i => i.id)).toEqual([4])
    expect(r.mejoras.map(i => i.id)).toEqual([6])
  })

  it('sin recomendaciones, los tres carriles quedan vacíos', () => {
    expect(repartirRecomendaciones([])).toEqual({ peticiones: [], unicos: [], faltantes: [], mejoras: [] })
  })
})

describe('lo que aporta tu copia', () => {
  it('dice cada aporte en una frase corta', () => {
    expect(textoDeAporte({ dim: 'resolucion', detail: '2160p' })).toBe('Resolución 2160p')
    expect(textoDeAporte({ dim: 'source', detail: 'Remux' })).toBe('Source Remux')
    expect(textoDeAporte({ dim: 'codec', detail: 'HEVC (−1,2 GB)' })).toBe('Códec HEVC (−1,2 GB)')
    expect(textoDeAporte({ dim: 'idioma', detail: 'ESP' })).toBe('Castellano')
    expect(textoDeAporte({ dim: 'otro', detail: 'algo' })).toBe('algo')
  })
})

describe('la línea de especificaciones', () => {
  it('junta tipo, calidad, castellano y tamaño', () => {
    const l = lineaDeEspecificaciones(rec({
      resolution: '1080p', source: 'WEB-DL', has_spanish_audio: 1, has_spanish_subs: 1, size_bytes: 6 * 1024 ** 3,
    }))
    expect(l).toBe('Película · 1080p WEB-DL · castellano · 6,0 GB')
  })

  it('dice dónde está el castellano cuando solo está en un lado', () => {
    expect(lineaDeEspecificaciones(rec({ item_type: 'season', has_spanish_audio: 0, has_spanish_subs: 1 })))
      .toBe('Temporada · castellano (subs)')
    expect(lineaDeEspecificaciones(rec({ item_type: 'season', has_spanish_audio: 1, has_spanish_subs: 0 })))
      .toBe('Temporada · castellano (audio)')
  })

  it('lo que no se sabe no sale: ni raya, ni «desconocido»', () => {
    expect(lineaDeEspecificaciones(rec({ item_type: 'series' }))).toBe('Serie')
  })
})

describe('las subidas en curso', () => {
  it('la que trabaja va primero y la cola en su orden', () => {
    const orden = ordenarEnCurso([
      job({ id: 1, status: 'queued', queue_position: 2 }),
      job({ id: 2, status: 'running' }),
      job({ id: 3, status: 'queued', queue_position: 1 }),
      job({ id: 4, status: 'preparing' }),
    ])
    expect(orden.map(j => j.id)).toEqual([2, 4, 3, 1])
  })

  it('sin subidas, nada', () => {
    expect(ordenarEnCurso([])).toEqual([])
  })
})

describe('las subidas fallidas que avisan', () => {
  const ahora = Date.parse('2026-11-03T12:00:00Z')
  const hace = (ms: number) => new Date(ahora - ms).toISOString()

  it('solo las fallidas, recientes y no reintentadas, la más nueva primero', () => {
    const fallidas = fallidasRecientes([
      job({ id: 1, status: 'failed', finished_at: hace(3_600_000) }),
      job({ id: 2, status: 'failed', finished_at: hace(60_000) }),
      job({ id: 3, status: 'completed', finished_at: hace(1000) }),
      job({ id: 4, status: 'failed', finished_at: hace(FALLIDA_VIGENTE_MS + 1000) }),
      job({ id: 5, status: 'failed', finished_at: hace(2000) }),
      job({ id: 6, status: 'queued', retry_of_job_id: 5 }),
    ], new Set(), ahora)
    expect(fallidas.map(j => j.id)).toEqual([2, 1])
  })

  it('la que aún se está despidiendo en «En curso» no sale dos veces', () => {
    const fallidas = fallidasRecientes([job({ id: 1, status: 'failed', finished_at: hace(1000) })], new Set([1]), ahora)
    expect(fallidas).toEqual([])
  })
})

describe('«Necesita atención»', () => {
  const caida = { id: 7, nombre: 'Radarr up', tipo: 'radarr', ultima_sincronizacion: null }

  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-03T12:00:00Z'))
  })
  afterEach(() => vi.useRealTimers())

  it('nada que avisar, ningún aviso (no hay «todo configurado» en verde)', () => {
    expect(avisosDeAtencion({ instancias: [], fallidas: [], versionNueva: null })).toEqual([])
  })

  it('primero las instancias, luego las subidas fallidas y al final la versión', () => {
    const avisos = avisosDeAtencion({
      instancias: [{ ...caida, ultima_sincronizacion: '2026-11-02T10:00:00Z' }],
      fallidas: [job({ id: 9, status: 'failed', title: 'Youjo Senki S01E12', error_message: 'Duplicado en eMuwarez\ntraza larga' })],
      versionNueva: '0.14.1',
    })
    expect(avisos.map(a => a.tipo)).toEqual(['instancia', 'subida', 'version'])
    expect(avisos[0]).toMatchObject({
      titulo: 'Radarr up no responde',
      detalle: 'Biblioteca de hace 26 h · se sincroniza sola al volver',
    })
    expect(avisos[1]).toMatchObject({ titulo: 'Subida fallida · Youjo Senki S01E12', detalle: 'Duplicado en eMuwarez', jobId: 9 })
    expect(avisos[2]).toMatchObject({ titulo: 'Versión nueva 0.14.1 publicada' })
  })

  it('una instancia que nunca se sincronizó lo dice', () => {
    const [aviso] = avisosDeAtencion({ instancias: [caida], fallidas: [], versionNueva: null })
    expect(aviso.detalle).toContain('Biblioteca sin sincronizar')
  })

  it('una subida fallida sin motivo guardado no inventa uno, y uno largo se corta', () => {
    const avisos = avisosDeAtencion({
      instancias: [], versionNueva: null,
      fallidas: [job({ id: 1, status: 'failed' }), job({ id: 2, status: 'failed', error_message: 'x'.repeat(300) })],
    })
    expect(avisos[0].detalle).toBe('Sin motivo guardado')
    expect(avisos[1].detalle!.length).toBeLessThanOrEqual(90)
    expect(avisos[1].detalle!.endsWith('…')).toBe(true)
  })

  it('lista como mucho las fallidas que caben y dice cuántas quedan fuera', () => {
    const fallidas = Array.from({ length: FALLIDAS_MAX + 2 }, (_, i) => job({ id: i + 1, status: 'failed' }))
    const avisos = avisosDeAtencion({ instancias: [], fallidas, versionNueva: null })
    expect(avisos.filter(a => a.tipo === 'subida')).toHaveLength(FALLIDAS_MAX)
    expect(avisos[avisos.length - 1]).toMatchObject({ tipo: 'mas', titulo: 'y 2 subidas fallidas más' })
  })
})

describe('la línea de sincronización', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 10, 3, 11, 13))   // hora local: martes 3/11/2026 11:13
  })
  afterEach(() => vi.useRealTimers())

  const local = (d: number, h: number, m: number) => new Date(2026, 10, d, h, m).toISOString()

  it('última hace unos minutos y próxima hoy', () => {
    expect(lineaSincronizacion(local(3, 11, 1), local(3, 11, 25), new Date()))
      .toBe('Última sincronización hace 12 min · próxima a las 11:25')
  })

  it('la próxima de mañana lo dice', () => {
    expect(lineaSincronizacion(local(3, 11, 1), local(4, 3, 30), new Date())).toContain('próxima mañana a las 03:30')
  })

  it('una próxima que ya tocaba es «en breve»', () => {
    expect(lineaSincronizacion(local(3, 10, 0), local(3, 11, 0), new Date())).toContain('próxima en breve')
  })

  it('sin sincronizar nunca ni próxima programada, lo dice sin inventar horas', () => {
    expect(lineaSincronizacion(null, null)).toBe('Aún no se ha sincronizado')
  })
})
