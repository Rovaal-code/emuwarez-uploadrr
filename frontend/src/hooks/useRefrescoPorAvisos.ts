import { useEffect, useRef, useState } from 'react'
import { canalVivo, observarCanal, suscribirse, type Aviso } from '../api/eventos'
import { useSeccionVisible } from '../context/SeccionVisible'

/**
 * Mantiene una pantalla al día: recarga cuando el servidor avisa, y repide por
 * su cuenta solo como red de seguridad.
 *
 * Antes cada pantalla tenía su `setInterval` y solo se enteraba de lo ocurrido
 * cuando le tocaba preguntar. Eso costaba dos cosas distintas según dónde:
 *
 *   Subidas / Panel      la barra avanzaba a saltos de 2,5 s, y una subida
 *                        larga eran unas 24 peticiones por minuto y pantalla
 *   Campana / Tareas     una notificación podía tardar medio minuto en salir
 *
 * Los sondeos NO desaparecen, se ralentizan mientras el canal está vivo y
 * vuelven a su cadencia de siempre si se cae. Un canal caído tiene que costar
 * latencia, no dejar la pantalla congelada enseñando una subida al 45% que
 * terminó hace diez minutos.
 *
 * Las recargas se aglutinan porque varios avisos llegan casi a la vez y piden
 * lo mismo: los tres de una subida (estado, progreso, registro) van juntos.
 */
export const CADA_CON_CANAL_MS = 30_000

const AGLUTINAR_MS = 400

/** Los tres avisos de una subida. El del registro se pide aparte porque solo
 *  le importa a quien tenga abierto el detalle de un trabajo. */
export const AVISOS_SUBIDA = ['subida-estado', 'subida-progreso']

interface Opciones {
  /** Cada cuánto repedir cuando NO hay canal. La cadencia de antes. */
  cadaSinCanal: number
  /** Cada cuánto repedir con el canal vivo. Solo es una red de seguridad. */
  cadaConCanal?: number
  /** Si está apagado no se escucha ni se repide. */
  activo?: boolean
  /** Para descartar avisos de otra cosa (otra subida, otra temporada). */
  filtro?: (aviso: Aviso) => boolean
}

export function useRefrescoPorAvisos(
  tipos: string[],
  recargar: () => void,
  { cadaSinCanal, cadaConCanal = CADA_CON_CANAL_MS, activo = true, filtro }: Opciones,
): { canalVivo: boolean } {
  const [vivo, setVivo] = useState(canalVivo)
  // Las secciones se quedan montadas al cambiar de pestaña, así que "montada"
  // ya no quiere decir "a la vista". Ocho repidiendo a la vez sería peor que
  // lo que había antes de todo esto.
  const seVe = useSeccionVisible()
  activo = activo && seVe
  // En refs para que rehacer el callback o el array en cada render de la
  // página no reinicie el temporizador ni rehaga las suscripciones.
  const recargarRef = useRef(recargar)
  recargarRef.current = recargar
  const filtroRef = useRef(filtro)
  filtroRef.current = filtro
  const clave = tipos.join(',')

  useEffect(() => observarCanal(setVivo), [])

  useEffect(() => {
    if (!activo) return
    let pendiente: ReturnType<typeof setTimeout> | null = null
    const pedirRecarga = (aviso: Aviso) => {
      if (filtroRef.current && !filtroRef.current(aviso)) return
      if (pendiente) return
      pendiente = setTimeout(() => { pendiente = null; recargarRef.current() }, AGLUTINAR_MS)
    }
    const cortes = clave.split(',').map(tipo => suscribirse(tipo, pedirRecarga))
    return () => {
      if (pendiente) clearTimeout(pendiente)
      cortes.forEach(cortar => cortar())
    }
  }, [activo, clave])

  useEffect(() => {
    if (!activo) return
    const t = setInterval(() => recargarRef.current(), vivo ? cadaConCanal : cadaSinCanal)
    return () => clearInterval(t)
  }, [vivo, cadaSinCanal, cadaConCanal, activo])

  return { canalVivo: vivo }
}


/**
 * Recarga la sección cuando vuelve a verse, si algo la dejó desfasada mientras
 * estaba oculta.
 *
 * Con las secciones montadas siempre, `lastInvalidatedAt` ya no puede provocar
 * una recarga inmediata en todas: si estás en Subidas y termina una
 * sincronización, Biblioteca no tiene que ponerse a rehacer 20.000 filas que
 * nadie mira. Se apunta que hay que hacerlo y se hace al volver a ella.
 *
 * Y NO se recarga por el simple hecho de volver: si nada avisó de que algo
 * cambió, lo que hay en pantalla sigue siendo bueno. Eso es lo que hace que
 * cambiar de pestaña sea instantáneo de verdad y no "instantáneo y luego un
 * parpadeo". Se puede confiar en ello porque ahora el servidor avisa de todo
 * lo que se mueve (ver services/eventos.py).
 */
export function useRecargarAlVerse(recargar: () => void, marca: number): void {
  const seVe = useSeccionVisible()
  const recargarRef = useRef(recargar)
  recargarRef.current = recargar
  // La marca con la que ya está al día. Arranca en la actual: recién montada,
  // la sección acaba de pedir sus datos y no debe a nadie.
  const alDiaCon = useRef(marca)

  useEffect(() => {
    if (!seVe || marca === alDiaCon.current) return
    alDiaCon.current = marca
    recargarRef.current()
  }, [seVe, marca])
}
