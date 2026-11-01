// Una lista que se consulta al servidor y se toca en local antes de que
// conteste (marcar como leído, borrar): la campana de notificaciones.
//
// - Solo cuenta la última consulta, y una acción local también tira las que
//   iban en vuelo: una respuesta anterior al cambio devolvería lo que se acaba
//   de borrar. Como esa consulta ya no se aplicará, se repite al acabar.
// - Mientras haya alguna acción en marcha, ninguna consulta pisa la lista: se
//   apunta y se consulta una vez cuando terminan todas.
// - Cada acción espera como mucho `topeMs`: una petición colgada no puede
//   dejar la lista sin consultar para siempre. Pasado el tope se da por
//   acabada y se consulta, que es lo que dice cómo quedó de verdad.

export const TOPE_ACCION_MS = 15_000

export const AGOTADO: unique symbol = Symbol('agotado')

/** `promesa`, o AGOTADO si tarda más de `ms`. Un fallo antes del tope se propaga. */
export function conTope<T>(promesa: Promise<T>, ms: number): Promise<T | typeof AGOTADO> {
  let reloj: ReturnType<typeof setTimeout> | undefined
  const tope = new Promise<typeof AGOTADO>(resolve => { reloj = setTimeout(() => resolve(AGOTADO), ms) })
  return Promise.race([promesa, tope]).finally(() => clearTimeout(reloj))
}

export interface AccionesOptimistas {
  refrescar(): Promise<void>
  accion(optimista: () => void, llamada: () => Promise<unknown>): Promise<void>
}

export function accionesOptimistas<T>(
  consultar: () => Promise<T>,
  aplicar: (resultado: T) => void,
  topeMs = TOPE_ACCION_MS,
): AccionesOptimistas {
  let enCurso = 0
  let consultasEnVuelo = 0
  let recargarAlAcabar = false
  let ultima = 0

  const refrescar = async (): Promise<void> => {
    if (enCurso > 0) { recargarAlAcabar = true; return }
    const esta = ++ultima
    consultasEnVuelo++
    try {
      const r = await consultar()
      if (esta === ultima) aplicar(r)
    } catch {
      /* no bloquea: la lista se queda como está */
    } finally {
      consultasEnVuelo--
    }
  }

  const accion = async (optimista: () => void, llamada: () => Promise<unknown>): Promise<void> => {
    // Invalida la consulta en vuelo; si había una, se repite al acabar para no perderla.
    if (consultasEnVuelo > 0) recargarAlAcabar = true
    ultima++
    optimista()
    enCurso++
    try {
      // Si falla, o se agota el tope, la lista ya no tiene por qué coincidir con el servidor.
      if (await conTope(llamada(), topeMs) === AGOTADO) recargarAlAcabar = true
    } catch {
      recargarAlAcabar = true
    } finally {
      enCurso--
      if (enCurso === 0 && recargarAlAcabar) {
        recargarAlAcabar = false
        void refrescar()
      }
    }
  }

  return { refrescar, accion }
}
