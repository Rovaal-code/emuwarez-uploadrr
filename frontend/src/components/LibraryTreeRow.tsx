import { useState, useCallback } from 'react'
import { getLibrary } from '../api/library'
import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { StatusBadge } from './StatusBadge'
import { ServiceLabel } from './ServiceIcon'
import { formatDate, formatItemType } from '../utils/format'
import { titleMismatchesFilename, buildDeepLink } from '../utils/libraryItem'

const NESTED_PAGE_SIZE = 25
// Seasons per series — well under the API's max limit=500 (a season list
// is never paginated, unlike episodes), but still bounded defensively.
const MAX_SEASONS_PER_SERIES = 500

export type LibraryActionKind = 'nomenclature' | 'fields' | 'upload'

interface LibraryTreeRowProps {
  item: LibraryItemResponse
  depth: number
  instances: InstanceSafeResponse[]
  onSelect: (item: LibraryItemResponse) => void
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
}

// Series -> Season -> Episode collapsible tree, one row per level, reused
// as-is in the list view, the small detail modal (for a selected Series),
// and the large "Serr-style" detail card. Series/season rows are rollup
// entities with no file of their own, so their Nomenclatura/Campos/Subir
// buttons are placeholders here — the batch action wiring for them lands
// in Phase 6; showing them disabled-with-explanation now avoids calling
// single-item endpoints with a rollup id that would error.
export function LibraryTreeRow({ item, depth, instances, onSelect, onAction }: LibraryTreeRowProps) {
  const [expanded, setExpanded] = useState(false)
  const [children, setChildren] = useState<LibraryItemResponse[]>([])
  const [childTotal, setChildTotal] = useState(0)
  const [childOffset, setChildOffset] = useState(0)
  const [loadingChildren, setLoadingChildren] = useState(false)

  const isSeries = item.item_type === 'series'
  const isSeason = item.item_type === 'season'
  const expandable = isSeries || isSeason
  const isRollup = isSeries || isSeason
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
    if (children.length === 0) loadChildren(0)
  }

  const deepLink = buildDeepLink(item, instances)
  const mismatched = titleMismatchesFilename(item)
  const indent = depth * 20
  const colSpan = 12

  return (
    <>
      <tr className="clickable" onClick={() => onSelect(item)}>
        <td>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingLeft: indent }}>
            {expandable && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={e => { e.stopPropagation(); toggle() }}
                style={{ width: 22, height: 22, padding: 0, fontSize: 10, flexShrink: 0 }}
                title={expanded ? 'Ocultar' : 'Desplegar'}
              >
                {expanded ? '▼' : '▶'}
              </button>
            )}
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
            {mismatched && (
              <span style={{ fontSize: 11, color: 'var(--color-missing)' }} title={`Título original: ${item.original_title}`}>⚠</span>
            )}
          </div>
          {item.year && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', paddingLeft: expandable ? indent + 28 : indent }}>
              {item.year}
            </div>
          )}
        </td>
        <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{formatItemType(item.item_type)}</td>
        <td>
          {item.instance_type
            ? <ServiceLabel type={item.instance_type} label={item.instance_name ?? item.instance_type} size={13} />
            : <span style={{ color: 'var(--text-muted)' }}>—</span>}
        </td>
        <td><StatusBadge status={item.local_status} type="local" /></td>
        <td style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
          {item.file_exists === null || item.file_exists === undefined
            ? <span style={{ color: 'var(--text-muted)' }}>—</span>
            : item.file_exists
              ? <span style={{ color: 'var(--color-available)' }}>OK</span>
              : <span style={{ color: 'var(--color-missing)' }}>NO</span>}
        </td>
        <td><StatusBadge status={item.request_status} type="request" /></td>
        <td><StatusBadge status={item.nomenclature_status} type="nomenclature" /></td>
        <td style={{ fontSize: 11, color: 'var(--text-secondary)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {item.diagnostic_summary ?? '—'}
        </td>
        <td style={{ fontSize: 11, color: '#a78bfa', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {item.recommended_action ?? '—'}
        </td>
        <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          {[item.resolution, item.source].filter(Boolean).join(' · ') || '—'}
        </td>
        <td style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
          {formatDate(item.updated_at)}
        </td>
        <td className="col-actions" onClick={e => e.stopPropagation()} style={{ display: 'flex', gap: 4 }}>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => onAction('nomenclature', item)}
            disabled={isRollup}
            title={isRollup ? 'Acción por lotes disponible próximamente' : 'Adaptar nomenclatura'}
          >
            Nomenclatura
          </button>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => onAction('fields', item)}
            disabled={isRollup}
            title={isRollup ? 'Acción por lotes disponible próximamente' : 'Editar campos de nomenclatura'}
          >
            Campos
          </button>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => onAction('upload', item)}
            disabled={isRollup}
            title={isRollup ? 'Acción por lotes disponible próximamente' : 'Preflight Uploadrr'}
          >
            Subir
          </button>
        </td>
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
