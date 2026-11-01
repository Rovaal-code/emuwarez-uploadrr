import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AGOTADO, accionesOptimistas, conTope } from '../accionesOptimistas'

// Una promesa que se resuelve o falla a mano.
function aMano<T>() {
  let resolver!: (v: T) => void
  let fallar!: (e: unknown) => void
  const promesa = new Promise<T>((res, rej) => { resolver = res; fallar = rej })
  return { promesa, resolver, fallar }
}

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

describe('conTope', () => {
  it('devuelve lo de la promesa si llega antes', async () => {
    await expect(conTope(Promise.resolve(3), 1000)).resolves.toBe(3)
  })

  it('pasado el tope devuelve AGOTADO', async () => {
    const colgada = aMano<number>()
    const r = conTope(colgada.promesa, 1000)
    await vi.advanceTimersByTimeAsync(1000)
    await expect(r).resolves.toBe(AGOTADO)
  })

  it('un fallo antes del tope se propaga', async () => {
    await expect(conTope(Promise.reject(new Error('x')), 1000)).rejects.toThrow('x')
  })
})

describe('accionesOptimistas', () => {
  it('una acción colgada no bloquea la lista: al tope se da por acabada y se consulta', async () => {
    const consultar = vi.fn(async () => 'servidor')
    const aplicar = vi.fn()
    const { accion, refrescar } = accionesOptimistas(consultar, aplicar, 15_000)
    const colgada = aMano<void>()
    void accion(() => {}, () => colgada.promesa)
    // Mientras está en marcha, refrescar solo se apunta.
    await refrescar()
    expect(consultar).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(15_000)
    expect(consultar).toHaveBeenCalledTimes(1)
    expect(aplicar).toHaveBeenCalledWith('servidor')
    // Y después, refrescar vuelve a funcionar.
    await refrescar()
    expect(consultar).toHaveBeenCalledTimes(2)
  })

  it('una acción que invalida una consulta en vuelo la repite al acabar', async () => {
    const vieja = aMano<string>()
    const consultar = vi.fn()
      .mockImplementationOnce(() => vieja.promesa)
      .mockImplementation(async () => 'nueva')
    const aplicar = vi.fn()
    const { accion, refrescar } = accionesOptimistas(consultar, aplicar)
    const enVuelo = refrescar()
    await accion(() => {}, async () => {})
    // La consulta que iba en vuelo no se aplica (es de antes del cambio)…
    vieja.resolver('vieja')
    await enVuelo
    expect(aplicar).not.toHaveBeenCalledWith('vieja')
    // …pero no se pierde: se repitió al acabar la acción.
    await vi.runAllTimersAsync()
    expect(consultar).toHaveBeenCalledTimes(2)
    expect(aplicar).toHaveBeenCalledWith('nueva')
  })

  it('sin consulta en vuelo ni fallo, una acción no consulta de más', async () => {
    const consultar = vi.fn(async () => 'x')
    const { accion } = accionesOptimistas(consultar, () => {})
    const optimista = vi.fn()
    await accion(optimista, async () => {})
    expect(optimista).toHaveBeenCalledTimes(1)
    expect(consultar).not.toHaveBeenCalled()
  })

  it('si la acción falla se consulta al acabar', async () => {
    const consultar = vi.fn(async () => 'x')
    const { accion } = accionesOptimistas(consultar, () => {})
    await accion(() => {}, async () => { throw new Error('500') })
    expect(consultar).toHaveBeenCalledTimes(1)
  })

  it('con dos acciones a la vez, se consulta una sola vez cuando acaban las dos', async () => {
    const consultar = vi.fn(async () => 'x')
    const { accion } = accionesOptimistas(consultar, () => {})
    const a = aMano<void>()
    const b = aMano<void>()
    const pa = accion(() => {}, () => a.promesa)
    const pb = accion(() => {}, () => b.promesa)
    a.fallar(new Error('x'))
    await pa
    expect(consultar).not.toHaveBeenCalled()
    b.resolver()
    await pb
    expect(consultar).toHaveBeenCalledTimes(1)
  })
})
