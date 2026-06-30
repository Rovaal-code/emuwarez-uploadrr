import { useState, useEffect } from 'react'
import type {
  EmuSource,
  EmuProvider,
  NomenclatureFields,
  FieldsPreviewResult,
  MkvTitlePreview,
} from '../api/nomenclature'
import {
  getEmuSources,
  getEmuProviders,
  getNomenclatureFields,
  previewNomenclatureFields,
  saveNomenclatureFields,
  previewMkvTitle,
  applyMkvTitle,
} from '../api/nomenclature'

const MKV_TOKEN = 'APLICAR_TITULO_MKV'
const PROVIDER_SOURCES = new Set(['WEB-DL'])

interface Props {
  itemId: number
  itemTitle: string
  onClose: () => void
  onSaved?: () => void
}

export function NomenclatureFieldsModal({ itemId, itemTitle, onClose, onSaved }: Props) {
  const [sources, setSources] = useState<EmuSource[]>([])
  const [providers, setProviders] = useState<EmuProvider[]>([])
  const [fields, setFields] = useState<NomenclatureFields>({})
  const [preview, setPreview] = useState<FieldsPreviewResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const [mkvPreview, setMkvPreview] = useState<MkvTitlePreview | null>(null)
  const [mkvLoading, setMkvLoading] = useState(false)
  const [mkvApplying, setMkvApplying] = useState(false)
  const [mkvToken, setMkvToken] = useState('')
  const [mkvResult, setMkvResult] = useState<MkvTitlePreview | null>(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)
      try {
        const [srcResp, prvResp, fieldsResp] = await Promise.all([
          getEmuSources(),
          getEmuProviders(),
          getNomenclatureFields(itemId),
        ])
        setSources(srcResp.sources)
        setProviders(prvResp.providers)
        setFields(fieldsResp.fields || {})
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Error cargando campos')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [itemId])

  useEffect(() => {
    if (!Object.keys(fields).length) return
    const t = setTimeout(async () => {
      try {
        const result = await previewNomenclatureFields(itemId, fields)
        setPreview(result)
      } catch {
        // preview errors are non-blocking
      }
    }, 400)
    return () => clearTimeout(t)
  }, [itemId, fields])

  const handleField = (key: string, value: string | null) => {
    setFields(prev => {
      const updated = { ...prev, [key]: value }
      if (key === 'source' && !PROVIDER_SOURCES.has(value || '')) {
        updated.provider = null
      }
      return updated
    })
    setSaved(false)
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await saveNomenclatureFields(itemId, fields)
      setSaved(true)
      onSaved?.()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error guardando campos')
    } finally {
      setSaving(false)
    }
  }

  const handleMkvPreview = async () => {
    setMkvLoading(true)
    setMkvResult(null)
    try {
      const r = await previewMkvTitle(itemId)
      setMkvPreview(r)
    } catch (e: unknown) {
      setMkvPreview({ status: 'error', errors: [e instanceof Error ? e.message : 'Error'] })
    } finally {
      setMkvLoading(false)
    }
  }

  const handleMkvApply = async () => {
    setMkvApplying(true)
    setMkvResult(null)
    try {
      const r = await applyMkvTitle(itemId, { dryRun: false, apply: true, confirmation: mkvToken })
      setMkvResult(r)
    } catch (e: unknown) {
      setMkvResult({ status: 'error', errors: [e instanceof Error ? e.message : 'Error'] })
    } finally {
      setMkvApplying(false)
    }
  }

  const sourceRequiresProvider = PROVIDER_SOURCES.has(fields.source || '')
  const providerOptions = preview?.provider_options ?? providers.map(p => ({
    code: p.code, name: p.name, label: `${p.code} (${p.name})`, tmdb_available: false,
  }))

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Campos de nomenclatura — {itemTitle}</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        {loading && <div className="modal-body"><p className="text-muted">Cargando...</p></div>}
        {error && <div className="modal-body"><p className="text-error">{error}</p></div>}

        {!loading && (
          <div className="modal-body">
            <div className="fields-grid">
              <label>Título
                <input value={fields.title || ''} onChange={e => handleField('title', e.target.value)} />
              </label>
              <label>Año
                <input value={fields.year || ''} onChange={e => handleField('year', e.target.value)} />
              </label>
              <label>Resolución
                <input value={fields.resolution || ''} onChange={e => handleField('resolution', e.target.value)} />
              </label>
              <label>Source
                <select value={fields.source || ''} onChange={e => handleField('source', e.target.value)}>
                  <option value="">— Seleccionar —</option>
                  {sources.map(s => (
                    <option key={s.code} value={s.code}>{s.label}</option>
                  ))}
                </select>
              </label>
              {sourceRequiresProvider && (
                <label>Provider
                  <select value={fields.provider || ''} onChange={e => handleField('provider', e.target.value || null)}>
                    <option value="">— Sin provider —</option>
                    {providerOptions.map(p => (
                      <option key={p.code} value={p.code}>
                        {p.label}{p.tmdb_available ? ' ★' : ''}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label>Códec vídeo
                <input value={fields.video_codec || ''} onChange={e => handleField('video_codec', e.target.value)} />
              </label>
              <label>Audio
                <input value={fields.audio_summary || ''} onChange={e => handleField('audio_summary', e.target.value)} />
              </label>
              <label>Subtítulos
                <input value={fields.subs || ''} onChange={e => handleField('subs', e.target.value)} />
              </label>
              <label>Tag
                <input value={fields.tag || ''} onChange={e => handleField('tag', e.target.value)} />
              </label>
            </div>

            {preview && (
              <div className="preview-box">
                <p><strong>Torrent name:</strong> <code>{preview.torrent_name}</code></p>
                <p><strong>Título MKV interno:</strong> <code>{preview.internal_mkv_title}</code></p>
              </div>
            )}

            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? 'Guardando…' : 'Guardar campos'}
              </button>
              {saved && <span className="text-success">✓ Guardado</span>}
            </div>

            <hr />

            <section>
              <h3>Título interno MKV</h3>
              <p className="text-muted text-sm">
                Aplica el título interno al fichero .mkv en prepared_path usando mkvpropedit.
                Requiere token de confirmación: <code>{MKV_TOKEN}</code>
              </p>
              <div className="modal-actions">
                <button className="btn btn-secondary" onClick={handleMkvPreview} disabled={mkvLoading}>
                  {mkvLoading ? 'Calculando…' : 'Previsualizar MKV'}
                </button>
              </div>
              {mkvPreview && (
                <div className="preview-box">
                  <p><strong>Status:</strong> {mkvPreview.status}</p>
                  {mkvPreview.internal_mkv_title && (
                    <p><strong>Título a aplicar:</strong> <code>{mkvPreview.internal_mkv_title}</code></p>
                  )}
                  {mkvPreview.command_preview && (
                    <p><strong>Comando:</strong> <code>{mkvPreview.command_preview}</code></p>
                  )}
                  {mkvPreview.errors?.map((e, i) => (
                    <p key={i} className="text-error">✗ {e}</p>
                  ))}
                  {mkvPreview.warnings?.map((w, i) => (
                    <p key={i} className="text-warning">⚠ {w}</p>
                  ))}
                  {mkvPreview.status === 'ready' && (
                    <div className="apply-section">
                      <input
                        placeholder={MKV_TOKEN}
                        value={mkvToken}
                        onChange={e => setMkvToken(e.target.value)}
                        className="confirm-input"
                      />
                      <button
                        className="btn btn-danger"
                        onClick={handleMkvApply}
                        disabled={mkvToken !== MKV_TOKEN || mkvApplying}
                      >
                        {mkvApplying ? 'Aplicando…' : 'Aplicar título MKV'}
                      </button>
                    </div>
                  )}
                </div>
              )}
              {mkvResult && (
                <div className={`preview-box ${mkvResult.status === 'applied' ? 'preview-ok' : 'preview-error'}`}>
                  <p><strong>Resultado:</strong> {mkvResult.status}</p>
                  {mkvResult.errors?.map((e, i) => (
                    <p key={i} className="text-error">✗ {e}</p>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
