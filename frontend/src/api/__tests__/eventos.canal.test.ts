/**
 * El canal de avisos frente a lo que lo mata sin ruido: un 401 que no es de
 * verdad y una conexión que muere sin cerrarse. Con fetch y temporizadores de
 * mentira, para ver cuándo reconecta y cuándo no.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

type Fetch = (url: string, init?: RequestInit) => Promise<Response>

const json = (cuerpo: unknown, status = 200) =>
  new Response(JSON.stringify(cuerpo), { status, headers: { 'content-type': 'application/json' } })

// Un canal abierto que no dice nada, y que falla si se aborta (como el de verdad).
function canalAbierto(signal?: AbortSignal | null, alCrear?: (c: ReadableStreamDefaultController) => void) {
  const cuerpo = new ReadableStream({
    start(c) {
      alCrear?.(c)
      signal?.addEventListener('abort', () => c.error(new DOMException('abort', 'AbortError')))
    },
  })
  return new Response(cuerpo, { status: 200, headers: { 'content-type': 'text/event-stream' } })
}

const eventosPedidos = (f: ReturnType<typeof vi.fn>) =>
  f.mock.calls.filter(([url]) => url === '/api/eventos').length

let quitados: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.resetModules()
  vi.useFakeTimers()
  quitados = vi.fn()
  vi.stubGlobal('localStorage', { getItem: () => 'token-de-prueba', setItem: vi.fn(), removeItem: quitados })
  vi.stubGlobal('sessionStorage', { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

async function conectar(fetchSimulado: Fetch) {
  const f = vi.fn(fetchSimulado)
  vi.stubGlobal('fetch', f)
  const eventos = await import('../eventos')
  const baja = eventos.suscribirse('prueba', () => {})
  await vi.advanceTimersByTimeAsync(0)
  return { f, eventos, baja }
}

describe('conexión muerta', () => {
  it('sin una sola línea durante la vigilancia se corta y se reconecta', async () => {
    const { f, eventos, baja } = await conectar(async (_u, init) => canalAbierto(init?.signal))
    expect(eventos.canalVivo()).toBe(true)

    await vi.advanceTimersByTimeAsync(eventos.VIGILANCIA_MS - 1)
    expect(eventos.canalVivo()).toBe(true)
    expect(eventosPedidos(f)).toBe(1)

    await vi.advanceTimersByTimeAsync(1)
    expect(eventos.canalVivo()).toBe(false)           // las pantallas vuelven al sondeo rápido

    await vi.advanceTimersByTimeAsync(eventos.ESPERAS_MS[0])
    expect(eventosPedidos(f)).toBe(2)
    baja()
  })

  it('cada línea que llega, aunque sea un latido, retrasa el corte', async () => {
    let escribir: ReadableStreamDefaultController | undefined
    const { f, eventos, baja } = await conectar(async (_u, init) => canalAbierto(init?.signal, c => { escribir = c }))

    await vi.advanceTimersByTimeAsync(40_000)
    escribir!.enqueue(new TextEncoder().encode(': latido\n\n'))
    await vi.advanceTimersByTimeAsync(eventos.VIGILANCIA_MS - 1)
    expect(eventos.canalVivo()).toBe(true)
    expect(eventosPedidos(f)).toBe(1)

    await vi.advanceTimersByTimeAsync(1)
    expect(eventos.canalVivo()).toBe(false)
    baja()
  })

  it('al darse de baja deja de vigilar', async () => {
    const { f, eventos, baja } = await conectar(async (_u, init) => canalAbierto(init?.signal))
    baja()
    await vi.advanceTimersByTimeAsync(eventos.VIGILANCIA_MS * 3)
    expect(eventosPedidos(f)).toBe(1)
  })
})

describe('un 401 en el canal', () => {
  it('si la sesión sigue valiendo (el 401 era de mentira) se reconecta', async () => {
    let n = 0
    const { f, eventos, baja } = await conectar(async (url, init) => {
      if (url === '/api/auth/me') return json({ id: 1 })
      return ++n === 1 ? new Response(null, { status: 401 }) : canalAbierto(init?.signal)
    })
    expect(eventosPedidos(f)).toBe(1)

    await vi.advanceTimersByTimeAsync(eventos.ESPERAS_MS[0])
    expect(eventosPedidos(f)).toBe(2)
    expect(eventos.canalVivo()).toBe(true)
    expect(quitados).not.toHaveBeenCalled()           // el token no se toca
    baja()
  })

  it('si la sesión caducó de verdad no insiste y se limpia el token', async () => {
    const { f, eventos, baja } = await conectar(async url =>
      url === '/api/auth/me' ? json({ detail: 'Token inválido' }, 401) : new Response(null, { status: 401 }),
    )
    await vi.advanceTimersByTimeAsync(Math.max(...eventos.ESPERAS_MS) * 2)
    expect(eventosPedidos(f)).toBe(1)
    expect(quitados).toHaveBeenCalled()
    baja()
  })

  it('si /auth/me se queda colgada, la vigilancia la corta y se reintenta', async () => {
    let n = 0
    const { f, eventos, baja } = await conectar((url, init) => {
      if (url === '/api/auth/me') {
        return new Promise<Response>((_resolver, rechazar) => {
          init?.signal?.addEventListener('abort', () => rechazar(new DOMException('abort', 'AbortError')))
        })
      }
      return Promise.resolve(++n === 1 ? new Response(null, { status: 401 }) : canalAbierto(init?.signal))
    })
    expect(eventosPedidos(f)).toBe(1)

    await vi.advanceTimersByTimeAsync(eventos.VIGILANCIA_MS)
    await vi.advanceTimersByTimeAsync(eventos.ESPERAS_MS[0])
    expect(eventosPedidos(f)).toBe(2)
    expect(quitados).not.toHaveBeenCalled()
    baja()
  })

  it('si /auth/me tampoco contesta bien, se reintenta', async () => {
    let n = 0
    const { f, eventos, baja } = await conectar(async (url, init) => {
      if (url === '/api/auth/me') return json({ detail: 'base ocupada' }, 503)
      return ++n === 1 ? new Response(null, { status: 401 }) : canalAbierto(init?.signal)
    })
    await vi.advanceTimersByTimeAsync(eventos.ESPERAS_MS[0])
    expect(eventosPedidos(f)).toBe(2)
    expect(quitados).not.toHaveBeenCalled()
    baja()
  })
})
