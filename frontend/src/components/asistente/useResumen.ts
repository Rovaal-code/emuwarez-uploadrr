// Lo que el Resumen pide fuera del asistente: si el catálogo local ya tiene lo que se sube y qué petición cubre.
import { useEffect, useState } from 'react'
import { getEmuComparison, getEmuSyncStatus, getLibraryItem } from '../../api/library'
import { getRequestDetail } from '../../api/requests'
import { resumirComparaciones, textoPeticion, type PeticionResumen, type YaHay } from '../../utils/resumenSubida'

export function useResumen({ ids, tuya, requestId, cubiertos, alcance }: {
  ids: readonly number[]
  // Lo que irá en el nombre; solo con un elemento (en una tanda cada uno lleva el suyo).
  tuya?: { resolution?: string | null; source?: string | null }
  requestId?: number
  // Cuántos de `ids` cubre la petición de la que se abrió el asistente.
  cubiertos: number
  // Una frase del tipo «esta temporada»; null en una tanda, donde no se mira si hay otra abierta.
  alcance: string | null
}) {
  const [yaHay, setYaHay] = useState<YaHay>({ estado: 'cargando' })
  const [sincronizado, setSincronizado] = useState<string | null>(null)
  const [peticion, setPeticion] = useState<PeticionResumen | null>(null)
  const clave = ids.join(',')

  useEffect(() => {
    if (ids.length === 0) return
    let vivo = true
    setYaHay({ estado: 'cargando' })
    Promise.all([
      Promise.all(ids.map(id => getEmuComparison(id, tuya).catch(() => null))),
      getEmuSyncStatus().then(s => s.last_sync_at).catch(() => null),
    ]).then(([comparaciones, sync]) => {
      if (!vivo) return
      setYaHay(resumirComparaciones(comparaciones))
      setSincronizado(sync)
    })
    return () => { vivo = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- se pide al entrar en el paso o cambiar lo que se sube, no con cada pintado
  }, [clave, tuya?.resolution, tuya?.source])

  useEffect(() => {
    if (ids.length === 0) return
    let vivo = true
    setPeticion(null)
    const pedir = async (): Promise<PeticionResumen> => {
      const sinAlcance = alcance ?? 'estos elementos'
      if (requestId != null && cubiertos > 0) {
        const r = await getRequestDetail(requestId).catch(() => null)
        return textoPeticion({
          enlazada: { titulo: r?.title ?? `#${requestId}`, puntos: r?.points ?? null },
          sinEnlazar: null, cubre: { cuantos: cubiertos, de: ids.length }, alcance: sinAlcance,
        })
      }
      // Una tanda no mira la ficha de cada elemento: dice solo que no enlaza ninguna.
      if (alcance == null) return { texto: 'Ninguna enlazada', aviso: false }
      const ficha = await getLibraryItem(ids[0]).catch(() => null)
      if (!ficha) return { texto: 'No se pudo comprobar si hay una abierta', aviso: false }
      return textoPeticion({ enlazada: null, sinEnlazar: ficha.peticion?.title ?? null, alcance })
    }
    pedir().then(p => { if (vivo) setPeticion(p) })
    return () => { vivo = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- igual que arriba
  }, [clave, requestId, cubiertos, alcance])

  return { yaHay, sincronizado, peticion }
}
