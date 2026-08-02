import { useEffect, useState } from 'react'

/**
 * True solo si algo lleva tardando más de la cuenta.
 *
 * Sirve para no avisar de esperas que no se llegan a notar. Filtrar u ordenar
 * tarda unos milisegundos, así que apagar la tabla o cambiarla por un
 * "Cargando…" en cuanto empieza la petición se ve como un parpadeo: molesta
 * más que la propia espera, y encima da la sensación de que la aplicación va
 * lenta justo cuando va rápida.
 *
 * Con esto no pasa nada en el caso normal, y el aviso aparece solo cuando la
 * espera es real (una biblioteca enorme, el servidor atascado) — que es cuando
 * hace falta, porque si no parecería que el clic no ha hecho nada.
 */
export const UMBRAL_MS = 250

export function useTardanza(esperando: boolean, umbral: number = UMBRAL_MS): boolean {
  const [tarda, setTarda] = useState(false)

  useEffect(() => {
    if (!esperando) { setTarda(false); return }
    const t = setTimeout(() => setTarda(true), umbral)
    return () => clearTimeout(t)
  }, [esperando, umbral])

  return tarda
}
