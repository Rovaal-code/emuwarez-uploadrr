import { memo } from 'react'
import type { LibraryItemResponse } from '../types/api'
import { PosterStatusIcon } from './PosterStatusIcon'
import { posterUrl } from '../utils/libraryItem'
import { formatBytes, formatItemType } from '../utils/format'
import { IconoTipo } from './Iconos'
import { CasillaLote } from './lote/CasillaLote'
import { seleccionableEnLote } from '../utils/lote'

// Bigger, Overseerr/Jellyseerr-style poster card for the "Pósters grandes"
// view — additive alongside the existing small grid, not a replacement.
// Memoized: takes a stable onSelect (setSelected) instead of a per-item
// inline onClick closure, so the memo actually skips re-rendering rows
// whose own item/priority props haven't changed.
//
// «Subir por lotes»: con `onToggle`, una película, una serie o una temporada (estas solo salen con un filtro) lleva
// su casilla arriba a la izquierda, encima del póster (arriba a la derecha va el estado). Fuera del layout: la
// tarjeta no puede cambiar de alto (RejillaVirtual la mide).
export const LargePosterCard = memo(function LargePosterCard({ item, onSelect, priority, seleccionado = false, loteLleno = false, onToggle }: {
  item: LibraryItemResponse
  onSelect: (item: LibraryItemResponse) => void
  priority?: boolean
  seleccionado?: boolean
  loteLleno?: boolean
  onToggle?: (item: LibraryItemResponse) => void
}) {
  return (
    <div
      className={seleccionado ? 'clickable poster-grande-tarjeta lote-marcada' : 'clickable poster-grande-tarjeta'}
      onClick={() => onSelect(item)}
    >
      <div className="poster-grande-marco">
        {item.poster_url ? (
          <img
            src={posterUrl(item.poster_url, 'w342')}
            alt=""
            loading={priority ? 'eager' : 'lazy'}
            fetchPriority={priority ? 'high' : 'auto'}
            className="poster-grande-img"
            onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <div className="poster-grande-vacio">
            <IconoTipo serie={item.item_type === 'series' || item.item_type === 'episode'} />
          </div>
        )}
        {/* El botón de verdad que abre la ficha: se llega con el teclado y el lector dice qué es. */}
        <button type="button" className="poster-grande-abrir" aria-label={`Abrir la ficha de ${item.year ? `${item.title} (${item.year})` : item.title}`} />
        {onToggle && seleccionableEnLote(item) && (
          <CasillaLote item={item} seleccionado={seleccionado} bloqueada={loteLleno} onAlternar={onToggle} className="lote-casilla-poster" />
        )}
        <div className="poster-grande-estado">
          <PosterStatusIcon status={item.local_status} />
        </div>
        <div className="poster-grande-pie">
          <div className="poster-grande-titulo">{item.title}</div>
          <div className="poster-grande-anio">
            {[formatItemType(item.item_type), item.year, item.resolution, item.size_bytes ? formatBytes(item.size_bytes) : null]
              .filter(Boolean).join(' · ')}
          </div>
        </div>
      </div>
    </div>
  )
})
