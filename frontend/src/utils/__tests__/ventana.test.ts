/**
 * Qué filas pinta la lista de Biblioteca.
 *
 * Pintarlas todas costaba casi 3 GB con 15.900 archivos y dos filtros (8.756
 * filas, 667.000 nodos). Lo que importa aquí es que se pinte poco, que no falte
 * nada de lo que se ve, y que los huecos midan lo que medirían las filas: si no,
 * la barra de scroll mentiría sobre el largo de la lista.
 */
import { describe, it, expect } from 'vitest'
import { inicios, filaEn, planVentana, type Tramo } from '../ventana'

const filas = (tramos: Tramo[]) => tramos.flatMap(t => (t.tipo === 'fila' ? [t.indice] : []))
const altoTotal = (tramos: Tramo[], alturas: number[]) =>
  tramos.reduce((s, t) => s + (t.tipo === 'hueco' ? t.alto : alturas[t.indice]), 0)

describe('inicios y filaEn', () => {
  it('cada fila empieza donde acaban las anteriores', () => {
    expect(inicios([10, 20, 30])).toEqual([0, 10, 30, 60])
  })

  it('encuentra la fila que ocupa una altura', () => {
    const ini = inicios([10, 20, 30])
    expect(filaEn(ini, 0)).toBe(0)
    expect(filaEn(ini, 9)).toBe(0)
    expect(filaEn(ini, 10)).toBe(1)
    expect(filaEn(ini, 59)).toBe(2)
    // Más allá del final, la última: no un índice que no existe.
    expect(filaEn(ini, 1e9)).toBe(2)
  })
})

describe('planVentana', () => {
  const veinteMil = new Array(20000).fill(50)

  it('con 20.000 filas pinta solo las que se ven y el margen', () => {
    const plan = planVentana({ alturas: veinteMil, desde: 0, alto: 800, margen: 600 })
    // 800 visibles + 600 de margen = 1400 px → 29 filas de 50.
    expect(filas(plan)).toEqual(Array.from({ length: 29 }, (_, i) => i))
  })

  it('en mitad de la lista pinta lo de alrededor y deja huecos a los lados', () => {
    const plan = planVentana({ alturas: veinteMil, desde: 500000, alto: 800, margen: 600 })
    const pintadas = filas(plan)
    expect(pintadas[0]).toBe((500000 - 600) / 50)
    expect(pintadas[pintadas.length - 1]).toBe((500000 + 800 + 600) / 50)
    expect(plan[0]).toMatchObject({ tipo: 'hueco', alto: 500000 - 600 })
    expect(plan[plan.length - 1].tipo).toBe('hueco')
  })

  it('los huecos más las filas miden lo mismo que la lista entera', () => {
    const alturas = Array.from({ length: 3000 }, (_, i) => 40 + (i % 7) * 10)
    const total = alturas.reduce((a, b) => a + b, 0)
    for (const desde of [0, 1234, 50000, total - 100]) {
      const plan = planVentana({ alturas, desde, alto: 700, margen: 300 })
      expect(altoTotal(plan, alturas)).toBe(total)
    }
  })

  it('no falta ninguna fila de las que caen en la vista', () => {
    const alturas = Array.from({ length: 500 }, (_, i) => (i % 3 === 0 ? 400 : 50))
    const ini = inicios(alturas)
    const desde = 9000
    const plan = filas(planVentana({ alturas, desde, alto: 600, margen: 0 }))
    for (let i = 0; i < alturas.length; i++) {
      const seVe = ini[i + 1] > desde && ini[i] < desde + 600
      if (seVe) expect(plan).toContain(i)
    }
  })

  it('una serie desplegada se pinta aunque esté fuera de la vista, en su sitio', () => {
    const plan = planVentana({ alturas: veinteMil, desde: 0, alto: 800, margen: 0, fijas: new Set([5000]) })
    const pintadas = filas(plan)
    expect(pintadas).toContain(5000)
    // En orden: lo que va antes que ella, un hueco, ella, y otro hueco hasta el final.
    expect(pintadas).toEqual([...pintadas].sort((a, b) => a - b))
    const i = plan.findIndex(t => t.tipo === 'fila' && t.indice === 5000)
    expect(plan[i - 1]).toMatchObject({ tipo: 'hueco' })
    expect(plan[i + 1]).toMatchObject({ tipo: 'hueco' })
    expect(altoTotal(plan, veinteMil)).toBe(20000 * 50)
  })

  it('una fija que ya se ve no se pinta dos veces, y una que ya no existe se ignora', () => {
    const plan = planVentana({ alturas: veinteMil, desde: 0, alto: 800, margen: 0, fijas: new Set([3, 99999]) })
    const pintadas = filas(plan)
    expect(pintadas.filter(i => i === 3)).toHaveLength(1)
    expect(pintadas).not.toContain(99999)
  })

  it('sin filas no hay nada que pintar', () => {
    expect(planVentana({ alturas: [], desde: 0, alto: 800, margen: 600 })).toEqual([])
  })

  it('las claves de los huecos no se repiten', () => {
    const plan = planVentana({ alturas: veinteMil, desde: 300000, alto: 800, margen: 0, fijas: new Set([10, 15000]) })
    const claves = plan.flatMap(t => (t.tipo === 'hueco' ? [t.clave] : []))
    expect(new Set(claves).size).toBe(claves.length)
  })
})
