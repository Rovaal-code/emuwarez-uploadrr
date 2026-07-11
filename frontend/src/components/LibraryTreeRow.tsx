import { useState, useCallback } from 'react'
import { getLibrary } from '../api/library'
import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { StatusBadge } from './StatusBadge'
import { ServiceLabel } from './ServiceIcon'
import { formatDate, formatItemType, formatBytes } from '../utils/format'
import { buildDeepLink, posterUrl } from '../utils/libraryItem'
import { LibraryActionButtons } from './LibraryActionButtons'

const NESTED_PAGE_SIZE = 25
// Seasons per series — well under the API's max limit=500 (a season list
// is never paginated, unlike episodes), but still bounded defensively.
const MAX_SEASONS_PER_SERIES = 500

export type LibraryActionKind = 'nomenclature' | 'fields' | 'upload' | 'request'

interface LibraryTreeRowProps {
  item: LibraryItemResponse
  depth: number
  instances: InstanceSafeResponse[]
  onSelect: (item: LibraryItemResponse) => void
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
  // Compact mode (used inside a Series detail): hides the Actualizado and
  // Acciones columns.
  compact?: boolean
}

// Series -> Season -> Episode collapsible tree, one row per level, reused
// as-is in the list view, the small detail modal (for a selected Series),
// and the large "Serr-style" detail card. Series/season rows are rollup
// entities with no file of their own, so their Nomenclatura/Campos/Subir
// buttons are placeholders here — the batch action wiring for them lands
// in Phase 6; showing them disabled-with-explanation now avoids calling
// single-item endpoints with a rollup id that would error.
export function LibraryTreeRow({ item, depth, instances, onSelect, onAction, compact = false }: LibraryTreeRowProps) {
  const [expanded, setExpanded] = useState(false)
  const [children, setChildren] = useState<LibraryItemResponse[]>([])
  const [childTotal, setChildTotal] = useState(0)
  const [childOffset, setChildOffset] = useState(0)
  const [loadingChildren, setLoadingChildren] = useState(false)

  const isSeries = item.item_type === 'series'
  const isSeason = item.item_type === 'season'
  const isEpisode = item.item_type === 'episode'
  const expandable = isSeries || isSeason              // has children to load
  const canExpand = expandable || isEpisode            // clicking toggles inline
  const childType = isSeries ? 'season' : 'episode'

  const loadChildren = useCallback(async (off: number) => {
    setLoadingChildren(true)
    try {
      const result = await getLibrary({
        parent_id: item.id,
        type: childType,
        limit: isSeries ? MAX_SEASONS_PER_SERIES : NESTED_PAGE_SIZE,
        offset: isSeries ? 0 : off,
      })
      setChildren(result.items)
      setChildTotal(result.total)
      setChildOffset(off)
    } catch {
      setChildren([])
      setChildTotal(0)
    } finally {
      setLoadingChildren(false)
    }
  }, [item.id, childType, isSeries])

  function toggle() {
    if (expanded) {
      setExpanded(false)
      return
    }
    setExpanded(true)
    // Only series/season load child rows; an episode just reveals its own
    // inline detail panel (no children to fetch).
    if (expandable && children.length === 0) loadChildren(0)
  }

  const deepLink = buildDeepLink(item, instances)
  const indent = depth * 20
  const colSpan = compact ? 9 : 11

  return (
    <>
      <tr className="clickable" onClick={() => canExpand ? toggle() : onSelect(item)}>
        <td>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingLeft: indent }}>
            {canExpand && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={e => { e.stopPropagation(); toggle() }}
                style={{ width: 22, height: 22, padding: 0, fontSize: 10, flexShrink: 0 }}
                title={expanded ? 'Ocultar' : 'Desplegar'}
              >
                {expanded ? '▼' : '▶'}
              </button>
            )}
            <div style={{ flexShrink: 0, width: 28, height: 42, borderRadius: 4, overflow: 'hidden', background: 'rgba(255,255,255,0.04)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {item.poster_url ? (
                <img
                  src={posterUrl(item.poster_url, 'w154')}
                  alt=""
                  loading="lazy"
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
                />
              ) : (
                <span style={{ fontSize: 14, opacity: 0.35 }}>
                  {item.item_type === 'series' || item.item_type === 'episode' ? '📺' : '🎬'}
                </span>
              )}
            </div>
            <div style={{ fontWeight: 500 }}>{item.title}</div>
            {deepLink && (
              <a
                href={deepLink}
                target="_blank"
                rel="noreferrer"
                onClick={e => e.stopPropagation()}
                title={`Ver en ${item.instance_name ?? item.instance_type}`}
                style={{ fontSize: 11, textDecoration: 'none' }}
              >
                🔗
              </a>
            )}
          </div>
          {item.year ? (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', paddingLeft: expandable ? indent + 28 : indent }}>
              {item.year}
            </div>
          ) : null}
        </td>
        <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{formatItemType(item.item_type)}</td>
        <td>
          {item.instance_type
            ? <ServiceLabel type={item.instance_type} label={item.instance_name ?? item.instance_type} size={13} />
            : <span style={{ color: 'var(--text-muted)' }}>—</span>}
        </td>
        <td><StatusBadge status={item.local_status} type="local" /></td>
        <td><StatusBadge status={item.request_status} type="request" /></td>
        <td><StatusBadge status={item.nomenclature_status} type="nomenclature" /></td>
        <td style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
          {formatBytes(item.size_bytes)}
        </td>
        <td style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
          {item.provider_label ?? '—'}
        </td>
        <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          {[item.resolution, item.source].filter(Boolean).join(' · ') || '—'}
        </td>
        {!compact && (
          <td style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
            {formatDate(item.updated_at)}
          </td>
        )}
        {!compact && (
          <td className="col-actions" onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-start', alignItems: 'center' }}>
              <LibraryActionButtons item={item} onAction={onAction} />
            </div>
          </td>
        )}
      </tr>
      {expanded && isEpisode && (
        <tr>
          <td colSpan={colSpan} style={{ padding: 0 }}>
            <div style={{ padding: '12px 16px', paddingLeft: indent + 44, background: 'rgba(255,255,255,0.02)' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '10px 20px', fontSize: 12.5 }}>
                {([
                  ['Resolución', item.resolution],
                  ['Source', item.source],
                  ['Provider', item.provider],
                  ['Códec de vídeo', item.video_codec],
                  ['Códec de audio', item.audio_codec],
                  ['Idiomas de audio', item.audio_languages],
                  ['Subtítulos', item.subtitle_languages],
                  ['Tamaño', formatBytes(item.size_bytes)],
                ] as [string, string | null][]).map(([k, v]) => (
                  <div key={k}>
                    <div style={{ fontSize: 10.5, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{k}</div>
                    <div>{v || '–'}</div>
                  </div>
                ))}
                <div style={{ gridColumn: '1 / -1' }}>
                  <div style={{ fontSize: 10.5, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Ruta</div>
                  <div style={{ wordBreak: 'break-all' }}>{item.path || '–'}</div>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
      {expanded && loadingChildren && (
        <tr>
          <td colSpan={colSpan} style={{ textAlign: 'center', padding: 10, color: 'var(--text-muted)', fontSize: 12 }}>
            Cargando…
          </td>
        </tr>
      )}
      {expanded && !loadingChildren && children.length === 0 && (
        <tr>
          <td colSpan={colSpan} style={{ textAlign: 'center', padding: 10, color: 'var(--text-muted)', fontSize: 12, paddingLeft: indent + 20 }}>
            Sin {childType === 'season' ? 'temporadas' : 'episodios'}
          </td>
        </tr>
      )}
      {expanded && !loadingChildren && children.map(child => (
        <LibraryTreeRow
          key={child.id}
          item={child}
          depth={depth + 1}
          instances={instances}
          onSelect={onSelect}
          onAction={onAction}
          compact={compact}
        />
      ))}
      {expanded && !loadingChildren && !isSeries && childTotal > NESTED_PAGE_SIZE && (
        <tr>
          <td colSpan={colSpan} style={{ padding: '6px 10px' }}>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingLeft: indent }}>
              <button
                className="btn btn-secondary btn-sm"
                disabled={childOffset === 0}
                onClick={() => loadChildren(Math.max(0, childOffset - NESTED_PAGE_SIZE))}
              >
                ← Anterior
              </button>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', alignSelf: 'center' }}>
                {Math.floor(childOffset / NESTED_PAGE_SIZE) + 1} / {Math.ceil(childTotal / NESTED_PAGE_SIZE)}
              </span>
              <button
                className="btn btn-secondary btn-sm"
                disabled={childOffset + NESTED_PAGE_SIZE >= childTotal}
                onClick={() => loadChildren(childOffset + NESTED_PAGE_SIZE)}
              >
                Siguiente →
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
