import { useState, useEffect } from 'react'
import { previewSeasonPack, adaptSeasonPack } from '../api/seasonPack'
import type { SeasonPackPlanResponse, LibraryItemResponse } from '../types/api'

const CONFIRMATION_TOKEN = 'APLICAR_SEASON_PACK'

type SeasonRowState = {
  season: LibraryItemResponse
  plan: SeasonPackPlanResponse | null
  loadingPlan: boolean
  applyStatus: 'idle' | 'applying' | 'applied' | 'failed' | 'blocked'
  applyMessage: string | null
}

// Season pack preview/apply — one modal used both for a single Season row
// ("Subir"/"Nomenclatura"/"Campos" all open this, since a season pack's
// per-episode filenames are already computed automatically — there's no
// separate manual field-editing step in this first version) and for a
// Series row, where every one of its seasons is listed and applied
// sequentially (never in parallel — mirrors a human clicking "Subir" on
// each season's row one at a time).
export function SeasonPackModal({ seasons, onClose }: {
  seasons: LibraryItemResponse[]
  onClose: () => void
}) {
  const [rows, setRows] = useState<SeasonRowState[]>(
    seasons.map(season => ({ season, plan: null, loadingPlan: true, applyStatus: 'idle', applyMessage: null }))
  )
  const [confirmInput, setConfirmInput] = useState('')
  const [applying, setApplying] = useState(false)

  useEffect(() => {
    let cancelled = false
    seasons.forEach((season, idx) => {
      previewSeasonPack(season.id)
        .then(plan => {
          if (cancelled) return
          setRows(prev => prev.map((r, i) => i === idx ? { ...r, plan, loadingPlan: false } : r))
        })
        .catch(() => {
          if (cancelled) return
          setRows(prev => prev.map((r, i) => i === idx ? {
            ...r, loadingPlan: false,
            plan: { status: 'blocked', errors: ['Error al obtener la previsualización'], warnings: [], episodes: [] },
          } : r))
        })
    })
    return () => { cancelled = true }
  }, [seasons])

  async function handleApplyAll() {
    setApplying(true)
    // Sequential, never parallel — same rationale as a human clicking
    // "Subir" on each season one at a time; avoids bursts of concurrent
    // preflight/hardlink work against the filesystem.
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i]
      if (!row.plan || row.plan.status === 'blocked') {
        setRows(prev => prev.map((r, idx) => idx === i ? { ...r, applyStatus: 'blocked', applyMessage: 'Plan bloqueado' } : r))
        continue
      }
      setRows(prev => prev.map((r, idx) => idx === i ? { ...r, applyStatus: 'applying' } : r))
      try {
        const result = await adaptSeasonPack(row.season.id, { dry_run: false, apply: true, confirmation: CONFIRMATION_TOKEN })
        setRows(prev => prev.map((r, idx) => idx === i ? {
          ...r,
          applyStatus: result.status === 'applied' ? 'applied' : (result.status === 'blocked' ? 'blocked' : 'failed'),
          applyMessage: result.message ?? null,
        } : r))
      } catch (e: unknown) {
        setRows(prev => prev.map((r, idx) => idx === i ? {
          ...r, applyStatus: 'failed', applyMessage: e instanceof Error ? e.message : 'Error al aplicar',
        } : r))
      }
    }
    setApplying(false)
  }

  const allLoaded = rows.every(r => !r.loadingPlan)
  const anyApplicable = rows.some(r => r.plan && r.plan.status !== 'blocked')
  const doneCount = rows.filter(r => r.applyStatus === 'applied' || r.applyStatus === 'failed' || r.applyStatus === 'blocked').length

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <div className="modal-header">
          <h2 className="modal-title">
            {seasons.length === 1 ? 'Season pack' : `Season packs (${seasons.length} temporadas)`}
          </h2>
          <button className="btn-icon" onClick={onClose} title="Cerrar">✕</button>
        </div>
        <div className="modal-body">
          {!allLoaded && <p>Generando previsualización…</p>}
          {allLoaded && rows.map((row, idx) => (
            <div key={row.season.id} style={{ marginBottom: 14, paddingBottom: 14, borderBottom: idx < rows.length - 1 ? '1px solid var(--border)' : 'none' }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{row.season.title}</div>
              {row.plan && (
                <>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                    {row.plan.season_pack_title || '—'}
                  </div>
                  {row.plan.episodes.length > 0 && (
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      {row.plan.episodes.length} episodio(s) en el pack
                    </div>
                  )}
                  {row.plan.warnings.map((w, i) => (
                    <div key={i} style={{ fontSize: 11, color: '#f59e0b' }}>⚠ {w}</div>
                  ))}
                  {row.plan.errors.map((e, i) => (
                    <div key={i} style={{ fontSize: 11, color: 'var(--color-missing, #ef4444)' }}>✗ {e}</div>
                  ))}
                  {row.applyStatus !== 'idle' && (
                    <div style={{
                      fontSize: 12, marginTop: 4,
                      color: row.applyStatus === 'applied' ? 'var(--color-available, #22c55e)'
                        : row.applyStatus === 'applying' ? 'var(--text-secondary)'
                        : 'var(--color-missing, #ef4444)',
                    }}>
                      {row.applyStatus === 'applying' ? 'Aplicando…' : (row.applyMessage ?? row.applyStatus)}
                    </div>
                  )}
                </>
              )}
            </div>
          ))}

          {allLoaded && anyApplicable && (
            <div style={{ marginTop: 8 }}>
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Se creará un hardlink por episodio disponible dentro de una única carpeta compartida por
                temporada. Los archivos originales nunca se modifican. Para aplicar, escribe el token de
                confirmación:
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  type="text"
                  value={confirmInput}
                  onChange={e => setConfirmInput(e.target.value)}
                  placeholder={CONFIRMATION_TOKEN}
                  style={{
                    flex: 1, padding: '4px 8px', fontFamily: 'monospace', fontSize: '0.85rem',
                    background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.15)',
                    borderRadius: 4, color: 'inherit',
                  }}
                />
                <button
                  className="btn btn-primary"
                  onClick={handleApplyAll}
                  disabled={applying || confirmInput !== CONFIRMATION_TOKEN || doneCount === rows.length}
                >
                  {applying ? `Aplicando… (${doneCount}/${rows.length})` : 'Aplicar'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
