import { useState, useEffect, useCallback } from 'react'
import { StatusBadge } from './StatusBadge'
import {
  getNomenclatureCheckInfo,
  runNomenclatureCheck,
  type NomenclatureCheckInfo,
  type NomenclatureCheckSummary,
} from '../api/library'

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  marginBottom: 3,
}

interface Props {
  item: { id: number; item_type: string; nomenclature_status?: string | null }
  /** Called after a successful check so the parent can reload the item/tree. */
  onChecked?: () => void
  /** Compact rendering for list rows (no inline badge, just the icon button). */
  compact?: boolean
}

const LEAF = new Set(['movie', 'episode'])

// What the check will do, in plain Spanish, given the pending/available counts.
function scopeText(info: NomenclatureCheckInfo): string {
  const { item_type, pending, available, seasons } = info
  if (available === 0) return 'No hay contenido disponible que comprobar.'
  if (LEAF.has(item_type)) {
    return pending === 0
      ? 'Este archivo ya está comprobado.'
      : 'Se comprobará la nomenclatura de este archivo con MediaInfo.'
  }
  const caps = (n: number) => `${n} capítulo${n === 1 ? '' : 's'}`
  const temps = (n: number) => `${n} temporada${n === 1 ? '' : 's'}`
  if (pending === 0) {
    const scope = item_type === 'series' ? `${temps(seasons)}, ${caps(available)}` : caps(available)
    return `Todo el contenido disponible ya está comprobado (${scope}).`
  }
  return item_type === 'series'
    ? `Se comprobarán ${caps(pending)} en ${temps(seasons)}.`
    : `Se comprobarán ${caps(pending)}.`
}

export function NomenclatureCheckButton({ item, onChecked, compact }: Props) {
  const [open, setOpen] = useState(false)
  const [info, setInfo] = useState<NomenclatureCheckInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [summary, setSummary] = useState<NomenclatureCheckSummary | null>(null)

  const isNA = item.nomenclature_status === 'N/A' || item.nomenclature_status == null

  const loadInfo = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setInfo(await getNomenclatureCheckInfo(item.id))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [item.id])

  useEffect(() => {
    if (open) {
      setSummary(null)
      loadInfo()
    }
  }, [open, loadInfo])

  async function run(force: boolean) {
    setRunning(true)
    setError(null)
    try {
      setSummary(await runNomenclatureCheck(item.id, force))
      await loadInfo()      // refresh status + stored result inside the card
      onChecked?.()         // refresh the parent's badges
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setRunning(false)
    }
  }

  const result = info?.result ?? null
  const canRun = !!info && info.available > 0
  const forceRerun = !!info && info.available > 0 && info.pending === 0

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      {!compact && <StatusBadge status={item.nomenclature_status ?? ''} type="nomenclature" />}
      {!isNA && (
        <button
          type="button"
          onClick={e => { e.stopPropagation(); setOpen(true) }}
          title="Comprobar nomenclatura"
          aria-label="Comprobar nomenclatura"
          style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 12, lineHeight: '16px', padding: '1px 6px', cursor: 'pointer',
            borderRadius: 4, border: '1px solid var(--border)',
            background: 'transparent', color: 'var(--text-secondary)',
          }}
        >
          ↗
        </button>
      )}

      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">Nomenclatura eMuwarez</h2>
              <button className="btn-icon" onClick={() => setOpen(false)} title="Cerrar">✕</button>
            </div>
            <div className="modal-body">
              {loading && <div style={{ color: 'var(--text-muted)' }}>Cargando…</div>}
              {error && <div style={{ color: 'var(--danger, #ef4444)' }}>Error: {error}</div>}

              {info && !loading && (
                <div style={{ display: 'grid', gap: 14 }}>
                  <div>
                    <StatusBadge status={(info.status ?? item.nomenclature_status) ?? ''} type="nomenclature" />
                  </div>

                  {info.available === 0 ? (
                    <p style={{ color: 'var(--text-muted)' }}>No hay contenido disponible que comprobar.</p>
                  ) : (
                    <p style={{ color: 'var(--text-secondary)', margin: 0 }}>{scopeText(info)}</p>
                  )}

                  {result && (
                    <div style={{ display: 'grid', gap: 12, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
                      <div>
                        <div style={labelStyle}>Nombre esperado</div>
                        <code style={{ wordBreak: 'break-all' }}>{result.expected || '—'}</code>
                      </div>
                      <div>
                        <div style={labelStyle}>Nombre real</div>
                        <code style={{ wordBreak: 'break-all' }}>{result.actual || '—'}</code>
                      </div>
                      {result.diff.length > 0 && (
                        <div>
                          <div style={labelStyle}>Diferencias</div>
                          <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                            {result.diff.map((d, i) => (
                              <li key={i} style={{ color: 'var(--danger, #ef4444)' }}>{d}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {result.status === 'Correcta' && (
                        <p style={{ color: 'var(--success, #22c55e)', margin: 0 }}>El nombre cumple la nomenclatura de eMuwarez.</p>
                      )}
                    </div>
                  )}

                  {summary && (
                    <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
                      Comprobados {summary.checked}: {summary.correct} correcta(s), {summary.not_adapted} no adaptada(s).
                    </p>
                  )}
                </div>
              )}
            </div>
            <div className="modal-actions">
              {canRun && (
                <button className="btn btn-primary" onClick={() => run(forceRerun)} disabled={running}>
                  {running ? 'Comprobando…' : forceRerun ? 'Volver a comprobar' : 'Comprobar'}
                </button>
              )}
              <button className="btn btn-secondary" onClick={() => setOpen(false)}>Cerrar</button>
            </div>
          </div>
        </div>
      )}
    </span>
  )
}
