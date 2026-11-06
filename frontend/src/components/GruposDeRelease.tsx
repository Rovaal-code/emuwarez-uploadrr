import { ValueChip, ValueIcon, PlainValue, ReleaseGroupValueIcon } from './DetailCard'

// Con más de estos, la ficha junta los grupos en «Varios» para no llenar la fila.
export const GRUPOS_MAX_EN_FICHA = 3

/** Los grupos de release de un elemento: los de todos sus capítulos si es una serie o temporada, y si no, el suyo. */
export function gruposDeRelease(item: { release_group?: string | null; release_groups?: string[] | null }): string[] {
  if (item.release_groups?.length) return item.release_groups
  return item.release_group ? [item.release_group] : []
}

/** Un grupo por insignia, o «Varios» con la lista en el tooltip cuando no caben (`junto`: ya con más de uno). */
export function GruposDeRelease({ grupos, junto = false, plano = false }: { grupos: string[]; junto?: boolean; plano?: boolean }) {
  if (grupos.length === 0) return <span className="muted">—</span>
  // `plano`: para una tabla, donde una ficha con borde parece un botón (ver PlainValue).
  if (plano) {
    const texto = grupos.length > (junto ? 1 : GRUPOS_MAX_EN_FICHA) ? `Varios (${grupos.length})` : grupos.join(', ')
    return <span title={grupos.length > 1 ? grupos.join(', ') : undefined}><PlainValue icon={<ReleaseGroupValueIcon />}>{texto}</PlainValue></span>
  }
  if (grupos.length > (junto ? 1 : GRUPOS_MAX_EN_FICHA)) {
    return (
      <ValueChip title={grupos.join(', ')}>
        <ValueIcon><ReleaseGroupValueIcon /></ValueIcon><span className="txt">Varios ({grupos.length})</span>
      </ValueChip>
    )
  }
  return (
    <span className="bibdet-proveedores">
      {grupos.map(g => (
        <ValueChip key={g}><ValueIcon><ReleaseGroupValueIcon /></ValueIcon><span className="txt">{g}</span></ValueChip>
      ))}
    </span>
  )
}
