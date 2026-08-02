/**
 * El canal por el que el servidor avisa de que algo ha cambiado.
 *
 * La interfaz pregunta cada pocos segundos en once sitios distintos. Esto es
 * el camino contrario: una conexión abierta por la que el servidor escribe
 * cuando pasa algo de verdad. De momento solo llega `sync-terminada`; el resto
 * de sondeos siguen intactos, así que si este canal no funciona no se rompe
 * nada — solo se vuelve a depender de lo que ya había.
 *
 * NO se usa `EventSource`, que sería lo natural, porque no sabe mandar
 * cabeceras y aquí se autentica con `Authorization: Bearer`. La otra salida
 * era meter el token en la URL, y ahí acaba en los registros del servidor y en
 * el historial del navegador. Así que `fetch` leyendo la respuesta a trozos, y
 * la reconexión —que `EventSource` regala— hay que escribirla: es lo de abajo.
 */
import { getToken } from './client'

export interface Aviso {
  tipo: string
  [clave: string]: unknown
}

/** Lo que se espera antes de reintentar, en cada intento seguido que falla. Se
 *  va abriendo para no machacar un servidor que está caído, y se para en 30 s
 *  para que volver no tarde una eternidad cuando vuelva. */
export const ESPERAS_MS = [1000, 2000, 5000, 10_000, 30_000]

export function esperaDelIntento(intento: number): number {
  return ESPERAS_MS[Math.min(intento, ESPERAS_MS.length - 1)]
}

/**
 * Saca los avisos completos de lo que se lleva leído.
 *
 * Un trozo de red no respeta las fronteras de los mensajes: puede traer dos
 * avisos juntos, o la mitad de uno. Por eso esto devuelve también el `resto`,
 * que es lo que hay que conservar para pegarle el siguiente trozo. Sin esto,
 * un aviso partido en dos se pierde y —peor— deja el flujo descolocado.
 *
 * Las líneas que empiezan por ':' son comentarios de SSE (los latidos) y se
 * ignoran, que es justo para lo que sirven.
 */
export function extraerAvisos(acumulado: string): { avisos: Aviso[]; resto: string } {
  const partes = acumulado.split('\n\n')
  const resto = partes.pop() ?? ''
  const avisos: Aviso[] = []
  for (const bloque of partes) {
    for (const linea of bloque.split('\n')) {
      if (!linea.startsWith('data:')) continue
      try {
        const aviso = JSON.parse(linea.slice(5).trim())
        if (aviso && typeof aviso.tipo === 'string') avisos.push(aviso as Aviso)
      } catch {
        // Un aviso ilegible se tira y ya. Solo dicen "recarga", así que
        // perderse uno cuesta enterarse por el sondeo de siempre.
      }
    }
  }
  return { avisos, resto }
}

/**
 * Se conecta y llama a `alRecibir` con cada aviso. Devuelve la función para
 * cortar, que hay que llamar al desmontar.
 *
 * Se reconecta sola salvo en dos casos: que la corten a propósito, o que el
 * servidor conteste 401 — ahí el token ya no vale y reintentar sería aporrear
 * la puerta.
 */
export function escucharEventos(alRecibir: (aviso: Aviso) => void): () => void {
  let cortado = false
  let intento = 0
  let control: AbortController | null = null
  let reintento: ReturnType<typeof setTimeout> | null = null

  const conectar = async (): Promise<void> => {
    if (cortado) return
    const token = getToken()
    if (!token) { programarReintento(); return }

    control = new AbortController()
    try {
      const respuesta = await fetch('/api/eventos', {
        headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
        signal: control.signal,
      })
      if (respuesta.status === 401) return          // sesión caducada: no insistir
      if (!respuesta.ok || !respuesta.body) { programarReintento(); return }

      // Conectados. Se reinicia la cuenta para que la siguiente caída vuelva a
      // reintentar rápido, en vez de arrastrar la espera larga de la anterior.
      intento = 0
      const lector = respuesta.body.getReader()
      const decodificador = new TextDecoder()
      let acumulado = ''
      for (;;) {
        const { done, value } = await lector.read()
        if (done) break
        acumulado += decodificador.decode(value, { stream: true })
        const { avisos, resto } = extraerAvisos(acumulado)
        acumulado = resto
        for (const aviso of avisos) {
          try { alRecibir(aviso) } catch { /* un fallo pintando no corta el canal */ }
        }
      }
      programarReintento()                          // el servidor cerró
    } catch {
      // Cortada a propósito, red caída, servidor reiniciándose: todo se trata
      // igual, esperar y volver a intentarlo.
      programarReintento()
    }
  }

  const programarReintento = (): void => {
    if (cortado) return
    const espera = esperaDelIntento(intento++)
    reintento = setTimeout(() => { void conectar() }, espera)
  }

  void conectar()

  return () => {
    cortado = true
    if (reintento) clearTimeout(reintento)
    control?.abort()
  }
}
