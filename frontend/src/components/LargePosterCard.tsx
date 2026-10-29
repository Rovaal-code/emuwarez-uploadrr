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
      className="clickable"
      onClick={() => onSelect(item)}
      style={{
        display: 'flex', flexDirection: 'column', borderRadius: 12, overflow: 'hidden',
        background: 'var(--bg-surface)', border: '1px solid var(--border)', cursor: 'pointer',
        boxShadow: '0 2px 8px color-mix(in srgb, var(--overlay-dark) 15%, transparent)',
      }}
    >
      <div style={{ position: 'relative', width: '100%', aspectRatio: '2 / 3', background: 'color-mix(in srgb, var(--overlay-light) 4%, transparent)' }}>
        {item.poster_url ? (
          <img
            src={posterUrl(item.poster_url, 'w342')}
            alt={item.title}
            loading={priority ? 'eager' : 'lazy'}
            fetchPriority={priority ? 'high' : 'auto'}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 64, opacity: 0.35 }}>
            <IconoTipo serie={item.item_type === 'series' || item.item_type === 'episode'} />
          </div>
        )}
        <div style={{ position: 'absolute', top: 10, right: 10 }}>
          <PosterStatusIcon status={item.local_status} />
        </div>
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, padding: '20px 12px 10px',
          background: 'linear-gradient(to top, color-mix(in srgb, var(--overlay-dark) 85%, transparent), transparent)',
        }}>
          <div style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.3, color: 'var(--text-on-color)' }}>{item.title}</div>
          <div style={{ fontSize: 12, color: 'color-mix(in srgb, var(--overlay-light) 75%, transparent)', marginTop: 2 }}>
            {item.year ?? '—'}
          </div>
        </div>
      </div>
    </div>
  )
})
