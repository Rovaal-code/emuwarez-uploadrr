import { useCallback, useEffect, useRef, useState } from 'react'
import type { LibraryItemResponse } from '../types/api'
import { MAX_ELEMENTOS_LOTE } from '../utils/lote'

const porId = (item: { id: number }) => item.id

/**
 * Lo marcado para «Subir por lotes». Vive en el estado de la página y no en el DOM: la lista y la rejilla solo
 * pintan lo que se ve (FilasVirtuales, RejillaVirtual). Se guarda el elemento entero y no solo su id, porque un
 * filtro o una recarga pueden quitarlo de la lista y sigue marcado.
 *
 * `alternar` y `limpiar` son estables: las filas y tarjetas reciben `seleccionado` (un booleano) y `alternar`,
 * nunca el Map, que rompería su `memo` y repintaría todas con cada clic.
 *
 * Biblioteca marca por id (Peticiones, por el de la petición); el Panel, por `claveDelPanel` (una fila por
 * petición). `claveDe` tiene que ser estable
 * (una función de módulo).
 */
export function useSeleccionLote<T extends { id: number } = LibraryItemResponse, K = number>(
  maximo = MAX_ELEMENTOS_LOTE,
  claveDe: (item: T) => K = porId as unknown as (item: T) => K,
) {
  const [seleccion, setSeleccion] = useState<ReadonlyMap<K, T>>(() => new Map())

  const alternar = useCallback((item: T) => {
    setSeleccion(prev => {
      const clave = claveDe(item)
      const sig = new Map(prev)
      if (sig.has(clave)) sig.delete(clave)
      else if (sig.size >= maximo) return prev
      else sig.set(clave, item)
      return sig
    })
  }, [maximo, claveDe])

  // Sin nada marcado no cambia el estado: no repinta la página para nada.
  const limpiar = useCallback(() => {
    setSeleccion(prev => (prev.size === 0 ? prev : new Map()))
  }, [])

  const tiene = useCallback((clave: K) => seleccion.has(clave), [seleccion])

  // «Subir seleccionadas» pide fichas antes de abrir el modal: si mientras tanto se marca, desmarca o limpia algo,
  // lo preparado ya no es lo marcado y no se abre. Cada cambio crea un Map nuevo, así que basta comparar referencias.
  const actual = useRef(seleccion)
  useEffect(() => { actual.current = seleccion }, [seleccion])
  const sigueIgual = useCallback((antes: ReadonlyMap<K, T>) => actual.current === antes, [])

  return { seleccion, total: seleccion.size, lleno: seleccion.size >= maximo, alternar, limpiar, tiene, sigueIgual }
}
