import type { LibraryItemResponse } from '../types/api'
import type { LibraryActionKind } from './LibraryTreeRow'
import { Tooltip } from './Tooltip'

// Single source of truth for the per-item action buttons, shared by the detail
// page and the tree. Same visual format as the "Sincronizar biblioteca" button
// (btn-primary). Both [Subir] and [Petición] are always shown; when the item is
// missing (Faltante) "Subir" is disabled — you can't upload what you don't
// have. For a series/season, "Subir" opens the wizard, which asks which
// season/episode (or the whole season) to target.
export function LibraryActionButtons({ item, onAction, title, showRequest = true }: {
  item: LibraryItemResponse
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
  title?: string
  // Hide the "Petición" button where creating a request makes no sense — e.g.
  // a dashboard recommendation that already has a compatible request.
  showRequest?: boolean
}) {
  const missing = item.local_status === 'Faltante'
  return (
    <>
      <Tooltip content={missing
        ? 'No se puede subir: contenido faltante (no lo tienes en disco).'
        : (title ?? 'Prepara y sube este contenido a eMuwarez (nomenclatura, comprobaciones y subida).')}>
        <button
          className="btn btn-primary btn-sm"
          onClick={() => onAction('upload', item)}
          disabled={missing}
        >
          Subir
        </button>
      </Tooltip>
      {showRequest && (
        <Tooltip content="Crea una petición de este contenido en eMuwarez.">
          <button className="btn btn-primary btn-sm" onClick={() => onAction('request', item)}>
            Petición
          </button>
        </Tooltip>
      )}
    </>
  )
}
