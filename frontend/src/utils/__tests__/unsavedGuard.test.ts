import { afterEach, describe, expect, it, vi } from 'vitest'
import { guardedLeave, hasUnsavedChanges, registerDirty, setLeavePrompt } from '../unsavedGuard'

const quitar: Array<() => void> = []
const registrar = (id: string, fn: () => boolean) => { const q = registerDirty(id, fn); quitar.push(q); return q }

afterEach(() => {
  quitar.splice(0).forEach(q => q())
  setLeavePrompt(null)
  vi.unstubAllGlobals()
})

describe('registro de cambios sin guardar', () => {
  it('sin nadie registrado no hay cambios', () => {
    expect(hasUnsavedChanges()).toBe(false)
  })

  it('basta con que uno de los registrados tenga cambios', () => {
    registrar('config', () => false)
    registrar('rutas', () => true)
    expect(hasUnsavedChanges()).toBe(true)
  })

  it('lo que se quita deja de contar, y lo demás sigue', () => {
    const quitarRutas = registrar('rutas', () => true)
    registrar('cuenta', () => true)
    quitarRutas()
    expect(hasUnsavedChanges()).toBe(true)
  })

  it('se pregunta en el momento: el estado de hoy, no el del registro', () => {
    let sucio = false
    registrar('config', () => sucio)
    expect(hasUnsavedChanges()).toBe(false)
    sucio = true
    expect(hasUnsavedChanges()).toBe(true)
  })

  it('con el mismo id gana el último, y quitar el viejo no quita el nuevo', () => {
    const quitarViejo = registrar('config', () => false)
    registrar('config', () => true)
    quitarViejo()
    expect(hasUnsavedChanges()).toBe(true)
  })
})

describe('guardedLeave', () => {
  it('sin cambios sale al momento', () => {
    const proceed = vi.fn()
    guardedLeave(proceed)
    expect(proceed).toHaveBeenCalledTimes(1)
  })

  it('con cambios pregunta y solo sale al confirmar', () => {
    registrar('rutas', () => true)
    const abrir = vi.fn()
    setLeavePrompt(abrir)
    const proceed = vi.fn()

    guardedLeave(proceed)
    expect(proceed).not.toHaveBeenCalled()
    expect(abrir).toHaveBeenCalledTimes(1)

    abrir.mock.calls[0][0]()
    expect(proceed).toHaveBeenCalledTimes(1)
  })

  it('sin modal registrado pregunta con window.confirm', () => {
    registrar('rutas', () => true)
    const confirmar = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true)
    vi.stubGlobal('window', { confirm: confirmar })
    const proceed = vi.fn()

    guardedLeave(proceed)
    expect(proceed).not.toHaveBeenCalled()
    guardedLeave(proceed)
    expect(proceed).toHaveBeenCalledTimes(1)
  })
})
