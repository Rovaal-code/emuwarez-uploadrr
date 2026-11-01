/**
 * Lo mínimo para montar un componente en jsdom y usarlo como lo haría alguien: pulsar, elegir, escribir y
 * esperar a que aparezca algo. Sin Testing Library: con `act` de React y los eventos del DOM basta.
 */
import { act, type ReactElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

// FitText mide con ResizeObserver, que jsdom no trae.
if (!('ResizeObserver' in globalThis)) {
  ;(globalThis as { ResizeObserver?: unknown }).ResizeObserver = class {
    observe() { /* nada que medir en jsdom */ }
    unobserve() { /* idem */ }
    disconnect() { /* idem */ }
  }
}

let raiz: Root | null = null
let caja: HTMLDivElement | null = null

export async function montar(el: ReactElement) {
  caja = document.createElement('div')
  document.body.appendChild(caja)
  raiz = createRoot(caja)
  await act(async () => { raiz!.render(el) })
}

export async function desmontar() {
  if (raiz) await act(async () => { raiz!.unmount() })
  caja?.remove()
  raiz = null
  caja = null
  document.body.innerHTML = ''
}

export const texto = () => document.body.textContent ?? ''

/** Repite `fn` hasta que devuelva algo, dejando correr a React entre intento e intento. */
export async function esperar<T>(fn: () => T | null | undefined | false, ms = 3000): Promise<T> {
  const fin = Date.now() + ms
  for (;;) {
    let r: T | null | undefined | false
    try { r = fn() } catch { r = undefined }
    if (r) return r as T
    if (Date.now() > fin) throw new Error(`No llegó a cumplirse: ${fn.toString()}`)
    await act(async () => { await new Promise(res => setTimeout(res, 20)) })
  }
}

/** El botón cuyo texto es exactamente `nombre`, si lo hay. */
export function boton(nombre: string): HTMLButtonElement | undefined {
  return [...document.querySelectorAll('button')].find(b => b.textContent?.trim() === nombre)
}

/** La tarjeta (un botón con título y explicación) cuyo título es `titulo`. */
export function tarjeta(titulo: string): HTMLButtonElement | undefined {
  return [...document.querySelectorAll('button')].find(b => b.firstElementChild?.textContent?.trim() === titulo)
}

/** El select o input de la etiqueta que empieza por `nombre` (los campos del asistente). */
export function campo<T extends HTMLSelectElement | HTMLInputElement = HTMLSelectElement>(nombre: string): T | undefined {
  const label = [...document.querySelectorAll('label')].find(l => l.textContent?.trim().startsWith(nombre))
  return (label?.querySelector('select, input') ?? undefined) as T | undefined
}

export async function pulsar(el: Element | undefined) {
  if (!el) throw new Error('No hay nada que pulsar')
  await act(async () => { el.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
}

export async function elegir(sel: HTMLSelectElement | undefined, valor: string) {
  if (!sel) throw new Error('No hay desplegable')
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!.call(sel, valor)
    sel.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

export async function escribir(input: HTMLInputElement | undefined, valor: string) {
  if (!input) throw new Error('No hay casilla')
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, valor)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

/** Una promesa que se resuelve a mano, para ver qué pasa mientras una petición sigue en vuelo. */
export function diferida<T>() {
  let resolver!: (v: T) => void
  let rechazar!: (e: unknown) => void
  const promesa = new Promise<T>((res, rej) => { resolver = res; rechazar = rej })
  return { promesa, resolver, rechazar }
}
