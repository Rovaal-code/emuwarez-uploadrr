import { useEffect, useRef, useState } from 'react'
import { canalVivo, observarCanal, suscribirse, type Aviso } from '../api/eventos'

/**
 * Mantiene al día una pantalla de subidas: recarga cuando el servidor avisa, y
 * repide por su cuenta solo como red de seguridad.
 *
 * Antes cada una tenía su `setInterval` de 2 o 2,5 segundos. Ya estaban
 * condicionados a que hubiera algún trabajo vivo, así que el ahorro con la
 * aplicación quieta no es la parte interesante: lo que cambia es lo que pasa
 * MIENTRAS se sube. Una subida larga son unas 24 peticiones por minuto y por
 * pantalla abierta, y la barra avanzaba a saltos de 2,5 segundos porque solo
 * se enteraba de lo ocurrido cuando le tocaba preguntar. Ahora se mueve cuando
 * se mueve.
 *
 * Los sondeos NO desaparecen, se ralentizan. Un canal caído tiene que costar
 * latencia, no dejar la pantalla congelada enseñando una subida al 45% que
 * terminó hace diez minutos:
 *
 *   canal vivo   →  cada 30 s   (por si se perdió un aviso)
 *   canal caído  →  el de siempre
 *
 * Las recargas se aglutinan porque los tres avisos de una subida (estado,
 * progreso, registro) llegan casi a la vez y piden lo mismo.
 */
export const CADA_CON_CANAL_MS = 30_000

const AGLUTINAR_MS = 400

/** Los avisos de una subida. 'subida-log' solo interesa a quien mira el
 *  registro de un trabajo concreto, así que se pide aparte. */
const AVISOS_BASE = ['subida-estado', 'subida-progreso']

export function useRefrescoDeSubidas(
  recargar: () => void,
  {
    cadaSinCanal,
    activo = true,
    jobId,
    conRegistro = false,
  }: { cadaSinCanal: number; activo?: boolean; jobId?: number; conRegistro?: boolean },
): { canalVivo: boolean } {
  const [vivo, setVivo] = useState(canalVivo)
  // Se guarda en una ref para que cambiar de callback (se rehace en cada render
  // de la página) no reinicie el temporizador ni rehaga las suscripciones.
  const recargarRef = useRef(recargar)
  recargarRef.current = recargar

  useEffect(() => observarCanal(setVivo), [])

  useEffect(() => {
    if (!activo) return
    let pendiente: ReturnType<typeof setTimeout> | null = null
    const pedirRecarga = (aviso: Aviso) => {
      // Con varias subidas a la vez, el detalle de una no se recarga porque
      // otra distinta esté avanzando.
      if (jobId !== undefined && aviso.job_id !== jobId) return
      if (pendiente) return
      pendiente = setTimeout(() => { pendiente = null; recargarRef.current() }, AGLUTINAR_MS)
    }
    const tipos = conRegistro ? [...AVISOS_BASE, 'subida-log'] : AVISOS_BASE
    const cortes = tipos.map(tipo => suscribirse(tipo, pedirRecarga))
    return () => {
      if (pendiente) clearTimeout(pendiente)
      cortes.forEach(cortar => cortar())
    }
  }, [activo, jobId, conRegistro])

  useEffect(() => {
    if (!activo) return
    const cada = vivo ? CADA_CON_CANAL_MS : cadaSinCanal
    const t = setInterval(() => recargarRef.current(), cada)
    return () => clearInterval(t)
  }, [vivo, cadaSinCanal, activo])

  return { canalVivo: vivo }
}
