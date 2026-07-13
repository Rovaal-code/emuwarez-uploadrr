import { useState } from 'react'
import { StatusBadge } from './StatusBadge'
import {
  getNomenclatureCheckInfo,
  runNomenclatureCheck,
  type NomenclatureCheckInfo,
  type NomenclatureCheckResult,
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
  /** Compact rendering for list rows (small button, no inline badge). */
  compact?: boolean
}

const LEAF = new Set(['movie', 'episode'])

function confirmMessage(info: NomenclatureCheckInfo): { proceed: boolean; force: boolean } | null {
  const { item_type, pending, available, seasons } = info
  if (available === 0) {
    window.alert('No hay contenido disponible que comprobar.')
    return null
  }
  // Leaf: check directly; only ask when re-running an already-checked file.
  if (LEAF.has(item_type)) {
    if (pending === 0) {
      return { proceed: window.confirm('Ya está comprobado. ¿Volver a ejecutar la comprobación?'), force: true }
    }
    return { proceed: true, force: false }
  }
  // Season / series: confirm the batch size.
  if (pending === 0) {
    const scope = item_type === 'series'
      ? `${seasons} temporada${seasons === 1 ? '' : 's'}, ${available} capítulo${available === 1 ? '' : 's'}`
      : `${available} capítulo${available === 1 ? '' : 's'}`
    return {
      proceed: window.confirm(`Todo el contenido disponible ya está comprobado, ¿quieres volver a ejecutarlo? (${scope})`),
      force: true,
    }
  }
  const msg = item_type === 'series'
    ? `¿Comprobar ${seasons} temporada${seasons === 1 ? '' : 's'} con ${pending} capítulo${pending === 1 ? '' : 's'} en total?`
    : `¿Comprobar ${pending} capítulo${pending === 1 ? '' : 's'}?`
  return { proceed: window.confirm(msg), force: false }
}

export function NomenclatureCheckButton({ item, onChecked, compact }: Props) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<NomenclatureCheckResult | null>(null)
  const [showResult, setShowResult] = useState(false)

  const isNA = item.nomenclature_status === 'N/A' || item.nomenclature_status == null
  const checked = item.nomenclature_status === 'Correcta' || item.nomenclature_status === 'No adaptada'

  async function runCheck() {
    setBusy(true)
    try {
      const info = await getNomenclatureCheckInfo(item.id)
      const decision = confirmMessage(info)
      if (!decision || !decision.proceed) return
      const summary = await runNomenclatureCheck(item.id, decision.force)
      window.alert(
        `Comprobados ${summary.checked}: ${summary.correct} correcta(s), ${summary.not_adapted} no adaptada(s).`,
      )
      onChecked?.()
    } catch (err) {
      window.alert(`Error al comprobar la nomenclatura: ${(err as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  async function viewResult() {
    setBusy(true)
    try {
      const info = await getNomenclatureCheckInfo(item.id)
      if (info.result) {
        setResult(info.result)
        setShowResult(true)
      } else {
        window.alert('No hay resultados de comprobación para este elemento.')
      }
    } catch (err) {
      window.alert(`Error al cargar el resultado: ${(err as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  const canViewResult = LEAF.has(item.item_type) && checked

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      {!compact && <StatusBadge status={item.nomenclature_status ?? ''} type="nomenclature" />}
      {!isNA && (
        <button
          className={compact ? 'btn btn-ghost btn-sm' : 'btn btn-secondary btn-sm'}
          onClick={runCheck}
          disabled={busy}
          title="Comprobar la nomenclatura con MediaInfo"
        >
          {busy ? 'Comprobando…' : compact ? 'Comprobar' : 'Comprobar Nomenclatura'}
        </button>
      )}
      {canViewResult && (
        <button className="btn btn-ghost btn-sm" onClick={viewResult} disabled={busy} title="Ver esperado vs. real">
          Ver resultados
        </button>
      )}

      {showResult && result && (
        <div className="modal-overlay" onClick={() => setShowResult(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title">Comprobación de nomenclatura</h2>
              <button className="btn-icon" onClick={() => setShowResult(false)} title="Cerrar">✕</button>
            </div>
            <div className="modal-body">
              <div style={{ marginBottom: 12 }}>
                <StatusBadge status={result.status ?? ''} type="nomenclature" />
              </div>
              <div style={{ display: 'grid', gap: 12 }}>
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
                  <p style={{ color: 'var(--success, #22c55e)' }}>El nombre cumple la nomenclatura de eMuwarez.</p>
                )}
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowResult(false)}>Cerrar</button>
            </div>
          </div>
        </div>
      )}
    </span>
  )
}
