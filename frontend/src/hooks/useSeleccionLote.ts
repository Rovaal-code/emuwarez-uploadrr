import { useCallback, useState } from 'react'
import type { LibraryItemResponse } from '../types/api'
import { MAX_ELEMENTOS_LOTE } from '../utils/lote'

/**
 * Lo marcado para «Subir por lotes». Vive en el estado de la página y no en el DOM: la lista y la rejilla solo
 * pintan lo que se ve (FilasVirtuales, RejillaVirtual). Se guarda el elemento entero y no solo su id, porque un
 * filtro o una recarga pueden quitarlo de la lista y sigue marcado.
 *
 * `alternar` y `limpiar` son estables: las filas y tarjetas reciben `seleccionado` (un booleano) y `alternar`,
 * nunca el Map, que rompería su `memo` y repintaría todas con cada clic.
 */
export function useSeleccionLote(maximo = MAX_ELEMENTOS_LOTE) {
  const [seleccion, setSeleccion] = useState<ReadonlyMap<number, LibraryItemResponse>>(() => new Map())

  const alternar = useCallback((item: LibraryItemResponse) => {
    setSeleccion(prev => {
      const sig = new Map(prev)
      if (sig.has(item.id)) sig.delete(item.id)
      else if (sig.size >= maximo) return prev
      else sig.set(item.id, item)
      return sig
    })
  }, [maximo])

  // Sin nada marcado no cambia el estado: no repinta la página para nada.
  const limpiar = useCallback(() => {
    setSeleccion(prev => (prev.size === 0 ? prev : new Map()))
  }, [])

  const tiene = useCallback((id: number) => seleccion.has(id), [seleccion])

  return { seleccion, total: seleccion.size, lleno: seleccion.size >= maximo, alternar, limpiar, tiene }
}
