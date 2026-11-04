import { useCallback, useEffect, useRef, useState } from 'react'

// Mismo corte que el @media de la barra lateral en layout.css.
const CONSULTA_MOVIL = '(max-width: 768px)'

/** En ventanas estrechas la barra lateral es un cajón: abrir, cerrar con Escape y devolver el foco al botón. */
export function useMenuMovil() {
  const [movil, setMovil] = useState(() => window.matchMedia?.(CONSULTA_MOVIL).matches ?? false)
  const [abierto, setAbierto] = useState(false)
  const botonRef = useRef<HTMLButtonElement>(null)
  const estabaAbierto = useRef(false)

  useEffect(() => {
    const consulta = window.matchMedia?.(CONSULTA_MOVIL)
    if (!consulta) return
    const alCambiar = () => setMovil(consulta.matches)
    consulta.addEventListener('change', alCambiar)
    return () => consulta.removeEventListener('change', alCambiar)
  }, [])

  const visible = movil && abierto
  const cerrar = useCallback(() => setAbierto(false), [])
  const alternar = useCallback(() => setAbierto(a => !a), [])

  useEffect(() => {
    if (!visible) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') cerrar() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [visible, cerrar])

  // Al cerrar, el foco vuelve al botón que lo abrió (después de pintar: antes seguía inerte).
  useEffect(() => {
    if (estabaAbierto.current && !visible) botonRef.current?.focus()
    estabaAbierto.current = visible
  }, [visible])

  return { movil, abierto: visible, cerrar, alternar, botonRef }
}
