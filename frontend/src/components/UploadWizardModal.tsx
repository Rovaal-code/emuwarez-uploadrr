import { useState, useEffect, useCallback, useRef, useLayoutEffect } from 'react'
import type { EmuSource, EmuProvider, NomenclatureFields, FieldsPreviewResult } from '../api/nomenclature'
import {
  getEmuSources,
  getEmuProviders,
  getNomenclatureFields,
  previewNomenclatureFields,
  saveNomenclatureFields,
  adaptNomenclature,
} from '../api/nomenclature'
import { uploadPreflight, startUploadJob, runUploadChecks, type UploadChecksResult } from '../api/uploads'
import { getLibrary, getMediaInfoReport, suggestProvider } from '../api/library'
import type { MediaInfoReport } from '../api/library'
import type { LibraryItemResponse } from '../types/api'

// Unified "Subir" wizard (replaces the separate Nomenclatura + Campos + Subir
// buttons). For a Series/Season it first asks which season (and episode, or the
// whole season) to target; then Step 1 generates the eMuwarez nomenclature —
// Spanish title + year from Radarr/Sonarr, Source/Provider from the filename,
// the rest from mediainfo — as editable boxes with a live preview of the final
// torrent name; Step 2 applies the nomenclature (hardlink → prepared_path),
// runs the read-only preflight, and asks for a confirmation token before the
// real upload.
const NOM_TOKEN = 'APLICAR_NOMENCLATURA'
const UPLOAD_TOKEN = 'INICIAR_UPLOADRR'
const PROVIDER_SOURCES = new Set(['WEB-DL'])
const WHOLE_SEASON = 'WHOLE_SEASON'

interface Props {
  item: LibraryItemResponse
  onClose: () => void
  onDone?: () => void
}

const labelStyle: React.CSSProperties = {
  fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4, display: 'block',
}

// Monospace one-liner (torrent name / internal title) that shrinks its font so
// the whole string fits the card width instead of wrapping onto two lines.
// Placeholder shown while the torrent name / ficha title is still being
// generated (the preview arrives a moment after opening), so the box is never
// empty first.
function GeneratingHint() {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: 13, padding: '2px 0' }}>
      <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Generando…
    </span>
  )
}

function FitText({ text, max = 13, min = 8 }: { text: string; max?: number; min?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const fit = () => {
      el.style.fontSize = `${max}px`
      const avail = el.clientWidth
      const full = el.scrollWidth
      if (full > avail && avail > 0) {
        el.style.fontSize = `${Math.max(min, Math.floor((max * avail) / full))}px`
      }
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [text, max, min])
  return (
    <div ref={ref} style={{ fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
      {text}
    </div>
  )
}

export function UploadWizardModal({ item, onClose, onDone }: Props) {
  const isSeries = item.item_type === 'series'
  const isSeason = item.item_type === 'season'
  const needsSelection = isSeries || isSeason

  // The item the nomenclature actually runs on: a movie/episode directly, a
  // season row for a whole-season pack, or an episode picked from a series.
  const [targetId, setTargetId] = useState<number | null>(needsSelection ? null : item.id)
  const [step, setStep] = useState<0 | 1 | 2>(needsSelection ? 0 : 1)

  // Step 0 — series/season selection
  const [seasons, setSeasons] = useState<LibraryItemResponse[]>([])
  const [episodes, setEpisodes] = useState<LibraryItemResponse[]>([])
  const [selSeasonId, setSelSeasonId] = useState<number | ''>(isSeason ? item.id : '')
  const [selEpisode, setSelEpisode] = useState<string>('')  // episode id or WHOLE_SEASON
  const [selError, setSelError] = useState<string | null>(null)

  // Step 1 — nomenclature fields
  const [sources, setSources] = useState<EmuSource[]>([])
  const [providers, setProviders] = useState<EmuProvider[]>([])
  const [fields, setFields] = useState<NomenclatureFields>({})
  const [preview, setPreview] = useState<FieldsPreviewResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Step 1 — on-demand MediaInfo report (only runs when the button is clicked)
  const [miReport, setMiReport] = useState<MediaInfoReport | null>(null)
  const [miLoading, setMiLoading] = useState(false)
  const [miError, setMiError] = useState<string | null>(null)

  // Step 1 — automatic TMDB provider detection for WEB-DL with no provider.
  const [detectingProvider, setDetectingProvider] = useState(false)
  // Which target we've already fired the TMDB detection for — guarantees at
  // most ONE TMDB call per resolved item while this wizard stays open.
  const detectedTargetRef = useRef<number | null>(null)

  // Step 2 — checks + (on upload) apply + preflight + start
  const [preparing, setPreparing] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<string | null>(null)
  const [checks, setChecks] = useState<UploadChecksResult | null>(null)
  const [checksLoading, setChecksLoading] = useState(false)

  const runChecks = useCallback(async () => {
    if (targetId == null) return
    setChecksLoading(true)
    try { setChecks(await runUploadChecks(targetId)) }
    catch { setChecks(null) }
    finally { setChecksLoading(false) }
  }, [targetId])

  // --- Step 0: load seasons (series) or episodes (season) ---
  useEffect(() => {
    if (!needsSelection) return
    const load = async () => {
      try {
        if (isSeries) {
          const r = await getLibrary({ parent_id: item.id, type: 'season', limit: 500 })
          setSeasons(r.items)
        } else {
          const r = await getLibrary({ parent_id: item.id, type: 'episode', limit: 500 })
          setEpisodes(r.items)
        }
      } catch (e: unknown) {
        setSelError(e instanceof Error ? e.message : 'Error cargando temporadas')
      }
    }
    load()
  }, [item.id, isSeries, needsSelection])

  // When a season is picked (series flow), load its episodes.
  useEffect(() => {
    if (!isSeries || selSeasonId === '') return
    setSelEpisode('')
    getLibrary({ parent_id: Number(selSeasonId), type: 'episode', limit: 500 })
      .then(r => setEpisodes(r.items))
      .catch(() => setEpisodes([]))
  }, [isSeries, selSeasonId])

  const confirmSelection = () => {
    setSelError(null)
    if (selEpisode === WHOLE_SEASON) {
      const seasonId = isSeason ? item.id : Number(selSeasonId)
      if (!seasonId) { setSelError('Selecciona una temporada'); return }
      setTargetId(seasonId)
    } else if (selEpisode) {
      setTargetId(Number(selEpisode))
    } else {
      setSelError('Selecciona un episodio o "Temporada entera"')
      return
    }
    setStep(1)
  }

  // --- Step 1: load nomenclature for the resolved target ---
  const loadFields = useCallback(async () => {
    if (targetId == null) return
    setLoading(true); setError(null)
    try {
      const [srcResp, prvResp, fieldsResp] = await Promise.all([
        getEmuSources(), getEmuProviders(), getNomenclatureFields(targetId),
      ])
      setSources(srcResp.sources)
      setProviders(prvResp.providers)
      setFields(fieldsResp.fields || {})
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error cargando la nomenclatura')
    } finally {
      setLoading(false)
    }
  }, [targetId])

  useEffect(() => { if (step === 1) loadFields() }, [step, loadFields])

  // Reset the MediaInfo report whenever the resolved target changes.
  useEffect(() => { setMiReport(null); setMiError(null) }, [targetId])

  // Auto-detect the provider via TMDB when Source is WEB-DL and none was
  // detected from the filename. Debounced 500ms and fired at most once per
  // resolved target, so clicking "Subir" never triggers a burst of TMDB calls.
  useEffect(() => {
    if (targetId == null || loading) return
    if (!PROVIDER_SOURCES.has(fields.source || '')) return
    if (fields.provider) return                       // already have one
    if (detectedTargetRef.current === targetId) return // already tried this item
    const t = setTimeout(async () => {
      detectedTargetRef.current = targetId            // lock before the call
      setDetectingProvider(true)
      try {
        const res = await suggestProvider(targetId)
        if (res.suggested) setField('provider', res.suggested)
      } catch { /* non-blocking — leave "Sin provider" */ }
      finally { setDetectingProvider(false) }
    }, 500)
    return () => clearTimeout(t)
  }, [targetId, loading, fields.source, fields.provider])

  const runMediaInfo = async () => {
    if (targetId == null) return
    setMiLoading(true); setMiError(null); setMiReport(null)
    try {
      setMiReport(await getMediaInfoReport(targetId))
    } catch (e: unknown) {
      setMiError(e instanceof Error ? e.message : 'Error ejecutando MediaInfo')
    } finally {
      setMiLoading(false)
    }
  }

  // Debounced live preview of the final torrent name + internal title.
  useEffect(() => {
    if (targetId == null || !Object.keys(fields).length) return
    const t = setTimeout(async () => {
      try { setPreview(await previewNomenclatureFields(targetId, fields)) } catch { /* non-blocking */ }
    }, 400)
    return () => clearTimeout(t)
  }, [targetId, fields])

  const setField = (key: string, value: string | null) => {
    setFields(prev => {
      const updated = { ...prev, [key]: value }
      if (key === 'source' && !PROVIDER_SOURCES.has(value || '')) updated.provider = null
      return updated
    })
  }

  const sourceRequiresProvider = PROVIDER_SOURCES.has(fields.source || '')

  // Entering step 2 only stores the edited fields and runs the read-only
  // checks. It does NOT apply the nomenclature nor create an upload job — a job
  // must only appear in "Subidas" once the user actually uploads.
  const goToUpload = async () => {
    if (targetId == null) return
    setPreparing(true); setUploadMsg(null)
    try { await saveNomenclatureFields(targetId, fields) } catch { /* non-blocking */ }
    setPreparing(false)
    setStep(2)
    runChecks()
  }

  const canUpload = !!checks?.ready
  // The real upload: apply the nomenclature, create the preflight job and start
  // it — all only now that every check passed and the user confirmed. Nothing
  // reaches "Subidas" before this.
  const doUpload = async () => {
    if (targetId == null || !canUpload) return
    setUploading(true); setUploadMsg(null)
    try {
      await saveNomenclatureFields(targetId, fields)
      const applied = await adaptNomenclature(targetId, { apply: true, confirmation: NOM_TOKEN })
      if (applied.status && applied.status !== 'applied') {
        setUploadMsg(`✗ No se pudo aplicar la nomenclatura (estado: ${applied.status}).`)
        return
      }
      const pf = await uploadPreflight(targetId)
      if (pf.status !== 'ready' || !pf.job?.id) {
        setUploadMsg(`✗ El preflight no está listo (estado: ${pf.status}).`)
        return
      }
      const r = await startUploadJob(pf.job.id, { dry_run: false, start: true, confirmation: UPLOAD_TOKEN })
      setUploadMsg(`✓ Subida iniciada (${r.status ?? 'ok'}).`)
      onDone?.()
    } catch (e: unknown) {
      setUploadMsg(`✗ ${e instanceof Error ? e.message : 'Error iniciando la subida'}`)
    } finally {
      setUploading(false)
    }
  }

  const fieldBox = (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px' }}>
        <label><span style={labelStyle}>Título</span>
          <input className="form-input" value={fields.title || ''} onChange={e => setField('title', e.target.value)} />
        </label>
        <label><span style={labelStyle}>Año</span>
          <input className="form-input" value={fields.year || ''} onChange={e => setField('year', e.target.value)} />
        </label>
        {fields.season_episode != null && (
          <label><span style={labelStyle}>Temporada / Episodio</span>
            <input className="form-input" value={fields.season_episode || ''} onChange={e => setField('season_episode', e.target.value)} />
          </label>
        )}
        <label><span style={labelStyle}>Resolución</span>
          <input className="form-input" value={fields.resolution || ''} onChange={e => setField('resolution', e.target.value)} />
        </label>
        <label><span style={labelStyle}>Source</span>
          <select className="form-input" value={fields.source || ''} onChange={e => setField('source', e.target.value)}>
            <option value="">— Seleccionar —</option>
            {sources.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}
          </select>
        </label>
        {sourceRequiresProvider && (
          <label><span style={labelStyle}>Provider</span>
            {detectingProvider ? (
              <div className="form-input" style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
                <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Detectando…
              </div>
            ) : (
              <select className="form-input" value={fields.provider || ''} onChange={e => setField('provider', e.target.value || null)}>
                <option value="">— Sin provider —</option>
                {providers.map(p => <option key={p.code} value={p.code}>{p.name} ({p.code})</option>)}
              </select>
            )}
          </label>
        )}
        <label><span style={labelStyle}>Códec de vídeo</span>
          <input className="form-input" value={fields.video_codec || ''} onChange={e => setField('video_codec', e.target.value)} />
        </label>
        <label><span style={labelStyle}>Audio</span>
          <input className="form-input" value={fields.audio_summary || ''} onChange={e => setField('audio_summary', e.target.value)} />
        </label>
        <label><span style={labelStyle}>Subtítulos</span>
          <input className="form-input" value={fields.subs || ''} onChange={e => setField('subs', e.target.value)} />
        </label>
        <label><span style={labelStyle}>Tag</span>
          <input className="form-input" value={fields.tag || ''} onChange={e => setField('tag', e.target.value)} />
        </label>
      </div>
      <div style={{ marginTop: 16, padding: '12px 14px', background: 'rgba(255,255,255,0.03)', borderRadius: 8, border: '1px solid var(--border)' }}>
        <div style={labelStyle}>Nombre final del torrent (eMuwarez)</div>
        {preview?.torrent_name ? <FitText text={preview.torrent_name} /> : <GeneratingHint />}
        <div style={{ ...labelStyle, marginTop: 10 }}>Título de la ficha</div>
        {preview?.internal_mkv_title ? <FitText text={preview.internal_mkv_title} /> : <GeneratingHint />}
      </div>
    </>
  )

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 720 }}>
        <div className="modal-header">
          <h2 className="modal-title">Subir a eMuwarez — {item.title}</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div style={{ display: 'flex', gap: 8, padding: '0 20px', marginTop: 8, fontSize: 12, flexWrap: 'wrap' }}>
          {needsSelection && <><span style={{ fontWeight: step === 0 ? 700 : 400, color: step === 0 ? 'var(--text)' : 'var(--text-muted)' }}>0. Selección</span><span style={{ color: 'var(--text-muted)' }}>→</span></>}
          <span style={{ fontWeight: step === 1 ? 700 : 400, color: step === 1 ? 'var(--text)' : 'var(--text-muted)' }}>1. Nomenclatura</span>
          <span style={{ color: 'var(--text-muted)' }}>→</span>
          <span style={{ fontWeight: step === 2 ? 700 : 400, color: step === 2 ? 'var(--text)' : 'var(--text-muted)' }}>2. Subida a eMuwarez</span>
        </div>

        {step === 0 && (
          <div className="modal-body">
            <p className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
              Elige qué subir de <strong>{item.title}</strong>: un episodio concreto, o la temporada entera.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px' }}>
              {isSeries && (
                <label><span style={labelStyle}>Temporada</span>
                  <select className="form-input" value={selSeasonId} onChange={e => setSelSeasonId(e.target.value ? Number(e.target.value) : '')}>
                    <option value="">— Seleccionar —</option>
                    {seasons.map(s => <option key={s.id} value={s.id}>{s.title || `Temporada ${s.season_number}`}</option>)}
                  </select>
                </label>
              )}
              <label><span style={labelStyle}>Episodio</span>
                <select className="form-input" value={selEpisode} onChange={e => setSelEpisode(e.target.value)} disabled={isSeries && selSeasonId === ''}>
                  <option value="">— Seleccionar —</option>
                  <option value={WHOLE_SEASON}>★ Temporada entera</option>
                  {episodes.map(ep => (
                    <option key={ep.id} value={ep.id}>
                      {ep.episode_number != null ? `E${String(ep.episode_number).padStart(2, '0')} — ` : ''}{ep.title}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {selError && <p className="text-error" style={{ marginTop: 10 }}>{selError}</p>}
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
              <button className="btn btn-primary" onClick={confirmSelection}>Continuar →</button>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="modal-body">
            {loading && (
              <div style={{ padding: '36px 0', textAlign: 'center' }}>
                <div style={{ fontSize: 15, fontWeight: 600 }}>Generando nomenclatura con MediaInfo…</div>
                <div className="text-muted" style={{ fontSize: 12, marginTop: 6 }}>
                  Leyendo el archivo real (Radarr/Sonarr como respaldo si no es accesible).
                </div>
              </div>
            )}
            {error && <p className="text-error">{error}</p>}
            {!loading && !error && (
              <>
                <p className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
                  Los campos técnicos (audio por pista, códec, HDR/DV) se leen con MediaInfo del archivo
                  real; el título/año vienen de Radarr/Sonarr y el Source/Provider del nombre del archivo.
                  Puedes ajustar cualquier campo, o ver el detalle de MediaInfo abajo.
                </p>
                {fieldBox}

                <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>MediaInfo del archivo</div>
                      <div className="text-muted" style={{ fontSize: 11, marginTop: 2 }}>
                        Muestra los datos de MediaInfo del archivo real y compara cada valor con el que iría a eMuwarez.
                      </div>
                    </div>
                    <button className="btn btn-primary" onClick={runMediaInfo} disabled={miLoading || targetId == null}>
                      {miLoading ? 'Cargando…' : miReport ? 'Actualizar MediaInfo' : 'Ver MediaInfo'}
                    </button>
                  </div>

                  {miError && <p className="text-error" style={{ fontSize: 12, marginTop: 10 }}>✗ {miError}</p>}
                  {miReport && !miReport.available && (
                    <p className="text-warning" style={{ fontSize: 12, marginTop: 10 }}>⚠ {miReport.message}</p>
                  )}
                  {miReport?.available && (
                    <div style={{ marginTop: 12, overflowX: 'auto', border: '1px solid var(--border)', borderRadius: 8 }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                        <thead>
                          <tr style={{ background: 'rgba(255,255,255,0.03)' }}>
                            <th style={{ textAlign: 'left', padding: '8px 12px', fontWeight: 600, color: 'var(--text-muted)' }}>Campo</th>
                            <th style={{ textAlign: 'left', padding: '8px 12px', fontWeight: 600, color: 'var(--text-muted)' }}>MediaInfo</th>
                            <th style={{ textAlign: 'left', padding: '8px 12px', fontWeight: 600, color: 'var(--text-muted)' }}>eMuwarez</th>
                          </tr>
                        </thead>
                        <tbody>
                          {miReport.rows.map((r, i) => (
                            <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
                              <td style={{ padding: '7px 12px', fontWeight: 600 }}>{r.field}</td>
                              <td style={{ padding: '7px 12px', fontFamily: 'monospace', color: 'var(--text-muted)', wordBreak: 'break-word' }}>{r.mediainfo}</td>
                              <td style={{ padding: '7px 12px', fontFamily: 'monospace', wordBreak: 'break-word' }}>{r.emu}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
                  {needsSelection
                    ? <button className="btn btn-secondary" onClick={() => setStep(0)}>← Selección</button>
                    : <span />}
                  <button className="btn btn-primary" onClick={goToUpload} disabled={preparing || !preview}>
                    {preparing ? 'Preparando…' : 'Continuar →'}
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="modal-body">
            <div style={{ marginBottom: 14, padding: '12px 14px', background: 'rgba(255,255,255,0.03)', borderRadius: 8, border: '1px solid var(--border)' }}>
              <div style={labelStyle}>Nombre final del torrent</div>
              <FitText text={preview?.torrent_name || '–'} />
              <div style={{ ...labelStyle, marginTop: 10 }}>Título</div>
              <FitText text={preview?.internal_mkv_title || '–'} />
            </div>

            {/* Pre-upload checks card */}
            <div style={{ padding: '12px 14px', background: 'rgba(255,255,255,0.03)', borderRadius: 8, border: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <div style={labelStyle}>Comprobaciones previas</div>
                {checksLoading && <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />}
              </div>
              {checks?.checks.map(c => (
                <div key={c.id} style={{ display: 'flex', gap: 8, alignItems: 'baseline', padding: '3px 0' }}>
                  <span style={{ color: c.status === 'ok' ? '#22c55e' : '#ef4444', fontWeight: 700 }}>{c.status === 'ok' ? '✓' : '✗'}</span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13 }}>{c.label}</div>
                    {c.message && <div style={{ fontSize: 11, color: 'var(--text-muted)', wordBreak: 'break-all' }}>{c.message}</div>}
                  </div>
                </div>
              ))}
              {checksLoading && !checks && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Comprobando…</div>}
              {!checksLoading && checks && (
                <div style={{ marginTop: 10, fontWeight: 600, color: checks.ready ? '#22c55e' : '#ef4444' }}>
                  {checks.ready ? '✓ Todo listo para subir' : '✗ La subida no se puede realizar'}
                </div>
              )}
              {!checksLoading && (
                <button className="btn btn-secondary btn-sm" style={{ marginTop: 10, fontSize: 12 }} onClick={runChecks} type="button">
                  ↻ Volver a comprobar
                </button>
              )}
            </div>

            {checks?.ready && (
              <p style={{ marginTop: 12, fontSize: 13 }}>
                ¿Seguro que quieres subir <strong>«{item.title}»</strong> a eMuwarez? Se iniciará la subida real.
              </p>
            )}
            {uploadMsg && <p style={{ fontSize: 13, marginTop: 8 }}>{uploadMsg}</p>}

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => setStep(1)} disabled={uploading}>← Volver</button>
              <button
                className="btn btn-primary"
                onClick={doUpload}
                disabled={!canUpload || uploading || checksLoading}
                title={canUpload ? '' : 'Alguna comprobación ha fallado o aún está en curso'}
              >
                {uploading ? 'Subiendo…' : 'Subir a eMuwarez'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
