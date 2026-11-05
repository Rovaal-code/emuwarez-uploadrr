/**
 * La casilla para marcar un elemento para «Subir por lotes»: en Biblioteca, en la fila de la lista y en las
 * tarjetas de póster; en el Panel, en las filas de «Listo para subir». El clic no sale de ella: ni despliega la fila
 * ni abre la ficha. `titulo` (por defecto el `title` del elemento) es el nombre que oye el lector.
 */
export function CasillaLote<T extends { title: string | null }>({
  item, titulo, seleccionado, bloqueada = false, onAlternar, className,
}: {
  item: T
  titulo?: string
  seleccionado: boolean
  // Lleno el lote: las que no están marcadas no se pueden marcar.
  bloqueada?: boolean
  onAlternar: (item: T) => void
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
        aria-label={`Seleccionar «${titulo ?? item.title ?? ''}»`}
      />
    </label>
  )
}
