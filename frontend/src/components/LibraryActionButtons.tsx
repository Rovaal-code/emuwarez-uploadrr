import type { LibraryItemResponse } from '../types/api'
import type { LibraryActionKind } from './LibraryTreeRow'
import { Tooltip } from './Tooltip'
import { UploadButtonIcon, RequestButtonIcon } from './DetailCard'

// Single source of truth for the per-item action buttons, shared by the detail
// page and the tree. Same visual format as the "Sincronizar biblioteca" button
// (btn-primary). Both [Subir] and [Petición] are always shown; when the item is
// missing (Faltante) "Subir" is disabled — you can't upload what you don't
// have. For a series/season, "Subir" opens the wizard, which asks which
// season/episode (or the whole season) to target.
export function LibraryActionButtons({ item, onAction, title, multiSeasonContext }: {
  item: LibraryItemResponse
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
  title?: string
  // Only true on a series' own dedicated Biblioteca page — the one place
  // "Subir" opens the multi-season checklist instead of the single season/
  // episode picker (never from the Biblioteca list/table, never from a
  // season's own page).
  multiSeasonContext?: boolean
}) {
  const missing = item.local_status === 'Faltante'
  const multiSeason = !!multiSeasonContext && item.item_type === 'series'
  return (
    <>
      <Tooltip content={missing
        ? 'No se puede subir: contenido faltante (no lo tienes en disco).'
        : (title ?? 'Prepara y sube este contenido a eMuwarez (nomenclatura, comprobaciones y subida).')}>
        <button
          className="btn btn-primary btn-sm"
          onClick={() => onAction(multiSeason ? 'upload-multi' : 'upload', item)}
          disabled={missing}
        >
          <UploadButtonIcon /> Subir
        </button>
      </Tooltip>
      <Tooltip content="Crea una petición de este contenido en eMuwarez.">
        <button className="btn btn-primary btn-sm" onClick={() => onAction('request', item)}>
          <RequestButtonIcon /> Petición
        </button>
      </Tooltip>
    </>
  )
}
