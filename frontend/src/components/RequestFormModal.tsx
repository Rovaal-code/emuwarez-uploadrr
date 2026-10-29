import { useState } from 'react'
import type { LibraryItemResponse } from '../types/api'
import { useTooltip } from './Tooltip'
import { episodeListLabel } from '../utils/libraryItem'
import { Favicon, domainOf } from './Favicon'

// eMuwarez "Petición" (request) creation form. Built from the field spec the
// user captured from eMuwarez's web form. Submission is intentionally gated:
// the real create/edit endpoints haven't been captured yet, so "Enviar"
// validates and previews the payload but does not POST. The form is prefilled
// from the library item so peticiones start from content you already track.
// category/scope aren't user choices — both are fixed by the library item
// the request was opened from, just shown here for context.
const CATEGORY_LABELS: Record<string, string> = { movie: 'Películas', tv: 'Series', doc: 'Documentales' }
const SCOPE_LABELS: Record<'all' | 'season' | 'episode', string> = {
  all: 'Todas las temporadas', season: 'Una temporada', episode: 'Un episodio',
}
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
  fontSize: 12, color: 'var(--text-muted)', marginBottom: 4, display: 'block',
}

export function RequestFormModal({ item, onClose }: Props) {
  const isSeriesLike = item.item_type === 'series' || item.item_type === 'season' || item.item_type === 'episode'

  // Everything below is fixed by the library item the request was opened
  // from — a petición always targets that exact title/season/episode, so
  // none of it is a user choice (only Tipo/Resolución/Descripción/
  // Recompensa/Anónimo are editable, further down).
  const category: string = isSeriesLike ? 'tv' : 'movie'
  // eMuwarez expects the year right after the series/movie name:
  // "Título (AÑO)" for a movie/series, "Serie (AÑO) - Temporada X" or
  // "Serie (AÑO) - SxxExx" for a season/episode — not tacked onto the very
  // end, since `item.title` for those already carries a suffix that has to
  // stay last. An episode's own `item.title` also carries Sonarr's
  // descriptive subtitle after the SxxExx code ("Serie SxxExx - Episode
  // Name…") — episodeListLabel() strips that down to "Serie - SxxExx" first,
  // same as the Biblioteca list already shows, so only the code survives.
  const title = (() => {
    const base = item.item_type === 'episode' ? episodeListLabel(item) : (item.title || '')
    if (!item.year || item.year <= 0 || /\(\d{4}\)/.test(base)) return base
    const sepIdx = (item.item_type === 'season' || item.item_type === 'episode') ? base.lastIndexOf(' - ') : -1
    return sepIdx === -1
      ? `${base} (${item.year})`
      : `${base.slice(0, sepIdx)} (${item.year})${base.slice(sepIdx)}`
  })()
  const tmdbId = onlyDigits(item.tmdb_id || '')
  const imdbId = onlyDigits(item.imdb_id || '')  // digits only (no tt)
  const malId = onlyDigits(item.mal_id || '')
  const tvdbId = onlyDigits(item.tvdb_id || '')
  const season = item.season_number != null ? String(item.season_number) : ''
  const episode = item.episode_number != null ? String(item.episode_number) : ''
  // A request targets every season, one season, or a single episode,
  // depending on the granularity of the item it was opened from.
  const scope: 'all' | 'season' | 'episode' =
    item.episode_number != null ? 'episode' : item.season_number != null ? 'season' : 'all'

  // Tipo por defecto "Any" (una petición no suele exigir un source concreto).
  const [type, setType] = useState('Any')
  const [resolution, setResolution] = useState(item.resolution && RESOLUTIONS.includes(item.resolution) ? item.resolution : 'Any')
  const [description, setDescription] = useState('')
  const [reward, setReward] = useState(String(MIN_REWARD))
  const [anon, setAnon] = useState(false)

  const [msg, setMsg] = useState<string | null>(null)

  // Documentaries share the Series field set (season/episode, tvdb), so they
  // inherit the exact same behaviour here.
  const isSeries = category === 'tv' || category === 'doc'
  const rewardNum = parseInt(reward || '0', 10)
  const rewardTooLow = rewardNum < MIN_REWARD
  const canSubmit = !rewardTooLow
  const submitTip = useTooltip(canSubmit ? null : 'Introduce una recompensa válida')

  const handleSubmit = () => {
    // No real endpoint yet — eMuwarez's create-request endpoint hasn't been
    // captured, so there's nothing to actually POST to.
    setMsg('No implementado')
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
            <ReadOnlyField label="Título" value={title} gridColumn="1 / -1" />
            <ReadOnlyField label="Categoría" value={CATEGORY_LABELS[category] ?? category} gridColumn={isSeries ? undefined : '1 / -1'} />
            {isSeries && <ReadOnlyField label="Alcance de la petición" value={SCOPE_LABELS[scope]} />}

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
                {scope !== 'all' && <ReadOnlyField label="Nº de temporada" value={season} />}
                {scope === 'episode' && <ReadOnlyField label="Nº de episodio" value={episode} />}
              </>
            )}
          </div>

          {/* External IDs — read-only: whatever the library item already has. */}
          <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 16px' }}>
            <IdRow label="TMDB ID" value={tmdbId} href={idVerifyUrl('tmdb', tmdbId, isSeries)} />
            <IdRow label="IMDB ID" value={imdbId} href={idVerifyUrl('imdb', imdbId, isSeries)} />
            <IdRow label="MAL ID (anime)" value={malId} href={idVerifyUrl('mal', malId, isSeries)} />
            {isSeries && (
              <IdRow label="TVDB ID" value={tvdbId} href={idVerifyUrl('tvdb', tvdbId, isSeries)} />
            )}
          </div>

          <label style={{ display: 'block', marginTop: 16 }}><span style={labelStyle}>Descripción personal</span>
            <textarea className="form-input" value={description} onChange={e => setDescription(e.target.value)} rows={3} style={{ resize: 'vertical' }} placeholder="No olvides dar las gracias!" />
          </label>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px', marginTop: 12, alignItems: 'center' }}>
            <label><span style={labelStyle}>Recompensa (puntos)</span>
              <input className="form-input" value={reward} onChange={e => setReward(onlyDigits(e.target.value))} inputMode="numeric" />
              {rewardTooLow && <span style={{ fontSize: 11, color: 'var(--color-error)' }}>Mínimo {MIN_REWARD} puntos</span>}
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 18 }}>
              <input type="checkbox" checked={anon} onChange={e => setAnon(e.target.checked)} /> Anónimo
            </label>
          </div>

          {msg && <p style={{ fontSize: 12, marginTop: 10, fontWeight: 600 }} className="text-error">{msg}</p>}

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

// Read-only stand-in for a plain <label><input> pair — used for every field
// that's fixed by the library item (Título/Categoría/Alcance/Temporada/
// Episodio) instead of a real form control the user could edit.
function ReadOnlyField({ label, value, gridColumn }: { label: string; value: string; gridColumn?: string }) {
  return (
    <label style={gridColumn ? { gridColumn } : undefined}>
      <span style={labelStyle}>{label}</span>
      <input className="form-input" value={value || '—'} disabled readOnly style={{ opacity: 0.7 }} />
    </label>
  )
}

function IdRow({ label, value, href }: { label: string; value: string; href?: string | null }) {
  const canVerify = !!href
  const verifyTip = useTooltip(canVerify ? 'Verificar: abrir la ficha en su web' : 'Este campo no tiene un valor disponible')
  return (
    <div>
      <span style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>{label}</span>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <input
          className="form-input"
          value={value || '—'}
          disabled
          readOnly
          style={{ flex: 1, minWidth: 0, opacity: 0.7 }}
        />
        <a
          className="btn btn-secondary btn-sm hover-link"
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
          <Favicon domain={domainOf(href)} size={16} radius={3} fallback={<span style={{ fontSize: 12 }}>↗</span>} />
          {verifyTip.tooltipNode}
        </a>
      </div>
    </div>
  )
}
