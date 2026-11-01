// Registro de «cambios sin guardar»: cada formulario registra una función que dice si tiene cambios, y la
// navegación (barra lateral, pestañas de Configuración, Atrás/Adelante, campana, cerrar la pestaña) pregunta
// antes de salir si alguna dice que sí.
//
// La confirmación es un modal: el anfitrión (AppShell) registra con `setLeavePrompt` quien lo abre, y
// `guardedLeave(proceed)` ejecuta `proceed` al momento si no hay cambios, o abre el modal y lo ejecuta al confirmar.
import { useEffect, useRef } from 'react'

let opener: ((proceed: () => void) => void) | null = null
const registro = new Map<string, () => boolean>()

// Devuelve la función que lo quita. Con el mismo id gana el último registro, y quitar uno viejo no quita el nuevo.
export function registerDirty(id: string, fn: () => boolean): () => void {
  registro.set(id, fn)
  return () => { if (registro.get(id) === fn) registro.delete(id) }
}

export function hasUnsavedChanges(): boolean {
  for (const fn of registro.values()) if (fn()) return true
  return false
}

// Registra mientras el componente está montado; `dirty` se lee en el momento de preguntar.
export function useUnsavedGuard(id: string, dirty: boolean): void {
  const actual = useRef(dirty)
  actual.current = dirty
  useEffect(() => registerDirty(id, () => actual.current), [id])
}

export function setLeavePrompt(fn: ((proceed: () => void) => void) | null): void {
  opener = fn
}

export function guardedLeave(proceed: () => void): void {
  if (!hasUnsavedChanges()) {
    proceed()
    return
  }
  if (opener) {
    opener(proceed)
  } else if (window.confirm('Tienes cambios sin guardar. ¿Salir y descartarlos?')) {
    proceed()
  }
}
