import { createContext, useContext, useEffect, useRef } from 'react'
import { SyncContext, useSync } from './SyncContext'

/**
 * Si la sección que envuelve es la que se está viendo ahora mismo.
 *
 * Hace falta porque las secciones ya no se desmontan al cambiar de pestaña
 * (ver AppShell): se quedan montadas y ocultas, que es lo que hace que volver
 * a una sea instantáneo. Pero "montada" ya no significa "a la vista", y hay
 * cosas que solo deben pasar cuando de verdad se está mirando:
 *
 *   - repedir datos. Ocho secciones montadas repidiendo a la vez sería peor
 *     que lo que había antes de todo esto (ver `SeccionVisible` más abajo).
 *   - recoger un salto a un contenido concreto (ver `useAlEntrar`).
 *   - reiniciarse al salir (ver `useAlSalir`).
 */
const SeccionVisibleContext = createContext(true)

export function useSeccionVisible(): boolean {
  return useContext(SeccionVisibleContext)
}

/**
 * Además, la marca `lastInvalidatedAt` que ve la sección solo avanza mientras se
 * ve. Cada vez que vuelves a la pestaña del navegador sube la marca, y con las
 * nueve secciones montadas eso recargaba Biblioteca (20.000 filas), Peticiones
 * y el Panel aunque estuvieran ocultas. Con la marca congelada, una sección
 * oculta recarga UNA vez al volver a verse, y solo si algo cambió mientras tanto.
 */
export function SeccionVisible({ visible, children }: { visible: boolean; children: React.ReactNode }) {
  const sync = useSync()
  const marca = useRef(sync.lastInvalidatedAt)
  if (visible) marca.current = sync.lastInvalidatedAt
  const valor = marca.current === sync.lastInvalidatedAt ? sync : { ...sync, lastInvalidatedAt: marca.current }
  return (
    <SeccionVisibleContext.Provider value={visible}>
      <SyncContext.Provider value={valor}>
        {children}
      </SyncContext.Provider>
    </SeccionVisibleContext.Provider>
  )
}

/**
 * Corre cada vez que la sección pasa a verse, incluida la primera.
 *
 * Es donde va lo que antes iba en un efecto de montaje y dejó de funcionar al
 * quedarse las secciones montadas: recoger un salto a un contenido concreto
 * ("Ver en Biblioteca" desde una petición, un aviso de la campana...). Eso se
 * apunta en sessionStorage y se recoge en el destino; montándose una sola vez
 * —y encima al arrancar la aplicación, cuando aún no hay nada apuntado— el
 * destino no volvía a mirar nunca, así que cambiaba de sección y ya está.
 */
export function useAlEntrar(hacer: () => void): void {
  const seVe = useSeccionVisible()
  const hacerRef = useRef(hacer)
  hacerRef.current = hacer
  useEffect(() => { if (seVe) hacerRef.current() }, [seVe])
}

/**
 * Corre cada vez que la sección deja de verse.
 *
 * Sirve para devolverla a su estado de partida: la tabla, sin filtros y con el
 * orden por defecto. Al SALIR y no al entrar, y esto importa: reiniciando al
 * entrar se borraría justo el contenido al que te acaban de mandar desde otra
 * sección, que es lo que `useAlEntrar` acaba de poner.
 */
export function useAlSalir(hacer: () => void): void {
  const seVe = useSeccionVisible()
  const hacerRef = useRef(hacer)
  hacerRef.current = hacer
  const seVeiaAntes = useRef(seVe)
  useEffect(() => {
    if (seVeiaAntes.current && !seVe) hacerRef.current()
    seVeiaAntes.current = seVe
  }, [seVe])
}
