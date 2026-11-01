import { useState } from 'react'
import { getInstances } from '../api/instances'
import type { InstanceSafeResponse } from '../types/api'
import { useAlEntrar } from '../context/SeccionVisible'

/**
 * Las instancias de Radarr/Sonarr, para los enlaces «Abrir en Radarr/Sonarr».
 *
 * Se vuelven a pedir cada vez que se entra en la sección: las secciones se quedan
 * montadas, y Instancias se edita en otra, así que pedirlas solo al montar dejaba
 * enlaces con la URL de antes de renombrar o reapuntar una instancia.
 */
export function useInstancias(): InstanceSafeResponse[] {
  const [instancias, setInstancias] = useState<InstanceSafeResponse[]>([])
  useAlEntrar(() => { getInstances().then(setInstancias).catch(() => {}) })
  return instancias
}
