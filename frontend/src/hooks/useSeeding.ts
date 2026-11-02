import { useCallback, useEffect, useRef, useState } from 'react'
import { getSeeding, type SeedingResponse } from '../api/seeding'

export interface SeedingEstado {
  // null: aún sin respuesta, o el servidor no contestó (la interfaz dice «Sin datos de qBittorrent»).
  datos: SeedingResponse | null
  cargando: boolean
  cargar: (forzar?: boolean) => void
}

// Lee el seeding al entrar y cuando se pide («Actualizar»); nunca por reloj. Un fallo no rompe nada: deja datos a null.
export function useSeeding(): SeedingEstado {
  const [datos, setDatos] = useState<SeedingResponse | null>(null)
  const [cargando, setCargando] = useState(false)
  const vivo = useRef(true)
  const ultima = useRef(0)

  const cargar = useCallback((forzar = false) => {
    const n = ++ultima.current
    setCargando(true)
    getSeeding(forzar)
      .then(d => { if (vivo.current && n === ultima.current) setDatos(d) })
      .catch(() => { if (vivo.current && n === ultima.current) setDatos(null) })
      .finally(() => { if (vivo.current && n === ultima.current) setCargando(false) })
  }, [])

  useEffect(() => {
    vivo.current = true
    cargar()
    return () => { vivo.current = false }
  }, [cargar])

  return { datos, cargando, cargar }
}
