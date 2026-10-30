import type { LibraryItemResponse } from '../types/api'
import { useTooltip } from './Tooltip'
import { episodeListLabel } from '../utils/libraryItem'
import { Favicon, domainOf } from './Favicon'
import { Modal } from './Modal'
import { urlCrearPeticion } from '../utils/peticionEmu'

// Vista previa de la petición en eMuwarez, sacada del elemento de la
// biblioteca. La API de UNIT3D no permite crear peticiones, así que el botón
// abre el formulario de eMuwarez (/requests/create) ya rellenado en otra
// pestaña y la petición se envía desde allí, con la sesión del navegador.
// Tipo, resolución, temporada, episodio, descripción y recompensa se completan
// en ese formulario: /requests/create no los acepta por la URL.
const CATEGORY_LABELS: Record<string, string> = { movie: 'Películas', tv: 'Series', doc: 'Documentales' }
const SCOPE_LABELS: Record<'all' | 'season' | 'episode', string> = {
  all: 'Todas las temporadas', season: 'Una temporada', episode: 'Un episodio',
}

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
  // from — a petición always targets that exact title/season/episode.
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

  // Documentaries share the Series field set (season/episode, tvdb), so they
  // inherit the exact same behaviour here.
  const isSeries = category === 'tv' || category === 'doc'

  const createUrl = urlCrearPeticion({ category, title, imdb: imdbId, tmdb: tmdbId, tvdb: tvdbId, mal: malId })

  return (
    <Modal titulo="Nueva petición en eMuwarez" onClose={onClose} className="modal-wide" style={{ maxWidth: 640 }}>
      <div className="modal-body">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px' }}>
          <ReadOnlyField label="Título" value={title} gridColumn="1 / -1" />
          <ReadOnlyField label="Categoría" value={CATEGORY_LABELS[category] ?? category} gridColumn={isSeries ? undefined : '1 / -1'} />
          {isSeries && <ReadOnlyField label="Alcance de la petición" value={SCOPE_LABELS[scope]} />}

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

        <p style={{ fontSize: 12, marginTop: 16 }} className="text-muted">
          Se abre el formulario de eMuwarez rellenado con estos datos. Allí completas tipo, resolución{scope !== 'all' && ', temporada, episodio'}, descripción y recompensa, y envías la petición.
        </p>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
          <a className="btn btn-primary" href={createUrl} target="_blank" rel="noreferrer" onClick={onClose} style={{ textDecoration: 'none' }}>
            Abrir en eMuwarez
          </a>
        </div>
      </div>
    </Modal>
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
