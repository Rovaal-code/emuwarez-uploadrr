import { memo } from 'react'
import type { LibraryItemResponse } from '../types/api'
import { PosterStatusIcon } from './PosterStatusIcon'
import { posterUrl } from '../utils/libraryItem'
import { IconoTipo } from './Iconos'

// Bigger, Overseerr/Jellyseerr-style poster card for the "Pósters grandes"
// view — additive alongside the existing small grid, not a replacement.
// Memoized: takes a stable onSelect (setSelected) instead of a per-item
// inline onClick closure, so the memo actually skips re-rendering rows
// whose own item/priority props haven't changed.
export const LargePosterCard = memo(function LargePosterCard({ item, onSelect, priority }: {
  item: LibraryItemResponse
  onSelect: (item: LibraryItemResponse) => void
  priority?: boolean
}) {
  return (
    <div
      className="clickable poster-grande-tarjeta"
      onClick={() => onSelect(item)}
    >
      <div className="poster-grande-marco">
        {item.poster_url ? (
          <img
            src={posterUrl(item.poster_url, 'w342')}
            alt={item.title}
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
        <div className="poster-grande-estado">
          <PosterStatusIcon status={item.local_status} />
        </div>
        <div className="poster-grande-pie">
          <div className="poster-grande-titulo">{item.title}</div>
          <div className="poster-grande-anio">
            {item.year ?? '—'}
          </div>
        </div>
      </div>
    </div>
  )
})
