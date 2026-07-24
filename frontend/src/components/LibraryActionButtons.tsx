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
  const seasonIncomplete = item.item_type === 'season' && item.local_status === 'Parcial'
  const multiSeason = !!multiSeasonContext && item.item_type === 'series'
  return (
    <>
      <Tooltip content={missing
        ? 'No se puede subir: contenido faltante (no lo tienes en disco).'
        : seasonIncomplete
        ? 'No se puede subir: temporada incompleta (faltan episodios por estar Disponibles).'
        : (title ?? 'Prepara y sube este contenido a eMuwarez (nomenclatura, comprobaciones y subida).')}>
        <button
          className="btn btn-primary btn-sm"
          onClick={() => onAction(multiSeason ? 'upload-multi' : 'upload', item)}
          disabled={missing || seasonIncomplete}
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
