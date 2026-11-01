import { useState, useEffect, useCallback, useRef, createContext, useContext } from 'react'
import { useTooltip } from '../../components/Tooltip'

export type TonoMensaje = 'ok' | 'error' | 'aviso'

export type SettingsMsg = {
  text: string
  tono: TonoMensaje
  // Un mensaje permanente describe un ESTADO que sigue siendo cierto (hay una
  // versión nueva), no algo que acaba de pasar. No se borra solo; si mientras
  // tanto ocurre algo (guardas, creas un backup), ese aviso pasa por delante
  // unos segundos y luego vuelve el permanente.
  permanente?: boolean
} | null

// Todos los avisos de esta página (guardado, backups, mantenimiento, errores)
// salen en la misma fila que las pestañas, a la derecha. Antes cada pestaña
// pintaba su propio bloque arriba del todo, que empujaba las tarjetas hacia
// abajo al aparecer y las devolvía a su sitio al irse: el contenido daba un
// salto justo cuando acabas de pulsar un botón. Desde la fila de pestañas no
// mueve nada.
export interface OpcionesMensaje {
  tono?: TonoMensaje
  permanente?: boolean
  // Borra el permanente que hubiera. Lo usa la comprobación de versión cuando
  // pasa a "al día": sin esto, el aviso de versión nueva de la comprobación
  // anterior seguía debajo y reaparecía al caducar el pasajero, diciendo que
  // hay novedad cuando ya no la hay.
  borrarPermanente?: boolean
}

export const SettingsMessageContext = createContext<
  (ok: boolean, text: string, opciones?: OpcionesMensaje) => void
>(() => {})

export function useSettingsMessage() {
  return useContext(SettingsMessageContext)
}

// Misma firma que el useState que sustituye (`setMsg({ ok, text })` y
// `setMsg(null)`), para no tocar los sitios que ya avisaban: lo único que
// cambia es dónde sale el aviso.
export function useSettingsMessageAdapter() {
  const show = useSettingsMessage()
  return useCallback(
    (m: { ok: boolean; text: string } | null) => { if (m) show(m.ok, m.text) },
    [show],
  )
}

// El aviso ocupa el hueco que sobra a la derecha de las pestañas y se recorta
// con puntos suspensivos: un error de backup puede ser una frase larga y no
// puede desmontar la fila. El texto completo sale al pasar el ratón.
export function SettingsMessageSlot({ msg }: { msg: SettingsMsg }) {
  const ref = useRef<HTMLSpanElement>(null)
  const [recortado, setRecortado] = useState(false)
  // El tooltip solo tiene sentido si falta texto por ver: repetir un aviso que
  // ya se lee entero solo estorba.
  useEffect(() => {
    const el = ref.current
    setRecortado(!!el && el.scrollWidth > el.clientWidth)
  }, [msg?.text])
  const { triggerProps, tooltipNode } = useTooltip(recortado ? msg?.text ?? null : null)
  if (!msg) return null
  const colores: Record<TonoMensaje, { texto: string; fondo: string; borde: string }> = {
    ok: { texto: 'var(--color-available)', fondo: 'color-mix(in srgb, var(--color-available) 10%, transparent)', borde: 'color-mix(in srgb, var(--color-available) 30%, transparent)' },
    error: { texto: 'var(--color-error)', fondo: 'color-mix(in srgb, var(--color-error) 10%, transparent)', borde: 'color-mix(in srgb, var(--color-error) 30%, transparent)' },
    aviso: { texto: 'var(--color-warning)', fondo: 'color-mix(in srgb, var(--color-warning) 10%, transparent)', borde: 'color-mix(in srgb, var(--color-warning) 30%, transparent)' },
  }
  const c = colores[msg.tono]
  return (
    <span
      ref={ref}
      className="aj-mensaje"
      style={{ background: c.fondo, border: `1px solid ${c.borde}`, color: c.texto }}
      {...triggerProps}
    >
      {msg.text}
      {tooltipNode}
    </span>
  )
}
