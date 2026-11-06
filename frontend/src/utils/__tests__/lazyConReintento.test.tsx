// @vitest-environment jsdom
/**
 * Un chunk diferido que no se puede bajar (lo típico: se publicó una versión y la pestaña pide el nombre con el hash
 * viejo). Se reintenta una vez; si sigue sin bajar, se recarga la página una sola vez, sin bucle; y «Reintentar» del
 * límite de errores también recarga en vez de volver a pintar lo que nunca va a cargar.
 */
import { act, Suspense } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cargarConReintento, esErrorDeCarga, lazyConReintento, pagina } from '../lazyConReintento'
import { LimiteDeErrores } from '../../components/LimiteDeErrores'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const chunkPerdido = () => new TypeError('Failed to fetch dynamically imported module: http://x/assets/LogsPage-viejo.js')
const pendiente = async (p: Promise<unknown>) => {
  let resuelta = false
  p.then(() => { resuelta = true }, () => { resuelta = true })
  await new Promise(r => setTimeout(r, 0))
  return !resuelta
}

let recargar: ReturnType<typeof vi.fn<() => void>>
beforeEach(() => {
  sessionStorage.clear()
  recargar = vi.fn<() => void>()
  vi.spyOn(pagina, 'recargar').mockImplementation(recargar)
})
afterEach(() => { vi.restoreAllMocks() })

describe('cargar un chunk', () => {
  it('reconoce el error de carga de un módulo y no otros', () => {
    expect(esErrorDeCarga(chunkPerdido())).toBe(true)
    expect(esErrorDeCarga(new TypeError('Importing a module script failed.'))).toBe(true)
    expect(esErrorDeCarga(new Error('Cannot read properties of undefined'))).toBe(false)
  })

  it('si falla una vez, lo reintenta y sale bien sin recargar', async () => {
    const cargar = vi.fn().mockRejectedValueOnce(chunkPerdido()).mockResolvedValue('módulo')
    await expect(cargarConReintento(cargar)).resolves.toBe('módulo')
    expect(cargar).toHaveBeenCalledTimes(2)
    expect(recargar).not.toHaveBeenCalled()
  })

  it('si sigue fallando, recarga la página UNA vez; la segunda deja pasar el error', async () => {
    const cargar = vi.fn().mockRejectedValue(chunkPerdido())
    expect(await pendiente(cargarConReintento(cargar))).toBe(true)   // espera a la recarga
    expect(recargar).toHaveBeenCalledTimes(1)
    await expect(cargarConReintento(cargar)).rejects.toThrow('dynamically imported module')
    expect(recargar).toHaveBeenCalledTimes(1)
  })

  it('un error que no es de carga no recarga', async () => {
    const cargar = vi.fn().mockRejectedValue(new Error('roto'))
    await expect(cargarConReintento(cargar)).rejects.toThrow('roto')
    expect(recargar).not.toHaveBeenCalled()
  })
})

describe('lazyConReintento en una sección', () => {
  let raiz: Root
  afterEach(() => act(() => raiz.unmount()))

  it('la sección sale aunque el primer intento de bajar el chunk falle', async () => {
    const cargar = vi.fn()
      .mockRejectedValueOnce(chunkPerdido())
      .mockResolvedValue({ default: () => <p>Logs</p> })
    const Seccion = lazyConReintento(cargar)
    const caja = document.createElement('div')
    raiz = createRoot(caja)
    await act(async () => { raiz.render(<LimiteDeErrores><Suspense fallback="cargando"><Seccion /></Suspense></LimiteDeErrores>) })
    expect(caja.textContent).toBe('Logs')
  })
})

describe('Reintentar del límite de errores', () => {
  it('con un chunk que no se pudo bajar, recarga la página', () => {
    const l = new LimiteDeErrores({ children: 'contenido' })
    l.state = { fallo: true, error: chunkPerdido() }
    let nuevo: unknown
    l.setState = ((s: unknown) => { nuevo = s }) as typeof l.setState
    ;(l.render() as { props: { onRetry: () => void } }).props.onRetry()
    expect(recargar).toHaveBeenCalledTimes(1)
    expect(nuevo).toBeUndefined()
  })
})
