import { useState, useCallback } from 'react'
import { getLibrary } from '../api/library'
import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { StatusBadge } from './StatusBadge'
import { ServiceLabel } from './ServiceIcon'
import { formatDate, formatItemType, formatBytes } from '../utils/format'
import { buildDeepLink, posterUrl, isAporteEligible, episodeListLabel } from '../utils/libraryItem'
import { ProviderTag } from './ProviderIcon'
import { LibraryActionButtons } from './LibraryActionButtons'

const NESTED_PAGE_SIZE = 25
// Seasons per series — well under the API's max limit=500 (a season list
// is never paginated, unlike episodes), but still bounded defensively.
const MAX_SEASONS_PER_SERIES = 500

export type LibraryActionKind = 'nomenclature' | 'fields' | 'upload' | 'upload-multi' | 'request'

interface LibraryTreeRowProps {
  item: LibraryItemResponse
  depth: number
  instances: InstanceSafeResponse[]
  onSelect: (item: LibraryItemResponse) => void
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
  // Called after a nomenclature check so the list can refresh the badges.
  onReload?: () => void
  // Compact mode (used inside a Series detail): hides the Actualizado and
  // Acciones columns.
  compact?: boolean
  // Above-the-fold rows (top of the list on initial load) — eager + high
  // fetch priority so their poster is already there instead of popping in
  // as the browser's own lazy-load catches up.
  priority?: boolean
}

// Series -> Season -> Episode collapsible tree, one row per level, reused
// as-is in the list view, the small detail modal (for a selected Series),
// and the large "Serr-style" detail card. Series/season rows are rollup
// entities with no file of their own, so their Nomenclatura/Campos/Subir
// buttons are placeholders here — the batch action wiring for them lands
// in Phase 6; showing them disabled-with-explanation now avoids calling
// single-item endpoints with a rollup id that would error.
// "¿En eMuwarez?" — badge (same visual format as Estado/Nomenclatura):
// "No" = not on the tracker (an upload opportunity, green), "Sí" = already
// there (neutral gray), — = catalog not synced yet.
export function EmuStatusCell({ item }: { item: LibraryItemResponse }) {
  if (item.emu_in_catalog == null) {
    return <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>—</span>
  }
  // 0 = No, 1 = Sí, 2 = Parcial (series with some seasons on eMuwarez, some not).
  const status = item.emu_in_catalog === 0 ? 'No' : item.emu_in_catalog === 2 ? 'Parcial' : 'Sí'
  return <StatusBadge status={status} type="emu" />
}

// "Aportes" — what your copy would add: "Nuevo" badge if it's not on the
// tracker at all, chips per improvement (resolution / source / codec / ESP),
// or — when it's there and you add nothing. Only meaningful for content you
// actually have (Disponible/Subido/Subiendo, or Parcial for a rollup) — a
// Faltante item has nothing to contribute regardless of emu_in_catalog.
export function EmuAportesCell({ item }: { item: LibraryItemResponse }) {
  if (item.emu_in_catalog == null || !isAporteEligible(item)) {
    return <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>—</span>
  }
  if (item.emu_in_catalog === 0) {
    return <StatusBadge status="Nuevo" type="emu" />
  }
  const aportes = item.emu_aportes ?? []
  if (aportes.length === 0) {
    return <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>—</span>
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {aportes.map((a, i) => (
        <span
          key={i}
          style={{
            fontSize: 10.5, padding: '1px 6px', borderRadius: 4, whiteSpace: 'nowrap',
            background: 'rgba(34,197,94,0.14)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.3)',
          }}
        >
          {a.detail}
        </span>
      ))}
    </div>
  )
}

export function LibraryTreeRow({ item, depth, instances, onSelect, onAction, onReload, compact = false, priority = false }: LibraryTreeRowProps) {
  const [expanded, setExpanded] = useState(false)
  const [children, setChildren] = useState<LibraryItemResponse[]>([])
  const [childTotal, setChildTotal] = useState(0)
  const [childOffset, setChildOffset] = useState(0)
  const [loadingChildren, setLoadingChildren] = useState(false)

  const isSeries = item.item_type === 'series'
  const isSeason = item.item_type === 'season'
  const expandable = isSeries || isSeason              // has children to load
  // Episodes are leaf rows: no dropdown — their title opens their own detail
  // card, which is where you consult their data.
  const canExpand = expandable
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
  const colSpan = compact ? 10 : 12

  return (
    <>
      <tr className={canExpand ? 'clickable' : undefined} onClick={canExpand ? toggle : undefined}>
        <td>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingLeft: indent }}>
            {canExpand ? (
              <button
                className="btn btn-ghost btn-sm"
                onClick={e => { e.stopPropagation(); toggle() }}
                style={{ width: 22, height: 22, padding: 0, fontSize: 10, flexShrink: 0 }}
                title={expanded ? 'Ocultar' : 'Desplegar'}
              >
                {expanded ? '▼' : '▶'}
              </button>
            ) : item.item_type === 'episode' && item.episode_number != null ? (
              // Episodes use the chevron's slot to show their episode number.
              <span style={{ width: 22, flexShrink: 0, textAlign: 'left', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>
                {item.episode_number}
              </span>
            ) : (
              // Other leaf rows (movies) keep the chevron's width so their
              // content stays aligned one indent level deeper than the parent.
              <span style={{ width: 22, flexShrink: 0 }} />
            )}
            <div className="poster-thumb" style={{ flexShrink: 0, width: 28, height: 42, borderRadius: 4, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {item.poster_url ? (
                <img
                  src={posterUrl(item.poster_url, 'w154')}
                  alt=""
                  loading={priority ? 'eager' : 'lazy'}
                  fetchPriority={priority ? 'high' : 'auto'}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
                />
              ) : (
                <span style={{ fontSize: 14, opacity: 0.35 }}>
                  {item.item_type === 'series' || item.item_type === 'episode' ? '📺' : '🎬'}
                </span>
              )}
            </div>
            <div
              className="lib-title-link"
              onClick={e => { e.stopPropagation(); onSelect(item) }}
              title="Abrir ficha"
            >
              {episodeListLabel(item)}
            </div>
            {item.year ? <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 4, flexShrink: 0 }}>({item.year})</span> : null}
          </div>
        </td>
        <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{formatItemType(item.item_type)}</td>
        <td>
          {item.instance_type
            ? (deepLink
                ? <a className="hover-link" href={deepLink} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} title={`Abrir en ${item.instance_name ?? item.instance_type}`}><ServiceLabel type={item.instance_type} label={item.instance_name ?? item.instance_type} size={13} /></a>
                : <ServiceLabel type={item.instance_type} label={item.instance_name ?? item.instance_type} size={13} />)
            : <span style={{ color: 'var(--text-muted)' }}>—</span>}
        </td>
        <td><StatusBadge status={item.local_status} type="local" /></td>
        <td><StatusBadge status={item.request_status} type="request" /></td>
        <td style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
          {formatBytes(item.size_bytes)}
        </td>
        <td style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
          {item.provider ? <ProviderTag code={item.provider} label={item.provider_label} size={16} /> : '—'}
        </td>
        <td style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
          {[item.resolution, item.source].filter(Boolean).join(' · ') || '—'}
        </td>
        <td style={{ whiteSpace: 'nowrap' }}><EmuStatusCell item={item} /></td>
        <td><EmuAportesCell item={item} /></td>
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
          onReload={onReload}
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
