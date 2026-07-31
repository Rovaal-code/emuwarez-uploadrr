import type { LibraryItemResponse } from '../types/api'
import type { LibraryActionKind } from './LibraryTreeRow'
import { Tooltip } from './Tooltip'
import { UploadButtonIcon, RequestButtonIcon } from './DetailCard'

// Single source of truth for the per-item action buttons, shared by the detail
// page and the tree. Same visual format as the "Sincronizar biblioteca" button
// (btn-primary). Both [Subir] and [Petición] are always shown; when the item is
// missing (Faltante) "Subir" is disabled — you can't upload what you don't
// have. A season with SOME but not all episodes Disponible ("Parcial") is the
// same story: build_season_pack_plan() blocks an incomplete pack outright
// (services/season_pack.py), so there's no point letting the user open the
// wizard just to hit that wall inside the pre-upload checks — disabled here,
// same as Faltante, instead. For a series/season, "Subir" opens the wizard,
// which asks which season/episode (or the whole season) to target.
export function LibraryActionButtons({ item, onAction, title }: {
  item: LibraryItemResponse
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
  title?: string
  // True for a series row anywhere in Biblioteca (its own page AND the
  // list/table): "Subir" opens the multi-season checklist instead of the
  // single season/episode picker. Never for a season's own page, which has
  // exactly one season to offer.
}) {
  const missing = item.local_status === 'Faltante'
  // A season no longer gets disabled for being incomplete or for its episodes
  // disagreeing: both of those only rule out the PACK, and the wizard now
  // offers a per-episode mode where neither applies. The reason moves to the
  // "Temporada entera" card inside, which is where it actually decides
  // something. Only "nothing held at all" still blocks, since then there is
  // no file to upload by any route.
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
