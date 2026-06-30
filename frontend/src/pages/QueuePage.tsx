import { useState, useEffect, useCallback } from 'react'
import { listQueue, getQueueSummary, refreshQueue, resolveQueueItem, ignoreQueueItem } from '../api/operationalQueue'
import type { OperationalQueueItem, OperationalQueueSummary } from '../types/api'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { formatDate } from '../utils/format'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BUCKET_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high:     '#f97316',
  medium:   '#f59e0b',
  low:      '#6b7280',
  blocked:  '#7f1d1d',
}

const STATUS_LABELS: Record<string, string> = {
  open:      'Abierto',
  ready:     'Listo',
  waiting:   'Esperando',
  blocked:   'Bloqueado',
  running:   'En curso',
  resolved:  'Resuelto',
  ignored:   'Ignorado',
  completed: 'Completado',
}

const ACTION_LABELS: Record<string, string> = {
  adapt_nomenclature: 'Adaptar nomenclatura',
  run_preflight:      'Ejecutar preflight',
  upload:             'Subir',
  view_upload:        'Ver subida',
  retry_upload:       'Reintentar subida',
  wait_download:      'Esperar descarga',
  review_arr:         'Revisar ARR',
  verify_file:        'Verificar archivo',
  fix_path:           'Corregir ruta',
  check_emu:          'Comprobar EMU',
  manual_review:      'Revisión manual',
  none:               '—',
}

function PriorityBadge({ bucket }: { bucket: string }) {
  const color = BUCKET_COLORS[bucket] ?? '#6b7280'
  return (
    <span style={{
      background: color + '22',
      color,
      border: `1px solid ${color}44`,
      borderRadius: 4,
      padding: '2px 7px',
      fontSize: '0.72rem',
      fontWeight: 600,
      textTransform: 'uppercase',
      letterSpacing: '0.03em',
    }}>
      {bucket}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    ready:   '#22c55e',
    open:    '#3b82f6',
    waiting: '#a78bfa',
    blocked: '#ef4444',
    running: '#f59e0b',
  }
  const color = colorMap[status] ?? '#6b7280'
  return (
    <span style={{
      color,
      fontSize: '0.78rem',
      fontWeight: 500,
    }}>
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

function DetailPanel({ item, onClose, onResolve, onIgnore }: {
  item: OperationalQueueItem
  onClose: () => void
  onResolve: (id: number) => void
  onIgnore: (id: number) => void
}) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.04)',
      border: '1px solid rgba(59,130,246,0.15)',
      borderRadius: 8,
      padding: 20,
      marginTop: 12,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontWeight: 600, fontSize: '0.92rem' }}>Item #{item.id}</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: '1.1rem' }}>✕</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: '0.82rem' }}>
        <div><span style={{ color: '#6b7280' }}>Clave: </span>{item.queue_key}</div>
        <div><span style={{ color: '#6b7280' }}>Tipo: </span>{item.item_type}</div>
        <div><span style={{ color: '#6b7280' }}>Estado: </span><StatusBadge status={item.status} /></div>
        <div><span style={{ color: '#6b7280' }}>Prioridad: </span><PriorityBadge bucket={item.priority_bucket} /></div>
        <div><span style={{ color: '#6b7280' }}>Acción: </span>{ACTION_LABELS[item.action] ?? item.action}</div>
        <div><span style={{ color: '#6b7280' }}>Score: </span>{item.priority_score}</div>
        {item.request_item_id && <div><span style={{ color: '#6b7280' }}>Request ID: </span>{item.request_item_id}</div>}
        {item.library_item_id && <div><span style={{ color: '#6b7280' }}>Library ID: </span>{item.library_item_id}</div>}
        {item.upload_job_id && <div><span style={{ color: '#6b7280' }}>Upload Job: </span>{item.upload_job_id}</div>}
        {item.updated_at && <div><span style={{ color: '#6b7280' }}>Actualizado: </span>{formatDate(item.updated_at)}</div>}
      </div>

      {item.subtitle && (
        <div style={{ marginTop: 10, fontSize: '0.82rem', color: '#9ca3af' }}>{item.subtitle}</div>
      )}

      {item.blockers.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: '0.78rem', color: '#ef4444', fontWeight: 600, marginBottom: 4 }}>Bloqueadores</div>
          {item.blockers.map((b, i) => (
            <div key={i} style={{ fontSize: '0.8rem', color: '#fca5a5', padding: '3px 0' }}>· {b}</div>
          ))}
        </div>
      )}

      {item.reasons.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: '0.78rem', color: '#9ca3af', fontWeight: 600, marginBottom: 4 }}>Razones</div>
          {item.reasons.map((r, i) => (
            <div key={i} style={{ fontSize: '0.8rem', color: '#d1d5db', padding: '3px 0' }}>· {r}</div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <button
          onClick={() => onResolve(item.id)}
          style={{
            background: '#166534', color: '#86efac', border: '1px solid #16a34a',
            borderRadius: 5, padding: '5px 14px', cursor: 'pointer', fontSize: '0.8rem',
          }}
        >
          Marcar resuelto
        </button>
        <button
          onClick={() => onIgnore(item.id)}
          style={{
            background: 'rgba(255,255,255,0.06)', color: '#9ca3af', border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 5, padding: '5px 14px', cursor: 'pointer', fontSize: '0.8rem',
          }}
        >
          Ignorar
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function QueuePage() {
  const [items, setItems] = useState<OperationalQueueItem[]>([])
  const [summary, setSummary] = useState<OperationalQueueSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null)
  const [selected, setSelected] = useState<OperationalQueueItem | null>(null)

  // Filters
  const [filterBucket, setFilterBucket] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterAction, setFilterAction] = useState('')

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, string> = {}
      if (filterBucket) params.priority_bucket = filterBucket
      if (filterStatus) params.status = filterStatus
      if (filterAction) params.action = filterAction
      const [list, sum] = await Promise.allSettled([
        listQueue({ ...params, limit: 200 }),
        getQueueSummary(),
      ])
      if (list.status === 'fulfilled') setItems(list.value.items)
      if (sum.status === 'fulfilled') setSummary(sum.value)
    } catch {
      setError('No se pudo cargar la cola operativa')
    } finally {
      setLoading(false)
    }
  }, [filterBucket, filterStatus, filterAction])

  useEffect(() => { loadData() }, [loadData])

  async function handleRefresh() {
    setRefreshing(true)
    setRefreshMsg(null)
    try {
      const res = await refreshQueue()
      setRefreshMsg(`Cola actualizada: ${res.items_built} items · Listos: ${res.summary?.ready ?? 0}`)
      await loadData()
    } catch {
      setRefreshMsg('Error al refrescar la cola')
    } finally {
      setRefreshing(false)
    }
  }

  async function handleResolve(id: number) {
    try {
      await resolveQueueItem(id)
      setSelected(null)
      await loadData()
    } catch { /* ignore */ }
  }

  async function handleIgnore(id: number) {
    try {
      await ignoreQueueItem(id)
      setSelected(null)
      await loadData()
    } catch { /* ignore */ }
  }

  if (loading) return <LoadingState label="Cargando cola operativa…" />
  if (error) return <ErrorState message={error} onRetry={loadData} />

  return (
    <div className="page-content">
      {/* Summary bar */}
      {summary && (
        <div style={{
          display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16,
          background: 'rgba(255,255,255,0.03)', borderRadius: 8,
          border: '1px solid rgba(255,255,255,0.08)', padding: '12px 16px',
        }}>
          {[
            { label: 'Listos', value: summary.ready, color: '#22c55e' },
            { label: 'Esperando', value: summary.waiting, color: '#a78bfa' },
            { label: 'Abiertos', value: summary.open, color: '#3b82f6' },
            { label: 'Bloqueados', value: summary.blocked, color: '#ef4444' },
            { label: 'Críticos', value: summary.critical, color: '#dc2626' },
            { label: 'Alta prio.', value: summary.high, color: '#f97316' },
          ].map(c => (
            <div key={c.label} style={{ minWidth: 80, textAlign: 'center' }}>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: c.color }}>{c.value}</div>
              <div style={{ fontSize: '0.72rem', color: '#6b7280' }}>{c.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
        <select
          value={filterBucket}
          onChange={e => setFilterBucket(e.target.value)}
          style={{ background: '#1e2332', color: '#d1d5db', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 5, padding: '5px 10px', fontSize: '0.82rem' }}
        >
          <option value="">Todas las prioridades</option>
          <option value="critical">Crítico</option>
          <option value="high">Alta</option>
          <option value="medium">Media</option>
          <option value="low">Baja</option>
          <option value="blocked">Bloqueado</option>
        </select>
        <select
          value={filterStatus}
          onChange={e => setFilterStatus(e.target.value)}
          style={{ background: '#1e2332', color: '#d1d5db', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 5, padding: '5px 10px', fontSize: '0.82rem' }}
        >
          <option value="">Todos los estados</option>
          <option value="ready">Listo</option>
          <option value="open">Abierto</option>
          <option value="waiting">Esperando</option>
          <option value="blocked">Bloqueado</option>
          <option value="running">En curso</option>
        </select>
        <select
          value={filterAction}
          onChange={e => setFilterAction(e.target.value)}
          style={{ background: '#1e2332', color: '#d1d5db', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 5, padding: '5px 10px', fontSize: '0.82rem' }}
        >
          <option value="">Todas las acciones</option>
          <option value="upload">Subir</option>
          <option value="adapt_nomenclature">Adaptar nomenclatura</option>
          <option value="run_preflight">Preflight</option>
          <option value="wait_download">Esperar descarga</option>
          <option value="review_arr">Revisar ARR</option>
          <option value="retry_upload">Reintentar</option>
          <option value="verify_file">Verificar archivo</option>
        </select>
        <div style={{ flex: 1 }} />
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          style={{
            background: refreshing ? 'rgba(59,130,246,0.3)' : 'rgba(59,130,246,0.15)',
            color: '#3b82f6', border: '1px solid rgba(59,130,246,0.3)',
            borderRadius: 5, padding: '6px 14px', cursor: refreshing ? 'default' : 'pointer',
            fontSize: '0.82rem', fontWeight: 500,
          }}
        >
          {refreshing ? 'Refrescando…' : 'Refrescar cola'}
        </button>
      </div>

      {refreshMsg && (
        <div style={{ marginBottom: 10, padding: '8px 12px', background: 'rgba(59,130,246,0.1)', borderRadius: 6, fontSize: '0.82rem', color: '#93c5fd' }}>
          {refreshMsg}
        </div>
      )}

      {/* Detail panel */}
      {selected && (
        <DetailPanel
          item={selected}
          onClose={() => setSelected(null)}
          onResolve={handleResolve}
          onIgnore={handleIgnore}
        />
      )}

      {/* Table */}
      {items.length === 0 ? (
        <EmptyState
          title="Cola vacía"
          body='Ejecuta "Refrescar cola" para reconstruir la cola desde todas las fuentes.'
        />
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.83rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', color: '#6b7280', textAlign: 'left' }}>
                {['Prioridad', 'Estado', 'Acción', 'Tipo', 'Título', 'Motivo', 'Actualizado', ''].map(h => (
                  <th key={h} style={{ padding: '8px 10px', fontWeight: 500, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr
                  key={item.id}
                  style={{
                    borderBottom: '1px solid rgba(255,255,255,0.04)',
                    background: selected?.id === item.id ? 'rgba(59,130,246,0.06)' : undefined,
                    cursor: 'pointer',
                  }}
                  onClick={() => setSelected(selected?.id === item.id ? null : item)}
                >
                  <td style={{ padding: '8px 10px' }}><PriorityBadge bucket={item.priority_bucket} /></td>
                  <td style={{ padding: '8px 10px' }}><StatusBadge status={item.status} /></td>
                  <td style={{ padding: '8px 10px', color: '#d1d5db' }}>{ACTION_LABELS[item.action] ?? item.action}</td>
                  <td style={{ padding: '8px 10px', color: '#9ca3af', fontSize: '0.75rem' }}>{item.item_type}</td>
                  <td style={{ padding: '8px 10px', color: '#f3f4f6', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.title ?? '—'}
                  </td>
                  <td style={{ padding: '8px 10px', color: '#9ca3af', fontSize: '0.75rem', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.blockers.length > 0 ? item.blockers[0] : (item.reasons[0] ?? '—')}
                  </td>
                  <td style={{ padding: '8px 10px', color: '#6b7280', fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                    {item.updated_at ? formatDate(item.updated_at) : '—'}
                  </td>
                  <td style={{ padding: '8px 10px' }}>
                    <button
                      onClick={e => { e.stopPropagation(); handleResolve(item.id) }}
                      style={{
                        background: 'none', border: '1px solid rgba(34,197,94,0.3)', color: '#86efac',
                        borderRadius: 4, padding: '2px 8px', cursor: 'pointer', fontSize: '0.72rem',
                      }}
                    >
                      ✓
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
