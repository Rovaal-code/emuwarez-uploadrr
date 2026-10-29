/**
 * El estado de una subida tal como lo lee la interfaz.
 *
 * Aquí vive lo que decide qué se enseña mientras un trabajo corre y cuál de
 * varios intentos representa "el estado actual" de ese contenido. Dos cosas
 * de estas ya han fallado en producción: las fases que el frontend no conocía
 * (enseñaba su clave interna cruda) y la cadena de reintentos.
 */
import { describe, it, expect } from 'vitest'
import {
  latestInChain, phaseLabel, formatSecondsHM, currentPhaseInfo,
  ACTIVE_JOB_STATUSES, statusLabel,
} from '../uploadStatus'
import type { UploadJob, UploadProgressPhase } from '../../types/api'

const job = (extra: Partial<UploadJob> = {}): UploadJob =>
  ({ id: 1, status: 'completed', title: 'X', ...extra }) as UploadJob

// El tipo real exige `pct` en cada fase y `global_pct` en el conjunto; se
// construyen completos para que el analizador de tipos siga sirviendo de red
// también dentro de los tests.
const fase = (key: string, status: UploadProgressPhase['status']): UploadProgressPhase =>
  ({ key, label: key, status, pct: status === 'done' ? 100 : 0 })

const conFases = (...fases: UploadProgressPhase[]): Partial<UploadJob> =>
  ({ progress: { phases: fases, global_pct: 0 } })

describe('la punta de una cadena de reintentos', () => {
  it('sin trabajos, no hay punta', () => {
    expect(latestInChain([])).toBeNull()
  })

  it('con uno solo, es ese', () => {
    expect(latestInChain([job({ id: 7 })])?.id).toBe(7)
  })

  it('es el que nadie reintentó, no el último de la lista', () => {
    // Llegan desordenados a propósito: el orden del array no decide.
    const jobs = [
      job({ id: 3, retry_of_job_id: 2 }),
      job({ id: 1 }),
      job({ id: 2, retry_of_job_id: 1 }),
    ]
    expect(latestInChain(jobs)?.id).toBe(3)
  })

  it('con dos cadenas distintas devuelve una punta, no una mezcla', () => {
    const jobs = [job({ id: 1 }), job({ id: 5 })]
    expect([1, 5]).toContain(latestInChain(jobs)?.id)
  })
})

describe('las etiquetas de fase', () => {
  it('sin fase, la raya de "sin dato" de toda la app', () => {
    expect(phaseLabel(null)).toBe('—')
    expect(phaseLabel(undefined)).toBe('—')
  })

  it('traduce las fases del backend', () => {
    // Estas cuatro faltaban y se enseñaban en crudo (hallazgo 5.2).
    expect(phaseLabel('screenshots')).not.toBe('screenshots')
    expect(phaseLabel('hash_torrent')).not.toBe('hash_torrent')
    expect(phaseLabel('uploading_emu')).not.toBe('uploading_emu')
    expect(phaseLabel('qbittorrent_add')).not.toBe('qbittorrent_add')
  })

  it('una fase desconocida se devuelve tal cual, sin romper', () => {
    expect(phaseLabel('fase_del_futuro')).toBe('fase_del_futuro')
  })

  it('"En progreso" NO se llama igual que la subida real a eMuwarez', () => {
    // Si coincidieran, un trabajo atascado parecería estar subiendo.
    expect(phaseLabel('running')).not.toBe(phaseLabel('uploading_emu'))
  })
})

describe('la fase en curso', () => {
  it('sin progreso todavía, null (quien llama cae en phaseLabel)', () => {
    expect(currentPhaseInfo(job())).toBeNull()
    expect(currentPhaseInfo(job(conFases()))).toBeNull()
  })

  it('encuentra la que está corriendo y su posición', () => {
    const j = job(conFases(
      fase('nomenclature', 'done'),
      fase('remux', 'running'),
      fase('screenshots', 'pending'),
    ))
    const info = currentPhaseInfo(j)
    expect(info?.counterText).toBe('2/3')
    expect(info?.label).toContain('Reordenando')
  })

  it('si ninguna corre, null en vez de inventarse una', () => {
    const j = job(conFases(fase('remux', 'done')))
    expect(currentPhaseInfo(j)).toBeNull()
  })
})

describe('el tiempo transcurrido', () => {
  it('menos de un minuto, en segundos', () => {
    expect(formatSecondsHM(0)).toBe('0s')
    expect(formatSecondsHM(59)).toBe('59s')
  })

  it('minutos y segundos', () => {
    expect(formatSecondsHM(60)).toBe('1m 0s')
    expect(formatSecondsHM(125)).toBe('2m 5s')
  })

  it('a partir de una hora, horas y minutos', () => {
    expect(formatSecondsHM(3600)).toBe('1h 0m')
    expect(formatSecondsHM(3900)).toBe('1h 5m')
  })

  it('un negativo no produce un tiempo negativo', () => {
    // Pasa de verdad: el reloj del servidor y el del navegador no van iguales.
    expect(formatSecondsHM(-30)).toBe('0s')
  })
})

describe('el vocabulario de estados', () => {
  it('los activos son los cuatro del backend', () => {
    expect(ACTIVE_JOB_STATUSES).toEqual(new Set(['queued', 'staging', 'preparing', 'running']))
  })

  it('todo estado conocido tiene etiqueta en español', () => {
    for (const s of ['queued', 'staging', 'preparing', 'running', 'completed', 'failed', 'cancelled']) {
      expect(statusLabel(s)).toBeTruthy()
      expect(statusLabel(s)).not.toBe(s)
    }
  })
})
