import { describe, expect, it } from 'vitest'
import { cuentaAtras, duracion, etiquetaDeEstado, etiquetaIntervalo, tonoDeEstado } from '../tareas'

describe('Tareas: estados', () => {
  it('cada estado conocido tiene su tono y su etiqueta; lo desconocido es neutro y se capitaliza', () => {
    expect(tonoDeEstado('completed')).toBe('ok')
    expect(tonoDeEstado('failed')).toBe('error')
    expect(tonoDeEstado('skipped')).toBe('aviso')
    expect(tonoDeEstado('running')).toBe('curso')
    expect(tonoDeEstado(null)).toBe('neutro')
    expect(tonoDeEstado('otra-cosa')).toBe('neutro')
    expect(etiquetaDeEstado('failed')).toBe('Error')
    expect(etiquetaDeEstado('otra-cosa')).toBe('Otra-cosa')
    expect(etiquetaDeEstado(null)).toBe('Sin ejecutar')
  })
})

describe('Tareas: cuenta atrás', () => {
  const ahora = Date.parse('2026-11-06T10:00:00Z')
  it('escribe horas y minutos, minutos y segundos, o solo segundos', () => {
    expect(cuentaAtras('2026-11-06T12:05:30Z', ahora)).toBe('en 2h 5m')
    expect(cuentaAtras('2026-11-06T10:04:23Z', ahora)).toBe('en 4m 23s')
    expect(cuentaAtras('2026-11-06T10:00:12Z', ahora)).toBe('en 12s')
  })
  it('una hora pasada es «en breve» y sin fecha o con una fecha rota es una raya', () => {
    expect(cuentaAtras('2026-11-06T09:00:00Z', ahora)).toBe('en breve')
    expect(cuentaAtras(null, ahora)).toBe('—')
    expect(cuentaAtras('no es una fecha', ahora)).toBe('—')
  })
})

describe('Tareas: duración de una ejecución', () => {
  it('milisegundos, segundos o minutos según lo que tardó', () => {
    expect(duracion('2026-11-06T10:00:00.000Z', '2026-11-06T10:00:00.850Z')).toBe('850 ms')
    expect(duracion('2026-11-06T10:00:00Z', '2026-11-06T10:00:12Z')).toBe('12 s')
    expect(duracion('2026-11-06T10:00:00Z', '2026-11-06T10:03:05Z')).toBe('3 min 5 s')
  })
  it('sin una de las dos horas, o con el fin antes del inicio, no inventa nada', () => {
    expect(duracion(null, '2026-11-06T10:00:00Z')).toBe('—')
    expect(duracion('2026-11-06T10:00:00Z', null)).toBe('—')
    expect(duracion('2026-11-06T10:00:10Z', '2026-11-06T10:00:00Z')).toBe('—')
  })
})

describe('Tareas: intervalos', () => {
  it('menos de una hora en minutos y el resto en horas', () => {
    expect(etiquetaIntervalo(30)).toBe('30 min')
    expect(etiquetaIntervalo(60)).toBe('1h')
    expect(etiquetaIntervalo(1440)).toBe('24h')
    expect(etiquetaIntervalo(90)).toBe('1h 30 min')
    expect(etiquetaIntervalo(150)).toBe('2h 30 min')
  })
})
