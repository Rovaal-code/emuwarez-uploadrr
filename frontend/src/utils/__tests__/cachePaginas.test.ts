/**
 * La caché que evita volver a ver "Cargando…" al cambiar de sección.
 *
 * Lo que se prueba es la regla de vigencia, que cada sección tenga la suya, y
 * que una petición que salió antes de invalidar no vuelva a meter lo viejo.
 * Que solo se guarde la vista sin filtrar lo decide quien llama (no se guarda
 * si hay filtros), porque la caché no puede saber qué es un filtro en cada
 * pantalla.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { guardarPagina, ultimaPagina, olvidarPagina, generacionCache, VIGENCIA_MS } from '../cachePaginas'

interface Datos { contador: number }

describe('la caché de secciones', () => {
  beforeEach(() => olvidarPagina())

  it('sin nada guardado, no hay nada que reutilizar (primera visita)', () => {
    expect(ultimaPagina<Datos>('panel')).toBeNull()
  })

  it('lo recién guardado se reutiliza', () => {
    guardarPagina<Datos>('panel', { contador: 7 }, { ahora: 1_000 })
    expect(ultimaPagina<Datos>('panel', 1_000)?.contador).toBe(7)
  })

  it('sigue valiendo dentro de la vigencia (ir a otra sección y volver)', () => {
    guardarPagina<Datos>('panel', { contador: 7 }, { ahora: 1_000 })
    expect(ultimaPagina<Datos>('panel', 1_000 + VIGENCIA_MS - 1)).not.toBeNull()
  })

  it('justo en el límite todavía vale', () => {
    guardarPagina<Datos>('panel', { contador: 7 }, { ahora: 1_000 })
    expect(ultimaPagina<Datos>('panel', 1_000 + VIGENCIA_MS)).not.toBeNull()
  })

  it('deja de valer al pasarse: mejor "Cargando" que un dato falso', () => {
    guardarPagina<Datos>('panel', { contador: 7 }, { ahora: 1_000 })
    expect(ultimaPagina<Datos>('panel', 1_000 + VIGENCIA_MS + 1)).toBeNull()
  })

  it('cada sección guarda la suya, sin mezclarse', () => {
    guardarPagina<Datos>('panel', { contador: 1 }, { ahora: 1_000 })
    guardarPagina<Datos>('biblioteca', { contador: 2 }, { ahora: 1_000 })
    expect(ultimaPagina<Datos>('panel', 1_000)?.contador).toBe(1)
    expect(ultimaPagina<Datos>('biblioteca', 1_000)?.contador).toBe(2)
    expect(ultimaPagina<Datos>('peticiones', 1_000)).toBeNull()
  })

  it('guardar otra vez renueva la cuenta', () => {
    guardarPagina<Datos>('panel', { contador: 1 }, { ahora: 1_000 })
    guardarPagina<Datos>('panel', { contador: 2 }, { ahora: 100_000 })
    expect(ultimaPagina<Datos>('panel', 100_000)?.contador).toBe(2)
  })

  it('se puede olvidar una sola sección', () => {
    guardarPagina<Datos>('panel', { contador: 1 }, { ahora: 1_000 })
    guardarPagina<Datos>('biblioteca', { contador: 2 }, { ahora: 1_000 })
    olvidarPagina('panel')
    expect(ultimaPagina<Datos>('panel', 1_000)).toBeNull()
    expect(ultimaPagina<Datos>('biblioteca', 1_000)).not.toBeNull()
  })

  // La carrera de verdad: Subidas repide cada 2,5 segundos, así que una
  // sincronización puede terminar con una petición ya en vuelo. Al resolver
  // traería datos de ANTES de la sincronización, y guardarlos volvería a
  // meter en la caché justo lo que se acababa de tirar, para dos minutos.
  it('lo pedido antes de invalidar ya no se guarda', () => {
    const generacion = generacionCache()      // la página empieza a pedir
    olvidarPagina()                           // termina una sincronización
    guardarPagina<Datos>('subidas', { contador: 1 }, { generacion, ahora: 1_000 })
    expect(ultimaPagina<Datos>('subidas', 1_000)).toBeNull()
  })

  it('olvidar una sola sección también invalida lo que estuviera en vuelo', () => {
    const generacion = generacionCache()
    olvidarPagina('biblioteca')
    guardarPagina<Datos>('panel', { contador: 1 }, { generacion, ahora: 1_000 })
    expect(ultimaPagina<Datos>('panel', 1_000)).toBeNull()
  })

  it('lo pedido después sí se guarda (la recarga que sigue a la sincronización)', () => {
    olvidarPagina()
    const generacion = generacionCache()
    guardarPagina<Datos>('subidas', { contador: 2 }, { generacion, ahora: 1_000 })
    expect(ultimaPagina<Datos>('subidas', 1_000)?.contador).toBe(2)
  })

  it('sin declarar generación se guarda igual: es opcional', () => {
    guardarPagina<Datos>('panel', { contador: 3 }, { ahora: 1_000 })
    expect(ultimaPagina<Datos>('panel', 1_000)?.contador).toBe(3)
  })
})
