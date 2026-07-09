import type { LibraryItemResponse } from '../types/api'
import type { LibraryActionKind } from './LibraryTreeRow'

// Single source of truth for the per-item action buttons, shared by the detail
// page and the tree. Same visual format as the "Sincronizar biblioteca" button
// (btn-primary). Rule:
//   - Available/partial item: [Subir] [Petición] side by side.
//   - Missing item (Faltante): only [Petición] — you can't upload what you
//     don't have. For a series/season, "Subir" opens the wizard, which asks
//     which season/episode (or the whole season) to target.
export function LibraryActionButtons({ item, onAction, title }: {
  item: LibraryItemResponse
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
  title?: string
}) {
  const missing = item.local_status === 'Faltante'
  return (
    <>
      {!missing && (
        <button className="btn btn-primary btn-sm" title={title} onClick={() => onAction('upload', item)}>
          Subir
        </button>
      )}
      <button className="btn btn-primary btn-sm" onClick={() => onAction('request', item)}>
        Petición
      </button>
    </>
  )
}
