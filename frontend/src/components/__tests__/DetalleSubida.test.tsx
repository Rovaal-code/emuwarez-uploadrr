// @vitest-environment jsdom
/**
 * El detalle de una subida: una completada abre por el resultado y la línea de tiempo, y una fallida, en curso o
 * cancelada abre por su estado, el motivo y la acción de reintento.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/uploads', () => ({ getUploadJobLogs: vi.fn(async () => ({ job_id: 1, logs: [], total: 0, limit: 0, offset: 0 })) }))
vi.mock('../../api/eventos', () => ({
  suscribirse: vi.fn(() => () => {}), canalVivo: vi.fn(() => true), observarCanal: vi.fn(() => () => {}),
}))

import type { SeedingResponse } from '../../api/seeding'
import type { SeedingEstado } from '../../hooks/useSeeding'
import type { UploadJob, UploadProgressPhase } from '../../types/api'
import { UploadJobDetailPage } from '../UploadJobDetailPage'
import { boton, desmontar, montar, pulsar, texto } from './dom'

const T0 = Date.parse('2026-11-02T10:00:00+00:00')
const hora = (s: number) => new Date(T0 + s * 1000).toISOString()
const fase = (key: string, ini: number, fin: number): UploadProgressPhase =>
  ({ key, label: key, status: 'done', pct: 100, started_at: hora(ini), finished_at: hora(fin) })

const completada: UploadJob = {
  id: 7, status: 'completed', title: 'Cyberpunk', display_title: 'Cyberpunk (2022) - Temporada 2', media_type: 'season',
  result_url: 'https://emu-warez.com/torrents/48213', result_torrent_id: '48213', duration_seconds: 409,
  request_title: 'Petición 5', request_url: 'https://emu-warez.com/requests/5',
  created_at: hora(-20), started_at: hora(0), finished_at: hora(409),
  remux_snapshot: { omitida: 'Ninguno' },
  progress: {
    global_pct: 100,
    phases: [fase('nomenclature', 0, 1), fase('remux', 1, 1), fase('screenshots', 11, 243), fase('hash_torrent', 243, 409)],
  },
  pasos: [{ clave: 'subida', nombre: 'Subir con Uploadrr', estado: 'hecho' }],
}
const fallida: UploadJob = {
  id: 9, status: 'failed', title: 'Película', display_title: 'Película (1993)', media_type: 'movie',
  error_message: 'Error de red al hablar con qBittorrent', created_at: hora(0), finished_at: hora(250), duration_seconds: 250,
  reintento_desde: 'verificacion', reintento_desde_nombre: 'Verificar antes de subir',
  pasos: [
    { clave: 'nomenclatura', nombre: 'Comprobar y poner el nombre', estado: 'hecho' },
    { clave: 'subida', nombre: 'Subir con Uploadrr', estado: 'fallido' },
  ],
  progress: { global_pct: 62, phases: [fase('nomenclature', 0, 2), { ...fase('hash_torrent', 2, 250), status: 'running' }] },
}

const respuesta: SeedingResponse = {
  configurado: true, disponible: true, mensaje: null, actualizado: null,
  items: [{ job_id: 7, estado: 'sembrando', etiqueta: 'Sembrando', ratio: 1.84, subido: 1024, progreso: 1, seeds: 14, peers: 3 }],
}
const seeding: SeedingEstado = { datos: respuesta, cargando: false, cargar: vi.fn() }

const manos = { onBack: vi.fn(), onStart: vi.fn(), onRetry: vi.fn(), onCancel: vi.fn(), onDelete: vi.fn() }
const pagina = (job: UploadJob) => <UploadJobDetailPage job={job} seeding={seeding} {...manos} />

afterEach(desmontar)

describe('detalle de una subida completada', () => {
  it('abre por el resultado: estado en eMuwarez, seeding, datos y acciones', async () => {
    await montar(pagina(completada))
    const estado = document.querySelector('[role="status"]')!
    expect(estado.textContent).toContain('Subido a eMuwarez')
    expect(estado.textContent).toContain('Sembrando en qBittorrent')
    const ver = [...document.querySelectorAll('a')].find(a => a.textContent?.includes('Ver en eMuwarez'))!
    expect(ver.getAttribute('href')).toBe('https://emu-warez.com/torrents/48213')
    expect(boton('Rellenar petición')).toBeDefined()
    expect(boton('Ver registro')).toBeDefined()
    expect(texto()).toContain('Petición 5')
    expect(texto()).toContain('Omitidas (Ninguno)')
    // El enlace a qBittorrent no se ofrece: la app solo conoce la dirección con que ella misma lo alcanza.
    expect(texto()).not.toContain('Abrir en qBittorrent')
  })

  it('«Dónde se fue el tiempo» da la duración de cada fase y dice «omitida» en la que no se hizo', async () => {
    await montar(pagina(completada))
    const bloque = document.querySelector('.dsub-tiempo')!
    expect(bloque.querySelector('h2')!.textContent).toContain('Total')
    expect(bloque.querySelector('h2')!.textContent).toContain('6m 49s')
    const filas = [...bloque.querySelectorAll('li')].map(li => li.textContent)
    expect(filas).toEqual(['Nomenclatura1s', 'Pistasomitida', 'Capturas3m 52s', 'Hash del torrent2m 46s'])
  })

  it('las filas de fases quedan tras «Ver todas las fases»', async () => {
    await montar(pagina(completada))
    expect(document.querySelector('table')).toBeNull()
    const abrir = [...document.querySelectorAll('button')].find(b => b.textContent?.includes('Ver todas las fases'))!
    expect(abrir.getAttribute('aria-expanded')).toBe('false')
    await pulsar(abrir)
    expect(abrir.getAttribute('aria-expanded')).toBe('true')
    expect(document.querySelector('table')!.textContent).toContain('Progreso global')
  })

  it('«Grupo» dice el que lleva el nombre del torrent, y no sale si aún no se sabe', async () => {
    await montar(pagina({ ...completada, nomenclature_snapshot: { release_tag: 'FLUX' } }))
    const dato = [...document.querySelectorAll('.dsub-dato')].find(d => d.querySelector('dt')?.textContent?.startsWith('Grupo'))!
    expect(dato.querySelector('dd')!.textContent).toBe('FLUX')
    await desmontar()
    await montar(pagina(completada))
    expect([...document.querySelectorAll('.dsub-dato dt')].map(dt => dt.textContent)).not.toContain('Grupo')
  })

  it('sin datos de la preparación no dice «Pendiente» en una terminada ni abre un recuadro vacío', async () => {
    await montar(pagina({ ...completada, remux_snapshot: null, nomenclature_snapshot: null, checks_snapshot: null }))
    const consultas = document.querySelector('.dsub-consultas')!
    expect(consultas.textContent).not.toContain('Pendiente')
    expect([...consultas.querySelectorAll('dd')].map(dd => dd.textContent)).toEqual(['Sin datos', 'Sin datos', 'Sin datos'])
    expect(consultas.querySelector('dd button')).toBeNull()
    await desmontar()
    await montar(pagina({ ...fallida, remux_snapshot: null, nomenclature_snapshot: null, checks_snapshot: null }))
    expect([...document.querySelectorAll('.dsub-consultas dd')].map(dd => dd.textContent)).toEqual(['No se llegó', 'No se llegó', 'No se llegó'])
  })

  it('con el total pero sin fases, «Dónde se fue el tiempo» no sale vacío', async () => {
    await montar(pagina({ ...completada, progress: { global_pct: 100, phases: [] } }))
    expect(document.querySelector('.dsub-tiempo')).toBeNull()
  })

  it('sin petición no hay «Rellenar petición»', async () => {
    await montar(pagina({ ...completada, request_title: null, request_url: null }))
    expect(texto()).not.toContain('Rellenar petición')
  })
})

describe('detalle de una subida que no terminó bien', () => {
  it('una fallida abre por el estado y el motivo, con el reintento antes que los datos', async () => {
    await montar(pagina(fallida))
    const estado = document.querySelector('[role="status"]')!
    expect(estado.textContent).toContain('Falló en «Subir con Uploadrr»')
    expect(estado.textContent).toContain('Error de red al hablar con qBittorrent')
    const reintento = [...document.querySelectorAll('button')].find(b => b.textContent?.includes('Reintentar desde «Verificar antes de subir»'))!
    expect(reintento).toBeDefined()
    expect(texto()).toContain('Reintentar desde el principio')
    expect(texto()).toContain('Borrar')
    const datos = document.querySelector('.dsub-datos')!
    expect(reintento.compareDocumentPosition(datos) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await pulsar(reintento)
    expect(manos.onRetry).toHaveBeenCalledWith(fallida, false)
  })

  it('conserva los pasos con nombre y la tabla de fases a la vista', async () => {
    await montar(pagina(fallida))
    expect(document.querySelector('[aria-label="Pasos de la subida"]')!.textContent).toContain('Subir con Uploadrr')
    expect(document.querySelector('table')!.textContent).toContain('Progreso global')
    expect(texto()).not.toContain('Dónde se fue el tiempo')
  })

  it('una en curso dice la fase y se puede cancelar; no ofrece reintento', async () => {
    await montar(pagina({ ...fallida, id: 10, status: 'running', error_message: undefined, finished_at: undefined, started_at: hora(0), pasos: undefined }))
    expect(document.querySelector('[role="status"]')!.textContent).toContain('Subiendo')
    expect(texto()).toContain('Cancelar')
    expect(texto()).not.toContain('Reintentar')
  })

  it('una cancelada ofrece reintentar y borrar', async () => {
    await montar(pagina({ ...fallida, id: 11, status: 'cancelled', error_message: undefined }))
    expect(document.querySelector('[role="status"]')!.textContent).toContain('Subida cancelada')
    expect(texto()).toContain('Reintentar')
    expect(texto()).toContain('Borrar')
  })
})

describe('una subida que es parte de un lote', () => {
  it('dice de cuántas es el lote y «Ver el lote» lo pide con su id', async () => {
    const onVerLote = vi.fn()
    await montar(<UploadJobDetailPage job={{ ...fallida, lote_id: '0123456789ab', lote_total: 4 }} seeding={seeding} {...manos} onVerLote={onVerLote} />)
    expect(document.querySelector('.dsub-lote')!.textContent).toBe('Parte de un lote de 4 · Ver el lote')
    await pulsar(boton('Ver el lote'))
    expect(onVerLote).toHaveBeenCalledWith('0123456789ab')
  })

  it('sin lote, o con un lote que se quedó en uno, no dice nada', async () => {
    await montar(pagina(fallida))
    expect(texto()).not.toContain('Parte de un lote')
    await desmontar()
    await montar(pagina({ ...fallida, lote_id: '0123456789ab', lote_total: 1 }))
    expect(texto()).not.toContain('Parte de un lote')
  })
})
