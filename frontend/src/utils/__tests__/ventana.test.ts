/**
 * Qué filas pinta la lista de Biblioteca.
 *
 * Pintarlas todas costaba casi 3 GB con 15.900 archivos y dos filtros (8.756
 * filas, 667.000 nodos). Lo que importa aquí es que se pinte poco, que no falte
 * nada de lo que se ve, y que los huecos midan lo que medirían las filas: si no,
 * la barra de scroll mentiría sobre el largo de la lista.
 */
import { describe, it, expect } from 'vitest'
import { inicios, filaEn, planVentana, columnasAutoFill, filasDeRejilla, type Tramo, medidaCorregida, cuentaTrasMedir, topeRecienAlcanzado, AJUSTES_SEGUIDOS_MAX } from '../ventana'

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

// Los pósters: 18.358 tarjetas con Estado = Disponible eran 148.000 nodos y
// casi 3 s de bloqueo al cambiar a esa vista.
describe('columnasAutoFill', () => {
  it('cuenta las mismas columnas que auto-fill', () => {
    // 6 × 140 + 5 × 16 = 920: caben 6 justas, con un píxel menos 5.
    expect(columnasAutoFill(920, 140, 16)).toBe(6)
    expect(columnasAutoFill(919, 140, 16)).toBe(5)
  })

  it('al menos una, aunque no quepa', () => {
    expect(columnasAutoFill(0, 140, 16)).toBe(1)
  })
})

describe('filasDeRejilla', () => {
  const base = { total: 18358, columnas: 8, paso: 250, alto: 800, margen: 600 }

  it('arriba del todo pinta las que se ven y el margen', () => {
    // 800 + 600 = 1400 px → filas 0 a 5 de 250.
    expect(filasDeRejilla({ ...base, desde: 0 })).toEqual({ filas: 2295, primera: 0, ultima: 5 })
  })

  it('en mitad pinta lo de alrededor', () => {
    const { primera, ultima } = filasDeRejilla({ ...base, desde: 100000 })
    expect(primera).toBe(Math.floor((100000 - 600) / 250))
    expect(ultima).toBe(Math.floor((100000 + 800 + 600) / 250))
  })

  it('al final no se sale de la última fila, que puede ir a medias', () => {
    expect(filasDeRejilla({ ...base, desde: 1e9 })).toMatchObject({ primera: 2294, ultima: 2294 })
  })
})

describe('medidaCorregida', () => {
  const a = { columnas: 3, alto: 300 }

  it('deja la medida como está si lo medido es lo mismo', () => {
    expect(medidaCorregida(a, { columnas: 3, alto: 300 }, 0)).toBeNull()
  })

  it('corrige si cambió el alto o las columnas', () => {
    expect(medidaCorregida(a, { columnas: 3, alto: 330 }, 0)).toEqual({ columnas: 3, alto: 330 })
    expect(medidaCorregida(a, { columnas: 4, alto: 300 }, 2)).toEqual({ columnas: 4, alto: 300 })
  })

  it('una oscilación entre dos medidas se corta en el tope, en vez de repintar sin fin', () => {
    // Cada medida provoca la otra: A mide B, y B mide A.
    const medirDesde = (m: { alto: number; columnas: number }) => ({ columnas: 3, alto: m.alto === 300 ? 330 : 300 })
    let medida = a
    let usados = 0
    let vueltas = 0
    for (;;) {
      const nueva = medidaCorregida(medida, medirDesde(medida), usados)
      if (!nueva) break
      medida = nueva
      usados++
      if (++vueltas > 1000) throw new Error('no termina')
    }
    expect(vueltas).toBe(AJUSTES_SEGUIDOS_MAX)
  })

  it('una corrección normal (columnas y luego alto) cabe de sobra en el tope', () => {
    expect(AJUSTES_SEGUIDOS_MAX).toBeGreaterThanOrEqual(3)
  })
})

describe('cuentaTrasMedir', () => {
  it('otra clave (scroll, lista, ancho) empieza la cuenta de nuevo', () => {
    expect(cuentaTrasMedir({ clave: 'a', usados: 5 }, 'b', false)).toEqual({ clave: 'b', usados: 0 })
  })

  it('una medida que ya coincide también: seis correcciones separadas no agotan el tope', () => {
    let c = { clave: 'a', usados: 0 }
    for (let i = 0; i < AJUSTES_SEGUIDOS_MAX * 2; i++) {
      c = cuentaTrasMedir(c, 'a', false)
      c.usados++                       // una corrección
      c = cuentaTrasMedir(c, 'a', true) // y la rejilla se calma
      expect(c.usados).toBe(0)
    }
  })

  it('con la misma clave y medidas todavía distintas, la cuenta sigue', () => {
    const c = { clave: 'a', usados: 4 }
    expect(cuentaTrasMedir(c, 'a', false)).toBe(c)
  })
})

describe('topeRecienAlcanzado', () => {
  it('una oscilación avisa una sola vez, cuando el tope la corta', () => {
    // Lo mismo que hace RejillaVirtual tras cada pintado, con dos medidas que se provocan una a la otra.
    const medirDesde = (m: { alto: number; columnas: number }) => ({ columnas: 3, alto: m.alto === 300 ? 330 : 300 })
    let medida = { columnas: 3, alto: 300 }
    let c = { clave: 'a', usados: 0 }
    let avisos = 0
    for (let pintado = 0; pintado < 50; pintado++) {
      const medido = medirDesde(medida)
      const coincide = medido.alto === medida.alto
      c = cuentaTrasMedir(c, 'a', coincide)
      if (topeRecienAlcanzado(c, coincide)) { avisos++; c.usados++ }
      const nueva = medidaCorregida(medida, medido, c.usados)
      if (nueva) { medida = nueva; c.usados++ }
    }
    expect(avisos).toBe(1)
  })

  it('una medida que se calma no avisa', () => {
    expect(topeRecienAlcanzado({ clave: 'a', usados: AJUSTES_SEGUIDOS_MAX }, true)).toBe(false)
    expect(topeRecienAlcanzado({ clave: 'a', usados: 2 }, false)).toBe(false)
  })
})
