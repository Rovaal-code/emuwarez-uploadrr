import { useState } from 'react'
import type { LibraryItemResponse } from '../types/api'
import { useTooltip } from './Tooltip'

// eMuwarez "Petición" (request) creation form. Built from the field spec the
// user captured from eMuwarez's web form. Submission is intentionally gated:
// the real create/edit endpoints haven't been captured yet, so "Enviar"
// validates and previews the payload but does not POST. The form is prefilled
// from the library item so peticiones start from content you already track.
const CATEGORIES: { value: string; label: string; enabled: boolean }[] = [
  { value: 'movie', label: 'Películas', enabled: true },
  { value: 'tv', label: 'Series', enabled: true },
  { value: 'doc', label: 'Documentales', enabled: true },
  { value: 'music', label: 'Música', enabled: false },
  { value: 'games', label: 'Juegos', enabled: false },
  { value: 'software', label: 'Software', enabled: false },
]
const TYPES = ['Any', 'Full Disc', 'Remux', 'Encode', 'WEB-DL', 'WEBRIP', 'HDTV', 'SD', 'STEAMRIP']
const RESOLUTIONS = ['Any', '4320p', '2160p', '1080p', '1080i', '720p', '540p', '576p', '480p', 'Otras']
const MIN_REWARD = 100

const onlyDigits = (v: string) => v.replace(/\D+/g, '')

// Build the public URL for an external ID so the user can verify the
// autofilled ID really points at the right movie/series/documentary.
function idVerifyUrl(kind: 'tmdb' | 'imdb' | 'tvdb' | 'mal', id: string, isSeries: boolean): string | null {
  if (!id) return null
  switch (kind) {
    case 'tmdb': return `https://www.themoviedb.org/${isSeries ? 'tv' : 'movie'}/${id}`
    case 'imdb': return `https://www.imdb.com/title/tt${id.padStart(7, '0')}/`
    case 'tvdb': return `https://thetvdb.com/dereferrer/series/${id}`
    case 'mal':  return `https://myanimelist.net/anime/${id}`
  }
}

interface Props {
  item: LibraryItemResponse
  onClose: () => void
}

const labelStyle: React.CSSProperties = {
  fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4, display: 'block',
}

export function RequestFormModal({ item, onClose }: Props) {
  const isSeriesLike = item.item_type === 'series' || item.item_type === 'season' || item.item_type === 'episode'

  const [category, setCategory] = useState(isSeriesLike ? 'tv' : 'movie')
  // eMuwarez expects the year in the title: "Título (AÑO)". Prefill it from the
  // item's year when known (>0), without duplicating an already-present year.
  const [title, setTitle] = useState(() => {
    const base = item.title || ''
    return item.year && item.year > 0 && !/\(\d{4}\)\s*$/.test(base)
      ? `${base} (${item.year})`
      : base
  })
  // Tipo por defecto "Any" (una petición no suele exigir un source concreto).
  const [type, setType] = useState('Any')
  const [resolution, setResolution] = useState(item.resolution && RESOLUTIONS.includes(item.resolution) ? item.resolution : 'Any')

  const [useTmdb, setUseTmdb] = useState(!!item.tmdb_id)
  const [tmdbId, setTmdbId] = useState(onlyDigits(item.tmdb_id || ''))
  const [useImdb, setUseImdb] = useState(!!item.imdb_id)
  const [imdbId, setImdbId] = useState(onlyDigits(item.imdb_id || ''))  // digits only (no tt)
  const [useMal, setUseMal] = useState(!!item.mal_id)
  const [malId, setMalId] = useState(onlyDigits(item.mal_id || ''))

  const [useTvdb, setUseTvdb] = useState(!!item.tvdb_id)
  const [tvdbId, setTvdbId] = useState(onlyDigits(item.tvdb_id || ''))
  const [season, setSeason] = useState(item.season_number != null ? String(item.season_number) : '')
  const [episode, setEpisode] = useState(item.episode_number != null ? String(item.episode_number) : '')
  // A series/doc request can target every season, one season, or a single
  // episode. Prefill the scope from the item's granularity.
  const [scope, setScope] = useState<'all' | 'season' | 'episode'>(
    item.episode_number != null ? 'episode' : item.season_number != null ? 'season' : 'all'
  )

  const [description, setDescription] = useState('')
  const [reward, setReward] = useState(String(MIN_REWARD))
  const [anon, setAnon] = useState(false)

  const [msg, setMsg] = useState<string | null>(null)

  // Documentaries share the Series field set (season/episode, tvdb), so they
  // inherit the exact same behaviour here.
  const isSeries = category === 'tv' || category === 'doc'
  const rewardNum = parseInt(reward || '0', 10)
  const rewardTooLow = rewardNum < MIN_REWARD
  const canSubmit = title.trim().length > 0 && !rewardTooLow
  const submitTip = useTooltip(canSubmit ? null : 'Completa el título y una recompensa válida')

  const handleSubmit = () => {
    // No real endpoint yet — validate and preview the payload only.
    const payload = {
      category, title: title.trim(), type, resolution,
      tmdb_id: useTmdb ? tmdbId : null,
      imdb_id: useImdb ? imdbId : null,
      mal_id: useMal ? malId : null,
      ...(isSeries ? {
        tvdb_id: useTvdb ? tvdbId : null,
        scope,
        season: scope === 'all' ? '0' : (onlyDigits(season) || '0'),
        episode: scope === 'episode' ? (onlyDigits(episode) || '0') : '0',
      } : {}),
      description, reward: rewardNum, anonymous: anon,
    }
    setMsg('La creación de peticiones está pendiente del endpoint real de eMuwarez (aún por capturar). Payload validado: ' + JSON.stringify(payload))
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <div className="modal-header">
          <h2 className="modal-title">Nueva petición en eMuwarez</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px' }}>
            <label style={{ gridColumn: '1 / -1' }}><span style={labelStyle}>Título</span>
              <input className="form-input" value={title} onChange={e => setTitle(e.target.value)} placeholder="Título (AÑO) — p. ej. Origen (2010)" />
            </label>

            <label><span style={labelStyle}>Categoría</span>
              <select className="form-input" value={category} onChange={e => setCategory(e.target.value)}>
                {CATEGORIES.map(c => (
                  <option key={c.value} value={c.value} disabled={!c.enabled}>
                    {c.label}{c.enabled ? '' : ' (próximamente)'}
                  </option>
                ))}
              </select>
            </label>

            <label><span style={labelStyle}>Tipo</span>
              <select className="form-input" value={type} onChange={e => setType(e.target.value)}>
                {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>

            <label><span style={labelStyle}>Resolución</span>
              <select className="form-input" value={resolution} onChange={e => setResolution(e.target.value)}>
                {RESOLUTIONS.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </label>

            {isSeries && (
              <>
                <label style={{ gridColumn: '1 / -1' }}><span style={labelStyle}>Alcance de la petición</span>
                  <select className="form-input" value={scope} onChange={e => setScope(e.target.value as 'all' | 'season' | 'episode')}>
                    <option value="all">Todas las temporadas</option>
                    <option value="season">Una temporada</option>
                    <option value="episode">Un episodio</option>
                  </select>
                </label>
                {scope !== 'all' && (
                  <label><span style={labelStyle}>Nº de temporada</span>
                    <input className="form-input" value={season} onChange={e => setSeason(onlyDigits(e.target.value))} inputMode="numeric" placeholder="1" />
                  </label>
                )}
                {scope === 'episode' && (
                  <label><span style={labelStyle}>Nº de episodio</span>
                    <input className="form-input" value={episode} onChange={e => setEpisode(onlyDigits(e.target.value))} inputMode="numeric" placeholder="1" />
                  </label>
                )}
              </>
            )}
          </div>

          {/* ID checkboxes */}
          <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 16px' }}>
            <IdRow label="TMDB ID" checked={useTmdb} onToggle={setUseTmdb} value={tmdbId} onChange={v => setTmdbId(onlyDigits(v))} href={idVerifyUrl('tmdb', tmdbId, isSeries)} />
            <IdRow label="IMDB ID" checked={useImdb} onToggle={setUseImdb} value={imdbId} onChange={v => setImdbId(onlyDigits(v))} href={idVerifyUrl('imdb', imdbId, isSeries)} />
            <IdRow label="MAL ID (anime)" checked={useMal} onToggle={setUseMal} value={malId} onChange={v => setMalId(onlyDigits(v))} href={idVerifyUrl('mal', malId, isSeries)} />
            {isSeries && (
              <IdRow label="TVDB ID" checked={useTvdb} onToggle={setUseTvdb} value={tvdbId} onChange={v => setTvdbId(onlyDigits(v))} href={idVerifyUrl('tvdb', tvdbId, isSeries)} />
            )}
          </div>

          <label style={{ display: 'block', marginTop: 16 }}><span style={labelStyle}>Descripción personal</span>
            <textarea className="form-input" value={description} onChange={e => setDescription(e.target.value)} rows={3} style={{ resize: 'vertical' }} placeholder="No olvides dar las gracias!" />
          </label>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px', marginTop: 12, alignItems: 'center' }}>
            <label><span style={labelStyle}>Recompensa (puntos)</span>
              <input className="form-input" value={reward} onChange={e => setReward(onlyDigits(e.target.value))} inputMode="numeric" />
              {rewardTooLow && <span style={{ fontSize: 11, color: '#ef4444' }}>Mínimo {MIN_REWARD} puntos</span>}
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 18 }}>
              <input type="checkbox" checked={anon} onChange={e => setAnon(e.target.checked)} /> Anónimo
            </label>
          </div>

          <div style={{ marginTop: 8, fontSize: 11 }} className="text-muted">
            Nota: validar la recompensa contra tu saldo de puntos requiere el endpoint de usuario de eMuwarez (pendiente).
          </div>

          {msg && <p style={{ fontSize: 12, marginTop: 10, wordBreak: 'break-all' }} className="text-warning">{msg}</p>}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
            <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
            <button className="btn btn-primary" onClick={handleSubmit} disabled={!canSubmit} {...submitTip.triggerProps}>
              Enviar petición
              {submitTip.tooltipNode}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function IdRow({ label, checked, onToggle, value, onChange, href }: {
  label: string; checked: boolean; onToggle: (v: boolean) => void; value: string; onChange: (v: string) => void
  href?: string | null
}) {
  const canVerify = checked && !!href
  const verifyTip = useTooltip(canVerify ? 'Verificar: abrir la ficha en su web' : 'Introduce un ID para verificarlo')
  return (
    <div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, marginBottom: 4 }}>
        <input type="checkbox" checked={checked} onChange={e => onToggle(e.target.checked)} /> {label}
      </label>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <input
          className="form-input"
          value={value}
          onChange={e => onChange(e.target.value)}
          disabled={!checked}
          inputMode="numeric"
          placeholder="solo dígitos"
          style={{ opacity: checked ? 1 : 0.5, flex: 1, minWidth: 0 }}
        />
        <a
          className="btn btn-secondary btn-sm"
          href={canVerify ? href! : undefined}
          target="_blank"
          rel="noreferrer"
          aria-disabled={!canVerify}
          onClick={e => { if (!canVerify) e.preventDefault() }}
          style={{
            flexShrink: 0, textDecoration: 'none', lineHeight: 1,
            padding: '0 10px', height: 34, display: 'flex', alignItems: 'center',
            opacity: canVerify ? 1 : 0.4, pointerEvents: canVerify ? 'auto' : 'none',
          }}
          {...verifyTip.triggerProps}
        >
          ↗
          {verifyTip.tooltipNode}
        </a>
      </div>
    </div>
  )
}
