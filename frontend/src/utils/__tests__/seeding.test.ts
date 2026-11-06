import { describe, expect, it } from 'vitest'
import type { SeedingResponse } from '../../api/seeding'
import { claseSeeding, resumenSeeding, seedingDe, textoSubido } from '../seeding'

const datos = (parcial: Partial<SeedingResponse> = {}): SeedingResponse => ({
  configurado: true, disponible: true, mensaje: null, actualizado: null,
  items: [{ job_id: 1, estado: 'sembrando', etiqueta: 'Sembrando', ratio: 0.5 }], ...parcial,
})

describe('seeding', () => {
  it('cada estado tiene su color y lo desconocido, el neutro', () => {
    expect(claseSeeding('sembrando')).toContain('status-available')
    expect(claseSeeding('faltan_ficheros')).toContain('status-error')
    expect(claseSeeding('error')).toContain('status-error')
    expect(claseSeeding('pausado')).toContain('status-partial')
    expect(claseSeeding('no_encontrado')).toContain('status-unknown')
    expect(claseSeeding('algo_nuevo')).toContain('status-unknown')
  })

  it('seedingDe solo devuelve datos si qBittorrent respondió', () => {
    expect(seedingDe(datos(), 1)?.estado).toBe('sembrando')
    expect(seedingDe(datos(), 2)).toBeUndefined()
    expect(seedingDe(datos({ disponible: false, items: [] }), 1)).toBeUndefined()
    expect(seedingDe(null, 1)).toBeUndefined()
    expect(seedingDe(datos(), undefined)).toBeUndefined()
  })

  it('el ratio va con coma decimal', () => {
    expect(resumenSeeding({ job_id: 1, estado: 'sembrando', etiqueta: 'Sembrando', ratio: 1.5 })).toBe('Sembrando · ratio 1,50')
    expect(resumenSeeding({ job_id: 1, estado: 'no_encontrado', etiqueta: 'No se encuentra' })).toBe('No se encuentra')
  })

  it('sin dato de lo subido sale una raya, no «0 B»', () => {
    expect(textoSubido({ job_id: 1, estado: 'no_encontrado', etiqueta: 'No se encuentra' })).toBe('—')
    expect(textoSubido({ job_id: 1, estado: 'no_encontrado', etiqueta: 'No se encuentra', subido: null })).toBe('—')
  })

  it('cero bytes subidos es un dato, no una raya', () => {
    expect(textoSubido({ job_id: 1, estado: 'pausado', etiqueta: 'Pausado', subido: 0 })).toBe('0 B')
    expect(textoSubido({ job_id: 1, estado: 'pausado', etiqueta: 'Pausado', subido: 1536 })).toBe('1,5 KB')
  })
})
