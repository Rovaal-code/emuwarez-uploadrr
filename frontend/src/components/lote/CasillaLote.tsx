import type { LibraryItemResponse } from '../../types/api'

/**
 * La casilla para marcar un elemento de Biblioteca para «Subir por lotes», en la fila de la lista y en las
 * tarjetas de póster. El clic no sale de ella: ni despliega la fila ni abre la ficha.
 */
export function CasillaLote({ item, seleccionado, bloqueada = false, onAlternar, className }: {
  item: LibraryItemResponse
  seleccionado: boolean
  // Lleno el lote: las que no están marcadas no se pueden marcar.
  bloqueada?: boolean
  onAlternar: (item: LibraryItemResponse) => void
  className?: string
}) {
  return (
    <label
      className={className ? `checkbox-label lote-casilla ${className}` : 'checkbox-label lote-casilla'}
      title={bloqueada && !seleccionado ? 'El lote ya está lleno' : undefined}
      onClick={e => e.stopPropagation()}
      onMouseDown={e => e.stopPropagation()}
    >
      <input
        type="checkbox"
        checked={seleccionado}
        disabled={bloqueada && !seleccionado}
        onChange={() => onAlternar(item)}
        aria-label={`Seleccionar «${item.title}»`}
      />
    </label>
  )
}
