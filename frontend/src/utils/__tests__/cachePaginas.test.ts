/**
 * La caché que evita volver a ver "Cargando…" al cambiar de sección.
 *
 * Lo que se prueba son sus tres decisiones: que cada sección tenga la suya,
 * que NO caduque por tiempo (la invalidan hechos, ver la cabecera del módulo),
 * y que una petición que salió antes de invalidar no vuelva a meter lo viejo.
 * Que solo se guarde la vista sin filtrar lo decide quien llama, no la caché:
 * no puede saber qué es un filtro en cada pantalla.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import {
  guardarPagina, ultimaPagina, olvidarPagina, generacionCache,
  tomarCopia, copiaNoConfirmada,
} from '../cachePaginas'

interface Datos { contador: number }

describe('la caché de secciones', () => {
  beforeEach(() => olvidarPagina())

  it('sin nada guardado, no hay nada que reutilizar (primera visita)', () => {
    expect(ultimaPagina<Datos>('panel')).toBeNull()
  })

  it('lo guardado se reutiliza', () => {
    guardarPagina<Datos>('panel', { contador: 7 })
    expect(ultimaPagina<Datos>('panel')?.contador).toBe(7)
  })

  it('cada sección guarda la suya, sin mezclarse', () => {
    guardarPagina<Datos>('panel', { contador: 1 })
    guardarPagina<Datos>('biblioteca', { contador: 2 })
    expect(ultimaPagina<Datos>('panel')?.contador).toBe(1)
    expect(ultimaPagina<Datos>('biblioteca')?.contador).toBe(2)
    expect(ultimaPagina<Datos>('peticiones')).toBeNull()
  })

  it('guardar otra vez sustituye lo anterior', () => {
    guardarPagina<Datos>('panel', { contador: 1 })
    guardarPagina<Datos>('panel', { contador: 2 })
    expect(ultimaPagina<Datos>('panel')?.contador).toBe(2)
  })

  // Subidas guarda un array, y una lista vacía es una respuesta legítima (no
  // hay ninguna subida). Distinguirla de "no hay copia" es la diferencia entre
  // enseñar la tabla vacía o el "Cargando…" que esto viene a quitar.
  it('un valor legítimamente vacío no se confunde con no tener nada', () => {
    guardarPagina<Datos[]>('subidas', [])
    expect(ultimaPagina<Datos[]>('subidas')).toEqual([])
  })

  it('se puede olvidar una sola sección', () => {
    guardarPagina<Datos>('panel', { contador: 1 })
    guardarPagina<Datos>('biblioteca', { contador: 2 })
    olvidarPagina('panel')
    expect(ultimaPagina<Datos>('panel')).toBeNull()
    expect(ultimaPagina<Datos>('biblioteca')).not.toBeNull()
  })

  // La carrera de verdad: Subidas repide cada 2,5 segundos, así que una
  // sincronización puede terminar con una petición ya en vuelo. Al resolver
  // traería datos de ANTES, y guardarlos volvería a meter en la caché justo
  // lo que se acababa de tirar.
  it('lo pedido antes de invalidar ya no se guarda', () => {
    const generacion = generacionCache()      // la página empieza a pedir
    olvidarPagina()                           // termina una sincronización
    guardarPagina<Datos>('subidas', { contador: 1 }, { generacion })
    expect(ultimaPagina<Datos>('subidas')).toBeNull()
  })

  it('olvidar una sola sección también invalida lo que estuviera en vuelo', () => {
    const generacion = generacionCache()
    olvidarPagina('biblioteca')
    guardarPagina<Datos>('panel', { contador: 1 }, { generacion })
    expect(ultimaPagina<Datos>('panel')).toBeNull()
  })

  it('lo pedido después sí se guarda (la recarga que sigue a la sincronización)', () => {
    olvidarPagina()
    const generacion = generacionCache()
    guardarPagina<Datos>('subidas', { contador: 2 }, { generacion })
    expect(ultimaPagina<Datos>('subidas')?.contador).toBe(2)
  })

  it('sin declarar generación se guarda igual: es opcional', () => {
    guardarPagina<Datos>('panel', { contador: 3 })
    expect(ultimaPagina<Datos>('panel')?.contador).toBe(3)
  })
})

// El único caso en que una copia se queda mintiendo, y no un instante sino
// hasta que toques algo: montas desde la copia y la recarga que debía
// confirmarla FALLA. Sin plazo de caducidad no hay nada más que la acote.
describe('la copia que nunca se llegó a confirmar', () => {
  beforeEach(() => olvidarPagina())

  it('montar desde la copia la deja pendiente de confirmar', () => {
    guardarPagina<Datos>('biblioteca', { contador: 1 })
    tomarCopia<Datos>('biblioteca')
    expect(copiaNoConfirmada('biblioteca')).toBe(true)
  })

  it('al fallar se tira, para no repetir la escena al volver a entrar', () => {
    guardarPagina<Datos>('biblioteca', { contador: 1 })
    tomarCopia<Datos>('biblioteca')
    copiaNoConfirmada('biblioteca')
    expect(ultimaPagina<Datos>('biblioteca')).toBeNull()
  })

  it('una recarga que llega bien la confirma', () => {
    guardarPagina<Datos>('biblioteca', { contador: 1 })
    tomarCopia<Datos>('biblioteca')
    guardarPagina<Datos>('biblioteca', { contador: 2 })   // la recarga vuelve
    expect(copiaNoConfirmada('biblioteca')).toBe(false)
  })

  // Un refresco de fondo que parpadea no puede vaciar una tabla buena.
  it('con los datos ya confirmados, un fallo posterior no vacía nada', () => {
    guardarPagina<Datos>('subidas', { contador: 1 })
    tomarCopia<Datos>('subidas')
    guardarPagina<Datos>('subidas', { contador: 2 })
    expect(copiaNoConfirmada('subidas')).toBe(false)
    expect(ultimaPagina<Datos>('subidas')?.contador).toBe(2)
  })

  it('sin copia con la que montar no hay nada que vaciar (primera visita)', () => {
    expect(tomarCopia<Datos>('panel')).toBeNull()
    expect(copiaNoConfirmada('panel')).toBe(false)
  })

  it('dos fallos seguidos no vacían dos veces', () => {
    guardarPagina<Datos>('panel', { contador: 1 })
    tomarCopia<Datos>('panel')
    expect(copiaNoConfirmada('panel')).toBe(true)
    expect(copiaNoConfirmada('panel')).toBe(false)
  })

  it('cada sección lleva su propia cuenta', () => {
    guardarPagina<Datos>('biblioteca', { contador: 1 })
    guardarPagina<Datos>('panel', { contador: 2 })
    tomarCopia<Datos>('biblioteca')
    expect(copiaNoConfirmada('panel')).toBe(false)
    expect(ultimaPagina<Datos>('panel')).not.toBeNull()
  })

  it('invalidar por sincronización deja la marca limpia', () => {
    guardarPagina<Datos>('biblioteca', { contador: 1 })
    tomarCopia<Datos>('biblioteca')
    olvidarPagina()
    expect(copiaNoConfirmada('biblioteca')).toBe(false)
  })
})
