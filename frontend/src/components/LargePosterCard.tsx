import type { LibraryItemResponse } from '../types/api'
import { PosterStatusIcon } from './PosterStatusIcon'
import { posterUrl } from '../utils/libraryItem'

// Bigger, Overseerr/Jellyseerr-style poster card for the "Pósters grandes"
// view — additive alongside the existing small grid, not a replacement.
export function LargePosterCard({ item, onClick, priority }: {
  item: LibraryItemResponse
  onClick: () => void
  priority?: boolean
}) {
  return (
    <div
      className="clickable"
      onClick={onClick}
      style={{
        display: 'flex', flexDirection: 'column', borderRadius: 12, overflow: 'hidden',
        background: 'var(--bg-surface)', border: '1px solid var(--border)', cursor: 'pointer',
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
      }}
    >
      <div style={{ position: 'relative', width: '100%', aspectRatio: '2 / 3', background: 'rgba(255,255,255,0.04)' }}>
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
            {item.item_type === 'series' || item.item_type === 'episode' ? '📺' : '🎬'}
          </div>
        )}
        <div style={{ position: 'absolute', top: 10, right: 10 }}>
          <PosterStatusIcon status={item.local_status} />
        </div>
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, padding: '20px 12px 10px',
          background: 'linear-gradient(to top, rgba(0,0,0,0.85), transparent)',
        }}>
          <div style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.3, color: '#fff' }}>{item.title}</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.75)', marginTop: 2 }}>
            {item.year ?? '—'}
          </div>
        </div>
      </div>
    </div>
  )
}
