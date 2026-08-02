import { createContext, useContext } from 'react'

/**
 * Si la sección que envuelve es la que se está viendo ahora mismo.
 *
 * Hace falta porque las secciones ya no se desmontan al cambiar de pestaña
 * (ver AppShell): se quedan montadas y ocultas, que es lo que hace que volver
 * a una sea instantáneo. Pero "montada" ya no significa "a la vista", y hay
 * cosas que solo deben pasar cuando de verdad se está mirando:
 *
 *   - repedir datos. Ocho secciones montadas repidiendo a la vez sería peor
 *     que lo que había antes de todo esto.
 *   - recargar porque algo cambió. Si estás en Subidas y termina una
 *     sincronización, Biblioteca no tiene que ponerse a recargar 20.000 filas
 *     que nadie está mirando: le basta con hacerlo cuando vuelvas a ella.
 */
const SeccionVisibleContext = createContext(true)

export function useSeccionVisible(): boolean {
  return useContext(SeccionVisibleContext)
}

export function SeccionVisible({ visible, children }: { visible: boolean; children: React.ReactNode }) {
  return (
    <SeccionVisibleContext.Provider value={visible}>
      {children}
    </SeccionVisibleContext.Provider>
  )
}
