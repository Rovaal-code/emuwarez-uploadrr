import { useEffect, useState } from 'react'
import { checkAutoUploadSource, queueAutoUpload, type AutoUploadSourceCheck } from '../api/uploads'
import { suggestProvider } from '../api/library'
import { getEmuSources, getEmuProviders } from '../api/nomenclature'
import type { EmuSource, EmuProvider } from '../api/nomenclature'

const PROVIDER_SOURCES = new Set(['WEB-DL'])

// Gate in front of an "Automático" upload (or a sequential batch of them, one
// per season): before each target is actually queued, does a quick source
// check (name vs Radarr/Sonarr vs MediaInfo-bitrate — see
// services/source_assistant.py::check_auto_upload_source). Silent and
// instant when the 3 agree (or the name already resolves it); pauses and
// asks the user to pick the source (and provider, if WEB-DL) only when
// Radarr/Sonarr and MediaInfo actually disagree with no name to break the tie.
export function AutoUploadSourceGate({ targetIds, onNavigate, onClose, onDone }: {
  targetIds: number[]
  onNavigate?: (page: string) => void
  onClose: () => void
  onDone?: () => void
}) {
  const [index, setIndex] = useState(0)
  const [phase, setPhase] = useState<'checking' | 'disparity' | 'queuing' | 'done'>('checking')
  const [check, setCheck] = useState<AutoUploadSourceCheck | null>(null)
  const [okCount, setOkCount] = useState(0)
  const [sources, setSources] = useState<EmuSource[]>([])
  const [providers, setProviders] = useState<EmuProvider[]>([])
  const [chosenSource, setChosenSource] = useState('')
  const [chosenProvider, setChosenProvider] = useState<string | null>(null)
  const [detectingProvider, setDetectingProvider] = useState(false)

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

  const sourceRequiresProvider = PROVIDER_SOURCES.has(chosenSource)
  const goToUploads = () => { onDone?.(); onNavigate?.('uploads'); onClose() }

  if (phase === 'done') {
    return (
      <div className="modal-body">
        <div style={{ padding: '20px 0', textAlign: 'center' }}>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>
            {total > 1 ? `${okCount} de ${total} subida(s) preparada(s) en Subidas` : 'Todo OK — subida preparada en Subidas'}
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
          El nombre del archivo no indica el source, y Radarr/Sonarr no coincide con lo que estima MediaInfo. Elige el source correcto para continuar.
        </p>
        <div className="detail-card" style={{ borderRadius: 8, marginBottom: 14, overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '7px 12px', color: 'var(--text-muted)', fontWeight: 600, borderBottom: '1px solid var(--border)' }}>Radarr/Sonarr</th>
                <th style={{ textAlign: 'left', padding: '7px 12px', color: 'var(--text-muted)', fontWeight: 600, borderBottom: '1px solid var(--border)' }}>MediaInfo (bitrate)</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: '7px 12px', fontFamily: 'monospace' }}>{check.from_radarr || '—'}</td>
                <td style={{ padding: '7px 12px', fontFamily: 'monospace' }}>{check.from_mediainfo || '—'}</td>
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
