import type { ReactNode } from 'react'
import { IconoOrden } from './Iconos'

// Cabecera que ordena la tabla por su columna, con el mismo aspecto que los
// filtros (HeaderFilter). El primer clic pone arriba lo mayor —o lo más
// reciente— y los siguientes alternan, igual que las opciones del selector de
// orden, que comparte `sortBy` con ella.
export function HeaderSort({ label, nombre, desc, asc, sortBy, onSort, align }: {
  label: ReactNode
  // Lo que lee el lector de pantalla cuando `label` es solo un icono.
  nombre?: string
  desc: string
  asc: string
  sortBy: string
  onSort: (v: string) => void
  align?: 'center'
}) {
  const sentido = sortBy === desc ? 'desc' : sortBy === asc ? 'asc' : null
  const color = sentido ? 'var(--text-accent)' : undefined
  return (
    <th aria-sort={sentido === 'desc' ? 'descending' : sentido === 'asc' ? 'ascending' : 'none'}>
      <button
        type="button"
        className={`hf-trigger${sentido ? ' active' : ''}`}
        onClick={() => onSort(sentido === 'desc' ? asc : desc)}
        title={sentido === 'desc' ? 'Ordenar de menor a mayor' : 'Ordenar de mayor a menor'}
        aria-label={nombre}
        style={{ color, justifyContent: align }}
      >
        <span>{label}</span>
        <span aria-hidden className="hf-caret" style={{ color }}>
          <IconoOrden sentido={sentido} size="1.4em" />
        </span>
      </button>
    </th>
  )
}
