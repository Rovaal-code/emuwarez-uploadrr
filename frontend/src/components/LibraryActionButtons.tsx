import type { LibraryItemResponse } from '../types/api'
import type { LibraryActionKind } from './LibraryTreeRow'

// Single source of truth for the per-item action buttons, shared by the detail
// page and the tree. Same visual format as the "Sincronizar biblioteca" button
// (btn-primary). Both [Subir] and [Petición] are always shown; when the item is
// missing (Faltante) "Subir" is disabled — you can't upload what you don't
// have. For a series/season, "Subir" opens the wizard, which asks which
// season/episode (or the whole season) to target.
export function LibraryActionButtons({ item, onAction, title }: {
  item: LibraryItemResponse
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
  title?: string
}) {
  const missing = item.local_status === 'Faltante'
  return (
    <>
      <button
        className="btn btn-primary btn-sm"
        title={missing ? 'No se puede subir: contenido faltante' : title}
        onClick={() => onAction('upload', item)}
        disabled={missing}
      >
        Subir
      </button>
      <button className="btn btn-primary btn-sm" onClick={() => onAction('request', item)}>
        Petición
      </button>
    </>
  )
}
