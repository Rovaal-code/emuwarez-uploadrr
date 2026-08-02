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
 *
 * QUÉ HACE UNA SECCIÓN OCULTA. Las secciones ya no se desmontan al cambiar de
 * pestaña (ver AppShell), así que hay que decidir qué siguen haciendo cuando
 * nadie las mira. La regla es por lo que cuesta cada cosa:
 *
 *   Avisos de "cambió QUÉ hay"      →  también oculta
 *     Una sincronización que termina, una subida que cambia de estado, una
 *     tarea, una notificación. Son raros —unos pocos por hora—, así que que
 *     las cuatro secciones reaccionen cuesta cuatro peticiones de vez en
 *     cuando. A cambio, cambiar de pestaña enseña lo actual y no lo actual
 *     tras un parpadeo.
 *
 *   Avisos de "cambió CUÁNTO lleva" →  solo a la vista (`soloVisible`)
 *     `subida-progreso` llega cada medio segundo mientras subes. Que Subidas y
 *     el Panel se recarguen los dos por eso estando ocultos duplicaría el
 *     tráfico durante toda la subida, y para nada: a nadie le importa que una
 *     barra que no está mirando vaya al día. Al volver a la sección se ve el
 *     progreso bueno igual, porque el siguiente aviso llega enseguida.
 *
 *   Sondeo de red de seguridad      →  solo a la vista
 *     Es lo único que se multiplica por sección y por segundo. Ocho a la vez
 *     sería peor que lo que había antes de todo esto.
 */
export const CADA_CON_CANAL_MS = 30_000

const AGLUTINAR_MS = 400

/** Cambia QUÉ subidas hay o en qué punto están: importa aunque no se mire. */
export const AVISOS_SUBIDA = ['subida-estado']

/** Cambia CUÁNTO lleva. Cada medio segundo, y solo importa si se está viendo. */
export const AVISOS_SUBIDA_PROGRESO = ['subida-progreso']

interface Opciones {
  /** Cada cuánto repedir cuando NO hay canal. La cadencia de antes. */
  cadaSinCanal: number
  /** Cada cuánto repedir con el canal vivo. Solo es una red de seguridad. */
  cadaConCanal?: number
  /** Si está apagado no se escucha ni se repide. */
  activo?: boolean
  /** Avisos que solo se escuchan mientras la sección está a la vista. Para lo
   *  que llega a chorro y no cambia qué hay, sino cuánto lleva. */
  soloVisible?: string[]
  /** Para descartar avisos de otra cosa (otra subida, otra temporada). */
  filtro?: (aviso: Aviso) => boolean
}

export function useRefrescoPorAvisos(
  tipos: string[],
  recargar: () => void,
  { cadaSinCanal, cadaConCanal = CADA_CON_CANAL_MS, activo = true, filtro, soloVisible = [] }: Opciones,
): { canalVivo: boolean } {
  const [vivo, setVivo] = useState(canalVivo)
  const seVe = useSeccionVisible()
  // En refs para que rehacer el callback o el array en cada render de la
  // página no reinicie el temporizador ni rehaga las suscripciones.
  const recargarRef = useRef(recargar)
  recargarRef.current = recargar
  const filtroRef = useRef(filtro)
  filtroRef.current = filtro
  // Los que se escuchan ahora mismo: siempre los de "qué hay", y los de
  // "cuánto lleva" solo si la sección está a la vista.
  const clave = [...tipos, ...(seVe ? soloVisible : [])].join(',')

  useEffect(() => observarCanal(setVivo), [])

  useEffect(() => {
    if (!activo || !clave) return
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
    if (!activo || !seVe) return
    const t = setInterval(() => recargarRef.current(), vivo ? cadaConCanal : cadaSinCanal)
    return () => clearInterval(t)
  }, [vivo, cadaSinCanal, cadaConCanal, activo, seVe])

  return { canalVivo: vivo }
}

