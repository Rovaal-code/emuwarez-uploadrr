import { useState, useEffect, useCallback } from 'react'
import { StatusBadge } from './StatusBadge'
import { FitText } from './FitText'
import { useTooltip } from './Tooltip'
import { ApiClientError } from '../api/client'
import {
  getNomenclatureCheckInfo,
  runNomenclatureCheck,
  type NomenclatureCheckInfo,
  type NomenclatureCheckSummary,
} from '../api/library'

// Turn a raw API error into a specific Spanish message. The most common one
// here is a 404 with detail "Not Found" — that means the running server does
// not have the nomenclature-check endpoint yet (needs a restart after update).
function friendlyError(err: unknown): string {
  if (err instanceof ApiClientError) {
    if (err.status === 404 && (err.message === 'Not Found' || !err.message)) {
      return 'El servidor no reconoce la comprobación de nomenclatura (endpoint no encontrado). Si acabas de actualizar Uploadrr, reinicia el servidor.'
    }
    if (err.status === 404) return err.message                 // "Elemento no encontrado", etc.
    if (err.status === 500) {
      return `Error del servidor al comprobar la nomenclatura${err.message ? `: ${err.message}` : '.'} Comprueba que el binario "mediainfo" esté instalado y que el archivo sea accesible.`
    }
    return err.message || `Error ${err.status}.`
  }
  return (err as Error)?.message || 'Error desconocido.'
}

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-muted)',
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
  // A check happened while the card was open — refresh the parent's badges on
  // close (doing it right away would reload the library and unmount the card).
  const [dirty, setDirty] = useState(false)

  const isNA = item.nomenclature_status === 'N/A' || item.nomenclature_status == null

  const loadInfo = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setInfo(await getNomenclatureCheckInfo(item.id))
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setLoading(false)
    }
  }, [item.id])

  useEffect(() => {
    if (open) {
      setSummary(null)
      setDirty(false)
      loadInfo()
    }
  }, [open, loadInfo])

  const close = useCallback(() => {
    setOpen(false)
    if (dirty) onChecked?.()   // reload the list/tree only after the card is gone
  }, [dirty, onChecked])

  async function run(force: boolean) {
    setRunning(true)
    setError(null)
    try {
      setSummary(await runNomenclatureCheck(item.id, force))
      await loadInfo()      // refresh status + stored result inside the card
      setDirty(true)        // parent badges refresh when the card is closed
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setRunning(false)
    }
  }

  const result = info?.result ?? null
  const canRun = !!info && info.available > 0
  const forceRerun = !!info && info.available > 0 && info.pending === 0
  const openTip = useTooltip('Comprobar nomenclatura')
  const closeTip = useTooltip('Cerrar')

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      {!compact && <StatusBadge status={item.nomenclature_status ?? ''} type="nomenclature" />}
      {!isNA && (
        <button
          type="button"
          onClick={e => { e.stopPropagation(); setOpen(true) }}
          aria-label="Comprobar nomenclatura"
          style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 12, lineHeight: '16px', padding: '1px 6px', cursor: 'pointer',
            borderRadius: 4, border: '1px solid var(--border)',
            background: 'transparent', color: 'var(--text-secondary)',
          }}
          {...openTip.triggerProps}
        >
          ↗
          {openTip.tooltipNode}
        </button>
      )}

      {open && (
        <div className="modal-overlay" onClick={close}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 720 }}>
            <div className="modal-header">
              <h2 className="modal-title">Nomenclatura eMuwarez</h2>
              <button className="btn-icon" onClick={close} {...closeTip.triggerProps}>✕{closeTip.tooltipNode}</button>
            </div>
            <div className="modal-body">
              {loading && <div style={{ color: 'var(--text-muted)' }}>Cargando…</div>}
              {error && <div style={{ color: 'var(--color-error)' }}>{error}</div>}

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
                        <FitText text={result.expected || '—'} />
                      </div>
                      <div>
                        <div style={labelStyle}>Nombre real</div>
                        <FitText text={result.actual || '—'} />
                      </div>
                      {result.status === 'Correcta' && (
                        <p style={{ color: 'var(--color-available)', margin: 0 }}>El nombre cumple la nomenclatura de eMuwarez.</p>
                      )}
                      <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: 0 }}>
                        El Proveedor/Source se obtiene del nombre del archivo y el Tag del Grupo (lo que va tras el último «-») no se compara.
                      </p>
                    </div>
                  )}

                  {summary && (
                    <div style={{ margin: 0, display: 'grid', gap: 6 }}>
                      {summary.evaluated > 0 && (
                        <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
                          Comprobados {summary.evaluated}: {summary.correct} correcta(s), {summary.not_adapted} no adaptada(s).
                        </p>
                      )}
                      {summary.errors > 0 && (
                        <p style={{ margin: 0, color: 'var(--color-error)' }}>
                          No se pudo leer {summary.errors} archivo(s) con MediaInfo, así que siguen «No comprobada».
                          {summary.error_detail ? ` (${summary.error_detail})` : ''}
                        </p>
                      )}
                      {summary.evaluated === 0 && summary.errors === 0 && (
                        <p style={{ margin: 0, color: 'var(--text-muted)' }}>No había nada que comprobar.</p>
                      )}
                    </div>
                  )}
                </div>
              )}
              {canRun && (
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
                  <button className="btn btn-primary" onClick={() => run(forceRerun)} disabled={running}>
                    {running ? 'Comprobando…' : forceRerun ? 'Volver a comprobar' : 'Comprobar'}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </span>
  )
}
