import { useState, useCallback } from 'react'
import { previewTrackRemux, applyTrackRemux, type TrackRemuxPreview, type TrackRemuxTrack } from '../api/nomenclature'
import { ApiClientError } from '../api/client'

const REMUX_TOKEN = 'REORDENAR_PISTAS'

function friendlyError(err: unknown): string {
  if (err instanceof ApiClientError) {
    if (err.status === 404 && (err.message === 'Not Found' || !err.message)) {
      return 'El servidor no reconoce el reordenado de pistas (endpoint no encontrado). Si acabas de actualizar Uploadrr, reinicia el servidor.'
    }
    return err.message || `Error ${err.status}.`
  }
  return (err as Error)?.message || 'Error desconocido.'
}

const TYPE_LABEL: Record<string, string> = { video: 'Vídeo', audio: 'Audio', subtitles: 'Subtítulos' }

function TrackTable({ tracks }: { tracks: TrackRemuxTrack[] }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table" style={{ fontSize: 12.5 }}>
        <thead>
          <tr>
            <th>Tipo</th>
            <th>Idioma (pista)</th>
            <th>Nombre actual</th>
            <th>Nombre nuevo</th>
            <th>Predeterminada</th>
          </tr>
        </thead>
        <tbody>
          {tracks.map(t => (
            <tr key={t.id} style={t.changed ? { background: 'rgba(96,165,250,0.08)' } : undefined}>
              <td style={{ whiteSpace: 'nowrap', color: 'var(--text-muted)' }}>{TYPE_LABEL[t.type] ?? t.type}</td>
              <td style={{ whiteSpace: 'nowrap', fontFamily: 'monospace', color: 'var(--text-secondary)' }} title="Idioma leído por mkvmerge en la pista (no depende del nombre que le puso el grupo anterior)">
                {t.language || '—'}
              </td>
              <td style={{ color: 'var(--text-muted)' }}>{t.current_name || '—'}</td>
              <td style={{ fontWeight: t.changed ? 600 : 400 }}>{t.new_name}</td>
              <td>
                {t.default_before === t.default_after
                  ? (t.default_after ? 'Sí' : '—')
                  : <span>{t.default_before ? 'Sí' : '—'} → <strong>{t.default_after ? 'Sí' : '—'}</strong></span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

interface Props {
  item: { id: number; item_type: string; track_remux_status?: string | null }
  /** Called after a successful apply so the parent can reload the item. */
  onApplied?: () => void
}

export function TrackRemuxButton({ item, onApplied }: Props) {
  const [open, setOpen] = useState(false)
  const [preview, setPreview] = useState<TrackRemuxPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const [token, setToken] = useState('')
  const [result, setResult] = useState<TrackRemuxPreview | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setPreview(await previewTrackRemux(item.id))
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setLoading(false)
    }
  }, [item.id])

  const openModal = () => {
    setResult(null)
    setToken('')
    setOpen(true)
    load()
  }

  const close = () => {
    setOpen(false)
    if (result?.status === 'applied') onApplied?.()
  }

  const handleApply = async () => {
    setApplying(true)
    setError(null)
    try {
      const r = await applyTrackRemux(item.id, { dryRun: false, apply: true, confirmation: token })
      setResult(r)
      if (r.status === 'applied') setPreview(r)
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setApplying(false)
    }
  }

  if (item.item_type !== 'movie' && item.item_type !== 'episode') return null

  return (
    <>
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={openModal}
        title="Reordena las pistas de audio/subtítulos (Español primero, luego Català, luego Inglés) y les pone un nombre claro"
      >
        Ordenar y renombrar pistas
      </button>

      {open && (
        <div className="modal-overlay" onClick={close}>
          <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 760 }}>
            <div className="modal-header">
              <h2 className="modal-title">Ordenar y renombrar pistas</h2>
              <button className="modal-close" onClick={close}>✕</button>
            </div>
            <div className="modal-body">
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 0 }}>
                Remux (mkvmerge, sin recodificar): reordena audio y subtítulos — Español (Castellano) primero,
                luego Català, luego Inglés, y el resto tal como estaban — y pone un nombre claro a cada pista
                de vídeo, audio y subtítulos. No modifica la imagen/sonido, solo la estructura del contenedor.
              </p>

              {loading && <div style={{ color: 'var(--text-muted)' }}>Cargando…</div>}
              {error && <p style={{ color: 'var(--danger, #ef4444)' }}>{error}</p>}

              {preview && !loading && (
                <div style={{ display: 'grid', gap: 12 }}>
                  {preview.errors?.map((e, i) => (
                    <p key={i} style={{ color: 'var(--danger, #ef4444)', margin: 0 }}>✗ {e}</p>
                  ))}
                  {preview.warnings?.map((w, i) => (
                    <p key={i} style={{ color: '#eab308', margin: 0 }}>⚠ {w}</p>
                  ))}

                  {preview.ordered_tracks && preview.ordered_tracks.length > 0 && (
                    <TrackTable tracks={preview.ordered_tracks} />
                  )}

                  {preview.status === 'ready' && (
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4, flexWrap: 'wrap' }}>
                      <input
                        placeholder={REMUX_TOKEN}
                        value={token}
                        onChange={e => setToken(e.target.value)}
                        className="form-input"
                        style={{ maxWidth: 220 }}
                      />
                      <button
                        className="btn btn-danger"
                        onClick={handleApply}
                        disabled={token !== REMUX_TOKEN || applying}
                      >
                        {applying ? 'Remuxeando…' : 'Aplicar (reescribe el archivo)'}
                      </button>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        Requiere confirmación: <code>{REMUX_TOKEN}</code>. Reescribe el .mkv real (copia de flujos, sin recodificar) — puede tardar según el tamaño del archivo.
                      </span>
                    </div>
                  )}
                </div>
              )}

              {result && (
                <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
                  <p style={{ margin: 0, color: result.status === 'applied' ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)' }}>
                    {result.status === 'applied' ? '✓ Pistas reordenadas y renombradas.' : `✗ ${result.status}`}
                  </p>
                  {result.errors?.map((e, i) => (
                    <p key={i} style={{ color: 'var(--danger, #ef4444)', margin: '4px 0 0' }}>{e}</p>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
