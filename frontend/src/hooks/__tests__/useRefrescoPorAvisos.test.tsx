// @vitest-environment jsdom
/**
 * Cuántas veces recarga una sección por el canal de avisos: al arrancar (una, la suya), cuando el canal se cae y
 * vuelve, y con los avisos de progreso, que tienen su propia recarga barata.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, useEffect } from 'react'
import { createRoot, type Root } from 'react-dom/client'

type Oyente = (aviso: { tipo: string; [k: string]: unknown }) => void
const estado = vi.hoisted(() => ({
  vivo: false,
  observadores: new Set<(vivo: boolean, primeraVez: boolean) => void>(),
  oyentes: new Map<string, Set<(aviso: { tipo: string }) => void>>(),
}))

vi.mock('../../api/eventos', () => ({
  canalVivo: () => estado.vivo,
  observarCanal: (cb: (vivo: boolean, primeraVez: boolean) => void) => {
    estado.observadores.add(cb)
    return () => { estado.observadores.delete(cb) }
  },
  suscribirse: (tipo: string, cb: Oyente) => {
    if (!estado.oyentes.has(tipo)) estado.oyentes.set(tipo, new Set())
    estado.oyentes.get(tipo)!.add(cb)
    return () => { estado.oyentes.get(tipo)!.delete(cb) }
  },
}))

import { useRefrescoPorAvisos } from '../useRefrescoPorAvisos'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let raiz: Root | null = null
function render(el: React.ReactElement) {
  const caja = document.createElement('div')
  document.body.appendChild(caja)
  raiz = createRoot(caja)
  act(() => { raiz!.render(el) })
}

function canal(vivo: boolean, primeraVez: boolean) {
  estado.vivo = vivo
  act(() => { for (const cb of estado.observadores) cb(vivo, primeraVez) })
}
function aviso(tipo: string) {
  act(() => { for (const cb of estado.oyentes.get(tipo) ?? []) cb({ tipo }) })
}

// Como las páginas de verdad: carga sola al montarse y deja el resto al gancho.
function Seccion({ cargar, progreso }: { cargar: () => void; progreso?: () => void }) {
  useEffect(() => { cargar() }, [cargar])
  useRefrescoPorAvisos(['subida-estado'], cargar, {
    cadaSinCanal: 60_000, soloVisible: ['subida-progreso'], recargarProgreso: progreso,
  })
  return null
}

beforeEach(() => {
  vi.useFakeTimers()
  estado.vivo = false
  estado.observadores.clear()
  estado.oyentes.clear()
})
afterEach(() => {
  act(() => { raiz?.unmount() })
  raiz = null
  vi.useRealTimers()
})

describe('al arrancar', () => {
  it('montar con el canal aún sin conectar y conectarlo después es UNA carga, no tres', () => {
    const cargar = vi.fn()
    render(<Seccion cargar={cargar} />)
    canal(true, true)                 // la primera conexión de la aplicación
    expect(cargar).toHaveBeenCalledTimes(1)
  })

  it('un canal que se cae y vuelve sí recarga: lo que pasó mientras tanto no se reenvía', () => {
    const cargar = vi.fn()
    render(<Seccion cargar={cargar} />)
    canal(true, true)
    canal(false, false)
    expect(cargar).toHaveBeenCalledTimes(2)   // caído y a la vista: nada más le va a despertar
    canal(true, false)
    expect(cargar).toHaveBeenCalledTimes(3)   // vuelve
  })

  it('montar con el canal caído después de haber estado vivo recarga al volver', () => {
    const cargar = vi.fn()
    render(<Seccion cargar={cargar} />)
    expect(cargar).toHaveBeenCalledTimes(1)
    canal(true, false)                // ya había estado vivo antes de montarse esta sección
    expect(cargar).toHaveBeenCalledTimes(2)
  })
})

describe('avisos de progreso', () => {
  it('subida-progreso usa la recarga de progreso y no la completa', () => {
    const cargar = vi.fn()
    const progreso = vi.fn()
    render(<Seccion cargar={cargar} progreso={progreso} />)
    canal(true, true)
    aviso('subida-progreso')
    act(() => { vi.advanceTimersByTime(500) })
    expect(progreso).toHaveBeenCalledTimes(1)
    expect(cargar).toHaveBeenCalledTimes(1)   // solo la del montaje
  })

  it('si en la misma tanda llega uno de «qué hay», gana la completa', () => {
    const cargar = vi.fn()
    const progreso = vi.fn()
    render(<Seccion cargar={cargar} progreso={progreso} />)
    canal(true, true)
    aviso('subida-progreso')
    aviso('subida-estado')
    act(() => { vi.advanceTimersByTime(500) })
    expect(cargar).toHaveBeenCalledTimes(2)
    expect(progreso).not.toHaveBeenCalled()
  })

  it('sin recarga de progreso propia, el progreso recarga entero como siempre', () => {
    const cargar = vi.fn()
    render(<Seccion cargar={cargar} />)
    canal(true, true)
    aviso('subida-progreso')
    act(() => { vi.advanceTimersByTime(500) })
    expect(cargar).toHaveBeenCalledTimes(2)
  })
})
