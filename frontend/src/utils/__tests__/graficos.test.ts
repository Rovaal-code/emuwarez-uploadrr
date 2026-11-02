/**
 * Cálculos de los gráficos de línea de Estadísticas: posiciones, huecos, ticks y el resumen para lectores de pantalla.
 */
import { describe, expect, it } from 'vitest'
import { describirSerie, diaAMs, formatDia, trazar, type Medidas, type PuntoSerie } from '../graficos'

// Recuadro útil de 100 x 100, a partir de (10, 10).
const M: Medidas = { ancho: 120, alto: 120, izquierda: 10, derecha: 10, arriba: 10, abajo: 10 }

const p = (dia: string, valor: number | null): PuntoSerie => ({ dia, valor })

describe('fechas', () => {
  it('formatDia pasa de ISO a dd/mm/aaaa, o dd/mm', () => {
    expect(formatDia('2026-11-02')).toBe('02/11/2026')
    expect(formatDia('2026-11-02', true)).toBe('02/11')
  })

  it('diaAMs cuenta días enteros aunque cambie la hora', () => {
    expect(diaAMs('2026-03-30') - diaAMs('2026-03-28')).toBe(2 * 86_400_000)
  })
})

describe('trazar', () => {
  it('sin ningún valor no dibuja nada', () => {
    expect(trazar([[p('2026-11-01', null)]], M)).toEqual({ lineas: [{ camino: '', puntos: [] }], ticksY: [], ticksX: [] })
    expect(trazar([], M)).toEqual({ lineas: [], ticksY: [], ticksX: [] })
  })

  it('el eje X es el tiempo: un día sin instantánea deja hueco', () => {
    const t = trazar([[p('2026-11-01', 1), p('2026-11-02', 2), p('2026-11-05', 3)]], M)
    expect(t.lineas[0].puntos.map(q => q.x)).toEqual([10, 35, 110])
  })

  it('el valor mayor queda arriba y el menor abajo, con margen respecto al borde', () => {
    const t = trazar([[p('2026-11-01', 0), p('2026-11-02', 10)]], M)
    const [bajo, alto] = t.lineas[0].puntos
    expect(alto.y).toBeLessThan(bajo.y)
    expect(alto.y).toBeGreaterThan(10)   // no toca el borde de arriba
    expect(bajo.y).toBeLessThan(110)     // ni el de abajo
  })

  it('desdeCero parte de 0 en el borde de abajo', () => {
    const t = trazar([[p('2026-11-01', 2), p('2026-11-02', 4)]], M, true)
    expect(t.ticksY.map(k => k.valor)).toEqual([0, 2, 4])
    expect(t.ticksY[0].y).toBe(110)
  })

  it('una serie plana no divide por cero y se pinta a media altura con un solo tick', () => {
    const t = trazar([[p('2026-11-01', 5), p('2026-11-02', 5)]], M)
    expect(t.lineas[0].puntos[0].y).toBe(60)
    expect(t.ticksY.map(k => k.valor)).toEqual([5])
    expect(trazar([[p('2026-11-01', 0)]], M).lineas[0].puntos[0].y).toBe(60)
  })

  it('un solo día se centra', () => {
    const t = trazar([[p('2026-11-01', 3)]], M)
    expect(t.lineas[0].puntos[0].x).toBe(60)
    expect(t.lineas[0].camino).toBe('M60 60')
    expect(t.ticksX).toEqual([{ dia: '2026-11-01', x: 60 }])
  })

  it('un valor null corta la línea en dos trazos', () => {
    const t = trazar([[p('2026-11-01', 1), p('2026-11-02', 2), p('2026-11-03', null), p('2026-11-04', 3), p('2026-11-05', 4)]], M)
    expect(t.lineas[0].camino.match(/M/g)).toHaveLength(2)
    expect(t.lineas[0].puntos).toHaveLength(4)
  })

  it('varias series comparten escala y fechas', () => {
    const t = trazar([[p('2026-11-01', 100), p('2026-11-03', 200)], [p('2026-11-01', 0), p('2026-11-03', 50)]], M)
    expect(t.lineas[1].puntos[0].y).toBeGreaterThan(t.lineas[0].puntos[0].y)
    expect(t.ticksY.map(k => k.valor)).toEqual([0, 100, 200])
  })

  it('los ticks del eje X son primero, medio y último', () => {
    const dias = ['2026-11-01', '2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05']
    expect(trazar([dias.map(d => p(d, 1))], M).ticksX.map(k => k.dia)).toEqual(['2026-11-01', '2026-11-03', '2026-11-05'])
    expect(trazar([dias.slice(0, 2).map(d => p(d, 1))], M).ticksX.map(k => k.dia)).toEqual(['2026-11-01', '2026-11-02'])
  })
})

describe('describirSerie', () => {
  const f = (n: number) => String(n)

  it('resume el primer y el último valor, el rango y los días con datos', () => {
    const texto = describirSerie('Ratio', [p('2026-10-01', 4), p('2026-10-02', null), p('2026-10-10', 6), p('2026-10-30', 5)], f)
    expect(texto).toBe('Ratio: de 4 el 01/10/2026 a 5 el 30/10/2026; mínimo 4, máximo 6; 3 días con datos.')
  })

  it('con un solo día lo dice en singular', () => {
    expect(describirSerie('Bonus', [p('2026-10-01', 7)], f)).toBe('Bonus: 7 el 01/10/2026; 1 día con datos.')
  })

  it('sin datos lo dice', () => {
    expect(describirSerie('H&R', [p('2026-10-01', null)], f)).toBe('H&R: sin datos en este rango.')
    expect(describirSerie('H&R', [], f)).toBe('H&R: sin datos en este rango.')
  })
})
