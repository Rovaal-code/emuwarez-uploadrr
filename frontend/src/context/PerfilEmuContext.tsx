import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { actualizarEmuPerfil, getEmuPerfil } from '../api/dashboard'
import type { EmuPerfil } from '../types/api'
import { useSync } from './SyncContext'

/**
 * Tu cuenta de eMuwarez, compartida por el Panel y la barra superior: una sola
 * petición para los dos, y «Actualizar» en el Panel cambia también la barra.
 *
 * Se vuelve a pedir con cada aviso de `lastInvalidatedAt` (una sincronización
 * que termina, volver a la pestaña). No gasta llamadas de la clave: el servidor
 * solo va a eMuwarez si lo que tiene guardado pasa de una hora.
 */
interface PerfilEmuValue {
  perfil: EmuPerfil | null
  actualizar: () => Promise<void>
  // El ojo de la barra superior tapa tu usuario de la app y también el de eMuwarez.
  ocultarNombre: boolean
  setOcultarNombre: React.Dispatch<React.SetStateAction<boolean>>
}

const PerfilEmuContext = createContext<PerfilEmuValue>({
  perfil: null, actualizar: async () => {}, ocultarNombre: false, setOcultarNombre: () => {},
})

export function usePerfilEmu(): PerfilEmuValue {
  return useContext(PerfilEmuContext)
}

export function tapar(nombre: string): string {
  return '*'.repeat(Math.max(4, nombre.length))
}

const HIDE_NAME_KEY = 'emuwarez_uploadrr_hide_username'

export function PerfilEmuProvider({ children }: { children: React.ReactNode }) {
  const [perfil, setPerfil] = useState<EmuPerfil | null>(null)
  const { lastInvalidatedAt } = useSync()
  // Persisted so obfuscation survives a reload — the name only reappears when
  // the user explicitly toggles it back on.
  const [ocultarNombre, setOcultarNombre] = useState(() => localStorage.getItem(HIDE_NAME_KEY) === '1')
  useEffect(() => {
    localStorage.setItem(HIDE_NAME_KEY, ocultarNombre ? '1' : '0')
  }, [ocultarNombre])

  // «Actualizar» siempre se aplica; de una lectura, solo la última y si no hubo
  // un «Actualizar» después (la que empezó antes trae lo de antes).
  const ultima = useRef(0)

  useEffect(() => {
    const esta = ++ultima.current
    getEmuPerfil()
      .then(nuevo => { if (esta === ultima.current) setPerfil(nuevo) })
      .catch(() => { /* sin perfil: no se enseña */ })
  }, [lastInvalidatedAt])

  const actualizar = useCallback(async () => {
    ultima.current++
    setPerfil(await actualizarEmuPerfil())
  }, [])

  return (
    <PerfilEmuContext.Provider value={{ perfil, actualizar, ocultarNombre, setOcultarNombre }}>
      {children}
    </PerfilEmuContext.Provider>
  )
}
