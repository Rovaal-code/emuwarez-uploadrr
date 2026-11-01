import { describe, expect, it } from 'vitest'
import { LimiteDeErrores } from '../LimiteDeErrores'

describe('LimiteDeErrores', () => {
  it('guarda el error que atrapa para enseñar el mensaje', () => {
    const e = new Error('Minified React error #185')
    expect(LimiteDeErrores.getDerivedStateFromError(e)).toEqual({ fallo: true, error: e })
  })

  it('sin error pinta lo que lleva dentro', () => {
    const hijo = 'contenido'
    const l = new LimiteDeErrores({ children: hijo })
    expect(l.render()).toBe(hijo)
  })

  it('con error pinta el mensaje, no el contenido, y Reintentar lo quita', () => {
    const l = new LimiteDeErrores({ children: 'contenido', donde: 'Biblioteca' })
    l.state = { fallo: true, error: new Error('x') }
    const pintado = l.render() as { props: { title: string; onRetry: () => void } }
    expect(pintado).not.toBe('contenido')
    expect(pintado.props.title).toContain('Biblioteca')
    let nuevo: unknown
    l.setState = ((s: unknown) => { nuevo = s }) as typeof l.setState
    pintado.props.onRetry()
    expect(nuevo).toEqual({ fallo: false, error: null })
  })

  it('también atrapa lo que se lanza como null o undefined', () => {
    for (const lanzado of [null, undefined]) {
      const l = new LimiteDeErrores({ children: 'contenido' })
      l.state = LimiteDeErrores.getDerivedStateFromError(lanzado)
      expect(l.render()).not.toBe('contenido')
    }
  })
})
