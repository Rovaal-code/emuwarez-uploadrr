import { useEffect, useState } from 'react'
import { checkAutoUploadSource, queueAutoUpload, type AutoUploadSourceCheck } from '../api/uploads'
import { suggestProvider } from '../api/library'
import { getEmuSources, getEmuProviders, getNomenclatureFields } from '../api/nomenclature'
import type { EmuSource, EmuProvider, SourceComparison } from '../api/nomenclature'
import { Tooltip } from './Tooltip'
import { SourceComparisonModal } from './SourceComparisonModal'

const PROVIDER_SOURCES = new Set(['WEB-DL'])

// Gate in front of an "Automático" upload (or a sequential batch of them, one
// per season): before each target is actually queued, does a quick source
// check (name vs Radarr/Sonarr vs Internal Source Tool — see
// services/source_assistant.py::check_auto_upload_source). Silent and
// instant when every available value agrees; pauses and asks the user to
// pick the source (and provider, if WEB-DL) as soon as any two disagree —
// the name is often just absent, so this doesn't wait for all three to be
// present before comparing.
export function AutoUploadSourceGate({ targetIds, onNavigate, onClose, onDone }: {
  targetIds: number[]
  onNavigate?: (page: string) => void
  onClose: () => void
  onDone?: () => void
}) {
  const [index, setIndex] = useState(0)
  const [phase, setPhase] = useState<'checking' | 'disparity' | 'inaccessible' | 'queuing' | 'done'>('checking')
  const [check, setCheck] = useState<AutoUploadSourceCheck | null>(null)
  const [inaccessibleMsg, setInaccessibleMsg] = useState<string | null>(null)
  const [okCount, setOkCount] = useState(0)
  const [sources, setSources] = useState<EmuSource[]>([])
  const [providers, setProviders] = useState<EmuProvider[]>([])
  const [chosenSource, setChosenSource] = useState('')
  const [chosenProvider, setChosenProvider] = useState<string | null>(null)
  const [detectingProvider, setDetectingProvider] = useState(false)
  // Full Internal Source Tool breakdown (evidence/ranking) — checkAutoUploadSource
  // only returns the 3 plain values needed for the disparity table itself, so
  // this is fetched lazily, only if the user actually clicks the blinking
  // value to see the detailed comparison (same one the manual wizard shows).
  const [comparisonDetail, setComparisonDetail] = useState<SourceComparison | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [showComparisonModal, setShowComparisonModal] = useState(false)

  const total = targetIds.length
  const currentId = targetIds[index]

  async function proceedQueue(id: number, overrides?: { source?: string; provider?: string }) {
    setPhase('queuing')
    try {
      const r = await queueAutoUpload(id, overrides)
      if (r.status === 'staging' || r.status === 'queued') setOkCount(c => c + 1)
    } catch { /* keep going with the rest of the batch */ }
  }

  // Drives one target at a time: check -> (queue directly, or pause on disparity).
  useEffect(() => {
    if (index >= total) { setPhase('done'); return }
    let alive = true
    setPhase('checking')
    checkAutoUploadSource(targetIds[index])
      .then(async result => {
        if (!alive) return
        if (!result.accessible) {
          // Don't queue a job we already know will fail once upload_queue.py
          // tries to read the file for real — pause here and let the user
          // see why and skip it, same failure the manual wizard would
          // otherwise surface first (see check_auto_upload_source's own
          // docstring for why this isn't fail-open like a plain disparity).
          setInaccessibleMsg(result.message || 'No se puede acceder al archivo.')
          setPhase('inaccessible')
          return
        }
        if (!result.disparity) {
          await proceedQueue(targetIds[index])
          if (alive) setIndex(i => i + 1)
          return
        }
        setCheck(result)
        setChosenSource('')
        setChosenProvider(null)
        setPhase('disparity')
        if (sources.length === 0) getEmuSources().then(r => { if (alive) setSources(r.sources) })
      })
      .catch(async () => {
        // Fail open client-side too — never block the batch over a check failure.
        if (!alive) return
        await proceedQueue(targetIds[index])
        if (alive) setIndex(i => i + 1)
      })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, total])

  // Auto-suggest provider (same source as the manual wizard) once the user
  // picks WEB-DL in the disparity dialog.
  useEffect(() => {
    if (phase !== 'disparity' || chosenSource !== 'WEB-DL') return
    let alive = true
    if (providers.length === 0) getEmuProviders().then(r => { if (alive) setProviders(r.providers) })
    setDetectingProvider(true)
    suggestProvider(currentId)
      .then(s => { if (alive) setChosenProvider(s.suggested) })
      .finally(() => { if (alive) setDetectingProvider(false) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, chosenSource])

  const confirmDisparity = async () => {
    if (!chosenSource) return
    await proceedQueue(currentId, { source: chosenSource, provider: chosenProvider || undefined })
    setIndex(i => i + 1)
  }

  // No overrides can fix an unreadable file — the only way forward is to
  // leave it out of the batch (not counted in okCount) and move on.
  const skipInaccessible = () => setIndex(i => i + 1)

  const sourceRequiresProvider = PROVIDER_SOURCES.has(chosenSource)
  const goToUploads = () => { onDone?.(); onNavigate?.('uploads'); onClose() }

  const openComparisonDetail = async () => {
    setLoadingDetail(true)
    try {
      const fields = await getNomenclatureFields(currentId)
      if (fields.source_comparison) {
        setComparisonDetail(fields.source_comparison)
        setShowComparisonModal(true)
      }
    } catch { /* ignore — the value just stays non-clickable-looking for this attempt */ }
    finally { setLoadingDetail(false) }
  }

  if (phase === 'inaccessible') {
    return (
      <div className="modal-body">
        <p className="text-muted" style={{ fontSize: 12, marginTop: 0, marginBottom: 12 }}>
          {total > 1 ? `Temporada ${index + 1} de ${total}: ` : ''}
          No se puede comprobar el source porque el archivo no es accesible.
        </p>
        <div className="detail-card" style={{ borderRadius: 8, padding: '12px 14px', marginBottom: 14, color: '#ef4444' }}>
          ✗ {inaccessibleMsg}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn btn-primary" onClick={skipInaccessible} type="button">
            {total > 1 ? 'Omitir y continuar' : 'Entendido'}
          </button>
        </div>
      </div>
    )
  }

  if (phase === 'done') {
    return (
      <div className="modal-body">
        <div style={{ padding: '20px 0', textAlign: 'center' }}>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>
            {total > 1 ? `${okCount} de ${total} subida(s) añadida(s) a la cola de subidas` : 'Subida añadida a la cola de subidas'}
          </div>
          <button className="btn btn-primary" onClick={goToUploads} type="button">Ir a Subidas</button>
        </div>
      </div>
    )
  }

  if (phase === 'disparity' && check) {
    return (
      <div className="modal-body">
        <p className="text-muted" style={{ fontSize: 12, marginTop: 0, marginBottom: 12 }}>
          {total > 1 ? `Temporada ${index + 1} de ${total}: ` : ''}
          El nombre del archivo, Radarr/Sonarr y la Internal Source Tool no coinciden en el source. Elige el source correcto para continuar.
        </p>
        <div className="detail-card" style={{ borderRadius: 8, marginBottom: 14, overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '7px 12px', color: 'var(--text-muted)', fontWeight: 600, borderBottom: '1px solid var(--border)' }}>Nombre del archivo</th>
                <th style={{ textAlign: 'left', padding: '7px 12px', color: 'var(--text-muted)', fontWeight: 600, borderBottom: '1px solid var(--border)' }}>Radarr/Sonarr</th>
                <th style={{ textAlign: 'left', padding: '7px 12px', color: 'var(--text-muted)', fontWeight: 600, borderBottom: '1px solid var(--border)' }}>Internal Source Tool</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: '7px 12px', fontFamily: 'monospace' }}>{check.from_name || '—'}</td>
                <td style={{ padding: '7px 12px', fontFamily: 'monospace' }}>{check.from_radarr || '—'}</td>
                <td style={{ padding: '7px 12px', fontFamily: 'monospace' }}>
                  {check.from_mediainfo ? (
                    <Tooltip content="Ver comparación detallada">
                      <button
                        type="button"
                        className="source-bitrate-link badge-blink"
                        onClick={openComparisonDetail}
                        disabled={loadingDetail}
                      >
                        {check.from_mediainfo}
                      </button>
                    </Tooltip>
                  ) : '—'}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <label style={{ display: 'block', marginBottom: sourceRequiresProvider ? 12 : 16 }}>
          <span style={{ display: 'block', fontSize: 12.5, color: 'var(--text-muted)', marginBottom: 4 }}>Source</span>
          <select className="form-input" value={chosenSource} onChange={e => setChosenSource(e.target.value)}>
            <option value="">— Seleccionar —</option>
            {sources.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}
          </select>
        </label>
        {sourceRequiresProvider && (
          <label style={{ display: 'block', marginBottom: 16 }}>
            <span style={{ display: 'block', fontSize: 12.5, color: 'var(--text-muted)', marginBottom: 4 }}>Proveedor</span>
            {detectingProvider ? (
              <div className="form-input" style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
                <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Detectando…
              </div>
            ) : (
              <select className="form-input" value={chosenProvider || ''} onChange={e => setChosenProvider(e.target.value || null)}>
                <option value="">— Sin proveedor —</option>
                {providers.map(p => <option key={p.code} value={p.code}>{p.name} ({p.code})</option>)}
              </select>
            )}
          </label>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn btn-primary" onClick={confirmDisparity} disabled={!chosenSource} type="button">
            Confirmar y subir
          </button>
        </div>
        {showComparisonModal && comparisonDetail && (
          <SourceComparisonModal
            comparison={comparisonDetail}
            initialShowDetail
            onClose={() => setShowComparisonModal(false)}
          />
        )}
      </div>
    )
  }

  return (
    <div className="modal-body">
      <div style={{ padding: '36px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
        <span className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
        <div style={{ fontSize: 15, fontWeight: 600 }}>
          {phase === 'checking' ? 'Verificando disparidades…' : 'Preparando la subida automática…'}
          {total > 1 ? ` (${index + 1} de ${total})` : ''}
        </div>
      </div>
    </div>
  )
}
