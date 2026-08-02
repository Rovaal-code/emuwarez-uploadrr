/**
 * El canal por el que el servidor avisa de que algo ha cambiado.
 *
 * La interfaz preguntaba cada pocos segundos en once sitios distintos. Esto es
 * el camino contrario: una conexión abierta por la que el servidor escribe
 * cuando pasa algo de verdad.
 *
 * Las pantallas que ya lo usan NO dejan de repedir: bajan a un sondeo lento de
 * red de seguridad mientras el canal está vivo, y vuelven al rápido si se cae
 * (ver `canalVivo`). Un canal caído tiene que costar latencia, no dejar la
 * pantalla congelada enseñando una subida al 45% que terminó hace diez
 * minutos.
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
 *
 * Uso directo solo desde `suscribirse`, que es quien se encarga de que haya UNA
 * conexión para toda la aplicación y no una por pantalla.
 */
function escucharEventos(alRecibir: (aviso: Aviso) => void): () => void {
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
      marcarVivo(true)
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
    marcarVivo(false)         // las pantallas vuelven al sondeo rápido
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

// ─────────────────────────────────────────────────────────────────────────────
// Una sola conexión para toda la aplicación
// ─────────────────────────────────────────────────────────────────────────────
//
// Varias pantallas quieren enterarse a la vez (la tabla de Subidas, el Panel,
// el detalle de un trabajo). Si cada una abriera la suya, un navegador tendría
// cuatro conexiones abiertas contra el mismo servidor para recibir lo mismo —
// y Chrome corta a seis por dominio, así que el resto de la aplicación se
// quedaría sin poder pedir nada.
//
// Así que la conexión es una, se abre con el primer suscriptor y se cierra con
// el último.

type Oyente = (aviso: Aviso) => void

const oyentes = new Map<string, Set<Oyente>>()
let cortarConexion: (() => void) | null = null

// Si el canal está dando servicio ahora mismo. Las pantallas lo miran para
// decidir cada cuánto repiden por su cuenta: con el canal vivo basta una red de
// seguridad lenta; sin él hay que volver al sondeo rápido de siempre, porque es
// lo único que queda.
let vivo = false
const oyentesDeEstado = new Set<(vivo: boolean) => void>()

function marcarVivo(nuevo: boolean): void {
  if (vivo === nuevo) return
  vivo = nuevo
  for (const cb of oyentesDeEstado) {
    try { cb(vivo) } catch { /* un oyente roto no tumba a los demás */ }
  }
}

export function canalVivo(): boolean {
  return vivo
}

/** Avisa cuando el canal se cae o vuelve. Devuelve cómo dejar de escuchar. */
export function observarCanal(cb: (vivo: boolean) => void): () => void {
  oyentesDeEstado.add(cb)
  return () => { oyentesDeEstado.delete(cb) }
}

function repartir(aviso: Aviso): void {
  for (const cb of oyentes.get(aviso.tipo) ?? []) {
    try { cb(aviso) } catch { /* un oyente roto no corta el canal */ }
  }
}

/**
 * Escucha un tipo de aviso. Devuelve cómo dejar de escuchar, que hay que
 * llamar al desmontar.
 */
export function suscribirse(tipo: string, cb: Oyente): () => void {
  let conjunto = oyentes.get(tipo)
  if (!conjunto) { conjunto = new Set(); oyentes.set(tipo, conjunto) }
  conjunto.add(cb)
  if (!cortarConexion) cortarConexion = escucharEventos(repartir)

  return () => {
    conjunto!.delete(cb)
    if (conjunto!.size === 0) oyentes.delete(tipo)
    if (oyentes.size === 0 && cortarConexion) {
      cortarConexion()
      cortarConexion = null
      marcarVivo(false)
    }
  }
}

/**
 * Sigue el progreso de una operación mientras dura, y devuelve cómo dejar de
 * seguirla.
 *
 * Es para los sondeos del asistente, que tienen otra forma que los de las
 * pantallas: no corren siempre, corren mientras una petición larga está en
 * vuelo (verificar un elemento, planear un pack de temporada). Eran los dos
 * más agresivos que había —cada 0,4 y 0,5 segundos— y encima disparaban justo
 * cuando el servidor estaba ocupado con el trabajo pesado.
 *
 * Igual que en las pantallas, el sondeo no desaparece: con el canal vivo baja a
 * una red de seguridad lenta, y sin él vuelve a su cadencia de siempre. Aquí
 * importa más que en ningún otro sitio, porque el usuario está mirando la
 * barra y esperando.
 */
export function seguirProgreso(
  tipo: string,
  coincide: (aviso: Aviso) => boolean,
  pedir: () => void,
  cadaSinCanal: number,
): () => void {
  const LENTO_MS = 5000
  let temporizador: ReturnType<typeof setInterval> | null = null

  const reprogramar = (vivo: boolean) => {
    if (temporizador) clearInterval(temporizador)
    temporizador = setInterval(pedir, vivo ? LENTO_MS : cadaSinCanal)
  }
  reprogramar(canalVivo())

  const dejarDeObservar = observarCanal(reprogramar)
  const dejarDeEscuchar = suscribirse(tipo, aviso => { if (coincide(aviso)) pedir() })

  return () => {
    if (temporizador) clearInterval(temporizador)
    dejarDeObservar()
    dejarDeEscuchar()
  }
}
