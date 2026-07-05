import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { StatusBadge } from './StatusBadge'
import { SeriesSeasonsSection } from './SeriesSeasonsSection'
import type { LibraryActionKind } from './LibraryTreeRow'
import { formatBytes, formatItemType } from '../utils/format'
import { titleMismatchesFilename, buildDeepLink } from '../utils/libraryItem'

// "Serr-style" (Overseerr/Jellyseerr) large detail card — opened from the
// "Pósters grandes" view. Same underlying data/actions as the existing
// small detail modal, just a roomier side-by-side layout; for a Series it
// also shows its Seasons below, expandable to Episodes (SeriesSeasonsSection,
// shared with the small modal).
export function LibraryDetailCard({ item, instances, onClose, onSelect, onAction }: {
  item: LibraryItemResponse
  instances: InstanceSafeResponse[]
  onClose: () => void
  onSelect: (item: LibraryItemResponse) => void
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
}) {
  const deepLink = buildDeepLink(item, instances)
  const mismatched = titleMismatchesFilename(item)
  const isRollup = item.item_type === 'series' || item.item_type === 'season'
  const actionTitle = isRollup ? 'Ver season pack' : undefined

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 24,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 14,
          maxWidth: 880, width: '100%', maxHeight: '86vh', overflowY: 'auto',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', gap: 24, padding: 28 }}>
          <div style={{ flexShrink: 0, width: 200 }}>
            <div style={{ position: 'relative', width: 200, aspectRatio: '2 / 3', borderRadius: 10, overflow: 'hidden', background: 'rgba(255,255,255,0.04)' }}>
              {item.poster_url ? (
                <img
                  src={item.poster_url}
                  alt={item.title}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
                />
              ) : (
                <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 56, opacity: 0.35 }}>
                  {item.item_type === 'series' || item.item_type === 'episode' ? '📺' : '🎬'}
                </div>
              )}
            </div>
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 22, display: 'flex', alignItems: 'center', gap: 8 }}>
                  {item.title} {item.year ? `(${item.year})` : ''}
                  {deepLink && (
                    <a href={deepLink} target="_blank" rel="noreferrer" title={`Ver en ${item.instance_name ?? item.instance_type}`} style={{ fontSize: 15, textDecoration: 'none' }}>
                      🔗
                    </a>
                  )}
                </div>
                {mismatched && (
                  <div style={{ fontSize: 12, color: 'var(--color-missing)', marginTop: 4 }}>
                    ⚠ Título distinto al del archivo original ({item.original_title})
                  </div>
                )}
              </div>
              <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
            </div>

            <div style={{ display: 'flex', gap: 8, margin: '16px 0', flexWrap: 'wrap' }}>
              <button className="btn btn-secondary btn-sm" title={actionTitle} onClick={() => onAction('nomenclature', item)}>Adaptar nomenclatura</button>
              <button className="btn btn-secondary btn-sm" title={actionTitle} onClick={() => onAction('fields', item)}>Editar campos</button>
              <button className="btn btn-secondary btn-sm" title={actionTitle} onClick={() => onAction('upload', item)}>Subir</button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 24px', fontSize: 13 }}>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>Tipo</div>
                <div>{formatItemType(item.item_type)}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>Origen</div>
                <div>{item.instance_name ?? '—'}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>Estado</div>
                <StatusBadge status={item.local_status} type="local" />
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>Petición</div>
                <StatusBadge status={item.request_status} type="request" />
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>Nomenclatura</div>
                <StatusBadge status={item.nomenclature_status} type="nomenclature" />
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>Resolución / Source</div>
                <div>{[item.resolution, item.source].filter(Boolean).join(' · ') || '—'}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>Tamaño</div>
                <div>{formatBytes(item.size_bytes)}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>TMDb / IMDb</div>
                <div style={{ wordBreak: 'break-all' }}>{item.tmdb_id ?? '—'} / {item.imdb_id ?? '—'}</div>
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>Ruta</div>
                <div style={{ wordBreak: 'break-all' }}>{item.path ?? '—'}</div>
              </div>
            </div>

            {(item.recommended_action || item.diagnostic_summary) && (
              <div style={{ marginTop: 16, padding: '12px 14px', background: 'rgba(255,255,255,0.03)', borderRadius: 8, border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Diagnóstico</div>
                {item.diagnostic_summary && <div style={{ fontSize: 12 }}>{item.diagnostic_summary}</div>}
                {item.recommended_action && (
                  <div style={{ fontSize: 12, marginTop: 4 }}>
                    <span style={{ color: 'var(--text-muted)' }}>Acción recomendada: </span>
                    <span style={{ color: '#a78bfa', fontWeight: 600 }}>{item.recommended_action}</span>
                  </div>
                )}
              </div>
            )}

            {item.item_type === 'series' && (
              <SeriesSeasonsSection seriesId={item.id} instances={instances} onSelect={onSelect} onAction={onAction} />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
