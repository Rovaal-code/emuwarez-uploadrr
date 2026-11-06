/**
 * Formateo de tamaños y fechas.
 *
 * El caso interesante es `parseServerDate`: el backend manda unas marcas de
 * tiempo con zona horaria (ISO) y otras sin ella (las de CURRENT_TIMESTAMP de
 * SQLite). El navegador interpreta una cadena SIN zona como hora LOCAL, así
 * que sin este arreglo una subida hecha hace un minuto se enseñaba con dos
 * horas de desfase en verano.
 */
import { describe, it, expect } from 'vitest'
import { formatBytes, formatNumero, parseServerDate, formatDate, timeAgo } from '../format'

describe('tamaños', () => {
  it('un tamaño vacío o cero es una raya, no "0 B"', () => {
    expect(formatBytes(null)).toBe('—')
    expect(formatBytes(undefined)).toBe('—')
    expect(formatBytes(0)).toBe('—')
  })

  it('escala hasta terabytes', () => {
    expect(formatBytes(500)).toBe('500,0 B')
    expect(formatBytes(1024)).toBe('1,0 KB')
    expect(formatBytes(1024 ** 3)).toBe('1,0 GB')
    expect(formatBytes(1024 ** 4)).toBe('1,0 TB')
  })

  it('no se pasa de la unidad más grande', () => {
    expect(formatBytes(1024 ** 5)).toContain('TB')
  })

  it('un tamaño típico de película', () => {
    expect(formatBytes(8_589_934_592)).toBe('8,0 GB')
  })

  it('el decimal va con coma, como el resto de cifras de la app', () => {
    expect(formatBytes(1.5 * 1024 ** 3)).toBe('1,5 GB')
  })
})

describe('cifras', () => {
  it('agrupa los miles con punto y deja sin agrupar las de cuatro cifras', () => {
    expect(formatNumero(51718)).toBe('51.718')
    expect(formatNumero(9631)).toBe('9631')
    expect(formatNumero(1234567)).toBe('1.234.567')
  })

  it('los decimales van con coma y con los que se pidan', () => {
    expect(formatNumero(19.6, 1)).toBe('19,6')
    expect(formatNumero(2, 1)).toBe('2,0')
  })

  it('sin número es una raya', () => {
    expect(formatNumero(null)).toBe('—')
    expect(formatNumero(undefined)).toBe('—')
    expect(formatNumero(Number.NaN)).toBe('—')
  })
})

describe('marcas de tiempo del servidor', () => {
  it('una fecha SIN zona se interpreta como UTC, no como hora local', () => {
    // Este es el fallo que arregla la función: sin la 'Z', el navegador la
    // habría leído como local y la habría desplazado.
    const d = parseServerDate('2026-08-02 10:30:00')
    expect(d.toISOString()).toBe('2026-08-02T10:30:00.000Z')
  })

  it('una fecha CON zona se respeta tal cual', () => {
    expect(parseServerDate('2026-08-02T10:30:00Z').toISOString())
      .toBe('2026-08-02T10:30:00.000Z')
    expect(parseServerDate('2026-08-02T12:30:00+02:00').toISOString())
      .toBe('2026-08-02T10:30:00.000Z')
  })

  it('las dos formas del backend dan el MISMO instante', () => {
    expect(parseServerDate('2026-08-02 10:30:00').getTime())
      .toBe(parseServerDate('2026-08-02T10:30:00Z').getTime())
  })

  it('sin fecha, una raya', () => {
    expect(formatDate(null)).toBe('—')
    expect(formatDate(undefined)).toBe('—')
    expect(formatDate('')).toBe('—')
  })
})

describe('hace cuánto', () => {
  it('sin fecha, una raya', () => {
    expect(timeAgo(null)).toBe('—')
  })

  it('algo recién hecho no se describe en el futuro', () => {
    const hace30s = new Date(Date.now() - 30_000).toISOString()
    expect(timeAgo(hace30s)).not.toContain('-')
  })
})
