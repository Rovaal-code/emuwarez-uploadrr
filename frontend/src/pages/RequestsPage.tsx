import { useState, useEffect, useCallback } from 'react'
import {
  getRequests,
  getRequestDetail,
} from '../api/requests'
import { getCandidates } from '../api/requestReadiness'
import type {
  RequestItemResponse, RequestDetailResponse,
  RequestReadinessResponse, RequestCandidateResponse,
} from '../types/api'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { SyncInfo } from '../components/SyncInfo'
import { StatusBadge } from '../components/StatusBadge'
import { HoverTitle } from '../components/Tooltip'
import { useSync } from '../context/SyncContext'
import { UploadWizardModal } from '../components/UploadWizardModal'
import { getLibraryItem } from '../api/library'
import type { LibraryItemResponse } from '../types/api'
import { posterUrl, idVerifyUrl } from '../utils/libraryItem'
import { ExternalIdLink } from '../components/ExternalIdLink'
import { InfoIcon } from '../components/InfoIcon'
import {
  Card, FieldRow, DetailPoster, ValueChip, ValueIcon, DETAIL_CARD_HEIGHT,
  StatusCardIcon, RequestCardIcon, ExternalIdsCardIcon,
  UploadButtonIcon, ExternalLinkButtonIcon,
  TypeValueIcon, AuthorValueIcon, CalendarValueIcon,
  SeasonValueIcon, EpisodeValueIcon, ResolutionValueIcon, SourceValueIcon,
  PointsValueIcon, ThumbsUpValueIcon, CommentValueIcon,
} from '../components/DetailCard'
import { HeaderFilter } from '../components/HeaderFilter'
import { formatBytes, timeAgo, formatDate } from '../utils/format'
import { getDetailIdFromPath, pushDetailPath, closeDetailPath } from '../utils/detailUrl'

// Fallback for "Consultar en eMuwarez" while we don't have the exact
// per-request URL yet — points at the general requests listing instead of
// leaving the button disabled.
const EMU_REQUESTS_FALLBACK_URL = 'https://emuwarez.com/requests'

// A request's category maps to a friendly "Tipo" with an icon.
function tipoOf(category: string | null): { icon: string; label: string } {
  const c = (category || '').toLowerCase()
  if (c.includes('serie')) return { icon: '📺', label: category || 'Serie' }
  if (c.includes('docu')) return { icon: '🎥', label: category || 'Documental' }
  if (c.includes('pel') || c.includes('movie') || c.includes('film')) return { icon: '🎬', label: category || 'Película' }
  return { icon: '🎬', label: category || '—' }
}

function RequestPoster({ url, category, size = 'sm' }: { url: string | null; category: string | null; size?: 'sm' | 'lg' }) {
  const dims = size === 'lg'
    ? { width: 120, height: 180, radius: 8, font: 44 }
    : { width: 30, height: 45, radius: 4, font: 15 }
  const t = tipoOf(category)
  return (
    <div className="poster-thumb" style={{ flexShrink: 0, width: dims.width, height: dims.height, borderRadius: dims.radius, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      {url ? (
        <img
          src={posterUrl(url, size === 'lg' ? 'w342' : 'w154')}
          alt=""
          loading="lazy"
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
        />
      ) : (
        <span style={{ fontSize: dims.font, opacity: 0.35 }}>{t.icon}</span>
      )}
    </div>
  )
}

const SORT_OPTIONS = [
  { value: 'created_desc', label: 'Orden: Más recientes' },
  { value: 'created_asc', label: 'Orden: Más antiguas' },
  { value: 'title', label: 'Orden: Título (A-Z)' },
  { value: 'points_desc', label: 'Orden: Más puntos' },
  { value: 'points_asc', label: 'Orden: Menos puntos' },
  { value: 'votes_desc', label: 'Orden: Más me gusta' },
  { value: 'comments_desc', label: 'Orden: Más comentarios' },
]

const fmtNum = (n: number | null | undefined) => (n == null ? '—' : n.toLocaleString('es-ES'))

// Inline SVG icons for the votes/comments/points columns — emoji (👍💬🪙)
// render as bare white outlines on some systems, so use real vector icons.
function Svg({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <svg viewBox="0 0 24 24" width={15} height={15} fill={color} style={{ verticalAlign: 'middle' }} aria-hidden="true">
      {children}
    </svg>
  )
}
const VotesIcon = () => (
  <Svg color="#60a5fa"><path d="M2 21h4V9H2v12zM23 10c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.59 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2z"/></Svg>
)
const CommentsIcon = () => (
  <Svg color="#9ca3af"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></Svg>
)
const PointsIcon = () => (
  <Svg color="#eab308"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1.41 15.09V18h-2v-.91c-1.28-.26-2.34-1.06-2.41-2.35h1.47c.07.67.55 1.19 1.94 1.19 1.49 0 1.82-.75 1.82-1.21 0-.63-.33-1.22-2.01-1.62-1.87-.45-3.15-1.22-3.15-2.76 0-1.29 1.05-2.13 2.34-2.41V7h2v.92c1.39.34 2.09 1.4 2.13 2.55h-1.47c-.04-.71-.42-1.19-1.65-1.19-1.17 0-1.87.53-1.87 1.28 0 .66.51 1.09 2.01 1.48s3.15 1.04 3.15 2.9c-.01 1.37-1.04 2.12-2.34 2.35z"/></Svg>
)

// Author cell — your own requests (author === emu.username) show in green + "(Yo)".
function AuthorCell({ author, isMine }: { author: string | null; isMine: boolean }) {
  if (!author) return <span style={{ color: 'var(--text-muted)' }}>—</span>
  if (isMine) return <span style={{ color: '#22c55e', fontWeight: 600 }}>{author} (Yo)</span>
  return <span>{author}</span>
}

// Comparison-table helpers.
const isAny = (v: string | null | undefined) =>
  !v || ['any', 'cualquiera', 'todos', 'all'].includes(v.trim().toLowerCase())

function noReq(v: string | null): string {
  return isAny(v) ? 'Cualquiera' : (v as string)
}

// Whether your library value satisfies the request. If the request has no
// restriction ("Cualquiera") it's satisfied as long as you have the content
// (any resolution/source you own counts) → green ✓.
function satisfies(requested: string | null, local: string | null, specMatch: boolean | null): boolean | null {
  if (isAny(requested)) return local ? true : null
  return specMatch
}

// Small ✓/✗ shown inside a comparison cell.
function cellMark(v: boolean | null) {
  if (v === true) return <span style={{ color: '#22c55e', fontWeight: 700 }}> ✓</span>
  if (v === false) return <span style={{ color: '#ef4444', fontWeight: 700 }}> ✗</span>
  return null
}

const baseName = (path: string | null) => (path ? path.split('/').pop() || null : null)

function CompatibilityBadge({ status }: { status: string | null }) {
  if (!status) return <span style={{ color: 'var(--text-muted)' }}>—</span>
  return <StatusBadge status={status} type="request" />
}

function ReadinessBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>
  const color =
    status === 'ready_to_upload' ? '#34d399' :
    status === 'needs_nomenclature' ? '#f59e0b' :
    status === 'preflight_needed' ? '#60a5fa' :
    status === 'downloading' ? '#818cf8' :
    status === 'uploaded' ? '#6ee7b7' :
    status === 'no_local_match' ? 'var(--text-muted)' :
    status.includes('error') || status.includes('missing') || status === 'blocked' ? 'var(--color-missing)' :
    'var(--text-secondary)'
  return <span style={{ fontSize: 11, color, fontWeight: 500 }}>{status}</span>
}

function CandidatesPanel({ requestId, onClose }: { requestId: number; onClose: () => void }) {
  const [candidates, setCandidates] = useState<RequestCandidateResponse[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCandidates(requestId)
      .then(setCandidates)
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false))
  }, [requestId])

  return (
    <div className="detail-panel">
      <div className="detail-panel__header">
        <div className="detail-panel__title">Candidatos locales</div>
        <button className="btn-icon" onClick={onClose}>✕</button>
      </div>
      {loading ? <LoadingState label="Cargando candidatos…" /> : candidates.length === 0 ? (
        <div className="empty-inline">Sin candidatos en biblioteca. Ejecuta "Recalcular readiness".</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 0' }}>
          {candidates.map(c => (
            <div key={c.id} className="detail-card" style={{ padding: '10px 14px', borderRadius: 6, fontSize: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>#{c.candidate_rank} — {c.lib_title || `Lib #${c.library_item_id}`}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 12px', color: 'var(--text-secondary)' }}>
                <span>Compat: <strong>{c.compatibility_score?.toFixed(0) ?? '—'}</strong></span>
                <span>Readiness: <strong>{c.readiness_score?.toFixed(0) ?? '—'}</strong></span>
                <span>Estado: {c.local_status || '—'}</span>
                <span>Resolución: {c.resolution || '—'}</span>
              </div>
              {c.blockers.length > 0 && (
                <div style={{ marginTop: 4, color: 'var(--color-missing)', fontSize: 11 }}>
                  ⛔ {c.blockers.join(' · ')}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// External-ID field with a mini button to open its public page. Renders nothing
// when the ID isn't available (e.g. MAL isn't provided by Radarr/Sonarr).
function IdField({ label, id, href }: { label: string; id: string | null; href: string | null }) {
  if (!id) return null
  return (
    <FieldRow label={label}>
      <ValueChip linkable={Boolean(href)}><ExternalIdLink id={id} href={href} label={label} /></ValueChip>
    </FieldRow>
  )
}

// Full dedicated request page — same visual format as the library item detail
// page (back button, big poster left, title + fields grid right).
function RequestDetailPage({ item, readiness, onBack, onShowCandidates, onUpload, onOpenLibraryItem }: {
  item: RequestDetailResponse
  readiness: RequestReadinessResponse | null
  onBack: () => void
  onShowCandidates: () => void
  onUpload: (libraryItemId: number, preselect?: { season?: number | null; episode?: number | null }) => void
  onOpenLibraryItem?: (id: number) => void
}) {
  const m = item.match
  const effectiveStatus = m ? m.status : (item.compatibility_status ?? null)
  const libId = m?.library_item_id ?? item.library_item_id
  const t = tipoOf(item.category)
  // External IDs: prefer the request's own, fall back to the matched library
  // item (Radarr/Sonarr). TVDB only comes from the library item; MAL isn't
  // provided by Radarr/Sonarr yet.
  const isTv = /serie/i.test(item.category || '')
  const isSeriesLike = /serie|docu/i.test(item.category || '')
  const tmdbId = item.tmdb_id || m?.local_tmdb_id || null
  const imdbId = item.imdb_id || m?.local_imdb_id || null
  const tvdbId = item.tvdb_id || m?.local_tvdb_id || null
  const malId = item.mal_id || null
  const hasSeason = item.req_scope === 'season' || item.req_scope === 'episode'
  const temporadaLabel = hasSeason ? String(item.req_season ?? '?') : 'Todas'
  return (
    <div style={{ width: '100%', flex: 1, minHeight: 0, overflowY: 'auto' }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← Volver a peticiones</button>
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 20 }}>
        <div style={{ fontWeight: 700, fontSize: 25, letterSpacing: '-0.01em' }}>{item.title}</div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0, flexWrap: 'wrap' }}>
          <a
            className="btn btn-primary btn-sm"
            href={item.url || EMU_REQUESTS_FALLBACK_URL}
            target="_blank"
            rel="noreferrer"
            title={item.url
              ? 'Abrir la petición en eMuwarez (reclamarla, marcarla como llena, ver el ID del torrent…)'
              : 'Todavía no tenemos la URL exacta de esta petición — abre el listado general de peticiones en eMuwarez'}
            style={{ textDecoration: 'none' }}
          >
            <ExternalLinkButtonIcon /> Consultar en eMuwarez
          </a>
          <button
            className="btn btn-primary btn-sm"
            disabled={!libId}
            title={libId
              ? 'Subir el contenido de tu biblioteca a eMuwarez (mismo asistente que en Biblioteca)'
              : 'No tienes este contenido en tu biblioteca'}
            onClick={() => libId && onUpload(libId, {
              season: item.req_season,
              episode: item.req_scope === 'episode' ? item.req_episode : null,
            })}
          >
            <UploadButtonIcon /> Subir a eMuwarez
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <DetailPoster url={item.poster_url ? posterUrl(item.poster_url, 'w500') : null} alt={item.title} fallbackEmoji={t.icon} />

        <div style={{ flex: 1, minWidth: 300 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, minHeight: DETAIL_CARD_HEIGHT }}>
            <Card title="Estado de la petición" icon={<StatusCardIcon />}>
              <FieldRow label="Estado" help="Aunque salga «Compatible», revisa la petición: el audio y el códec no se pueden comparar del todo (suelen indicarse en la descripción del torrent), y si pide la serie completa puede que no quiera la temporada especial."><CompatibilityBadge status={effectiveStatus} /></FieldRow>
              <FieldRow label="Tipo">
                <ValueChip><ValueIcon><TypeValueIcon /></ValueIcon><span className="txt">{t.label}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Autor">
                <ValueChip><ValueIcon><AuthorValueIcon /></ValueIcon><span className="txt"><AuthorCell author={item.author} isMine={item.is_mine} /></span></ValueChip>
              </FieldRow>
              {item.created_at && (
                <FieldRow label="Creada">
                  <ValueChip><ValueIcon><CalendarValueIcon /></ValueIcon><span className="txt">{new Date(item.created_at).toLocaleDateString('es-ES')}</span></ValueChip>
                </FieldRow>
              )}
            </Card>

            <Card title="Detalle pedido" icon={<RequestCardIcon />}>
              {isSeriesLike && (
                <FieldRow label="Temporada">
                  <ValueChip><ValueIcon><SeasonValueIcon /></ValueIcon><span className="txt">{temporadaLabel}</span></ValueChip>
                </FieldRow>
              )}
              {isSeriesLike && (
                <FieldRow label="Capítulo">
                  <ValueChip><ValueIcon><EpisodeValueIcon /></ValueIcon><span className="txt">{item.req_scope === 'episode' ? (item.req_episode ?? '?') : 'Todos'}</span></ValueChip>
                </FieldRow>
              )}
              <FieldRow label="Resolución pedida">
                <ValueChip><ValueIcon><ResolutionValueIcon /></ValueIcon><span className="txt">{noReq(item.requested_resolution)}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Source pedido">
                <ValueChip><ValueIcon><SourceValueIcon /></ValueIcon><span className="txt">{noReq(item.requested_source)}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Puntos">
                <ValueChip><ValueIcon><PointsValueIcon /></ValueIcon><span className="txt">{fmtNum(item.points)}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Votos">
                <ValueChip><ValueIcon><ThumbsUpValueIcon /></ValueIcon><span className="txt">{item.votes ?? 0}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Comentarios">
                <ValueChip><ValueIcon><CommentValueIcon /></ValueIcon><span className="txt">{item.comments ?? 0}</span></ValueChip>
              </FieldRow>
            </Card>

            <Card title="Identificadores externos" icon={<ExternalIdsCardIcon />}>
              <IdField label="TMDb" id={tmdbId} href={idVerifyUrl('tmdb', tmdbId, isTv)} />
              <IdField label="IMDb" id={imdbId} href={idVerifyUrl('imdb', imdbId, isTv)} />
              <IdField label="TVDB" id={tvdbId} href={idVerifyUrl('tvdb', tvdbId, isTv)} />
              {/* MAL always shown (mainly for anime); "–" when the request had none. */}
              <FieldRow label="MAL">
                {malId
                  ? <ValueChip linkable={Boolean(idVerifyUrl('mal', malId, isTv))}><ExternalIdLink id={malId} href={idVerifyUrl('mal', malId, isTv)} label="MAL" /></ValueChip>
                  : <span className="muted">–</span>}
              </FieldRow>
            </Card>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 17 }}>
        <div style={{ fontSize: 11.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', marginBottom: 15 }}>
          Petición vs. tu biblioteca
        </div>
        <div className="detail-card" style={{ borderRadius: 10, padding: '21px 19px' }}>
          {!m ? (
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Sin coincidencia en tu biblioteca local, no tienes este contenido.</span>
          ) : effectiveStatus === 'No disponible' ? (
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Tienes una entrada para este contenido en tu biblioteca, pero el archivo no está disponible (falta, en cola o con error), así que no hay nada que comparar. Vuelve a descargarlo para poder cotejarlo con la petición.</span>
          ) : (
            <>
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table" style={{ fontSize: 12.5 }}>
                  <thead>
                    <tr>
                      <th>Contenido</th><th>Resolución</th><th>Source</th>
                      <th><span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>Códec <InfoIcon text="El códec no se puede comparar de forma fiable: en eMuwarez suele indicarse en la descripción del torrent, no en los campos." /></span></th>
                      <th><span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>Idiomas <InfoIcon text="El audio/idiomas no se pueden comparar de forma fiable: suelen indicarse en la descripción del torrent." /></span></th>
                      <th>Tamaño</th><th>Nombre</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>Petición</td>
                      <td>{noReq(item.requested_resolution)}</td>
                      <td>{noReq(item.requested_source)}</td>
                      <td style={{ color: 'var(--text-muted)' }}>—</td>
                      <td style={{ color: 'var(--text-muted)' }}>—</td>
                      <td style={{ color: 'var(--text-muted)' }}>—</td>
                      <td style={{ maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }} title={m.content_name || ''}>{m.content_name || '—'}</td>
                    </tr>
                    <tr style={{ background: 'rgba(34,197,94,0.06)' }}>
                      <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>Tu biblioteca</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{m.local_resolution || '—'}{cellMark(satisfies(item.requested_resolution, m.local_resolution, m.resolution_match))}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{m.local_source || '—'}{cellMark(satisfies(item.requested_source, m.local_source, m.source_match))}</td>
                      <td>{m.local_video_codec || '—'}</td>
                      <td>{m.local_audio_languages || '—'}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{m.local_size ? formatBytes(m.local_size) : '—'}</td>
                      <td style={{ maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={m.content_name || baseName(m.local_path) || m.library_title || ''}>
                        {libId
                          ? <span className="lib-title-link" onClick={() => onOpenLibraryItem?.(libId)} title="Ver ficha del contenido">{m.content_name || baseName(m.local_path) || m.library_title || '—'}</span>
                          : <span style={{ color: 'var(--text-secondary)' }}>{m.content_name || baseName(m.local_path) || m.library_title || '—'}</span>}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>

      {readiness && (
        <details className="cmp-readiness" style={{ marginTop: 20, maxWidth: 640 }}>
          <summary>Preparación de subida (avanzado)</summary>
          <div style={{ marginTop: 8 }}>
            <div className="detail-row"><span>Estado</span><ReadinessBadge status={readiness.status} /></div>
            <div className="detail-row"><span>Acción</span><span style={{ fontSize: 12, color: '#a78bfa' }}>{readiness.recommended_action || '—'}</span></div>
            <div className="detail-row"><span>Compat. score</span><span>{readiness.compatibility_score?.toFixed(0) ?? '—'}/100</span></div>
            <div className="detail-row"><span>Readiness score</span><span>{readiness.upload_readiness_score?.toFixed(0) ?? '—'}/100</span></div>
            {readiness.blockers.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>BLOQUEADORES</div>
                {readiness.blockers.map((b, i) => (
                  <div key={i} style={{ fontSize: 11, color: 'var(--color-missing)' }}>⛔ {b}</div>
                ))}
              </div>
            )}
            <div style={{ marginTop: 8 }}>
              <button className="btn btn-ghost btn-sm" onClick={onShowCandidates}>Ver candidatos</button>
            </div>
          </div>
        </details>
      )}
    </div>
  )
}

const PAGE_SIZE = 2000  // show everything in one scrollable container (like Biblioteca)

export function RequestsPage({ onNavigate }: { onNavigate?: (page: string) => void } = {}) {
  // Open a library item's dedicated detail page from a request (its "Tu
  // biblioteca" name): stash the id and switch to the Biblioteca tab.
  const goToLibraryItem = (id: number) => {
    try { sessionStorage.setItem('emuwarez_open_library_item', String(id)) } catch { /* ignore */ }
    onNavigate?.('library')
  }
  const [items, setItems] = useState<RequestItemResponse[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  // The input stays bound to `search` for instant typing feedback; loadItems
  // only reacts to `debouncedSearch`, same convention as Biblioteca's search
  // box (LibraryPage.tsx) — searching here used to require pressing Enter.
  const [debouncedSearch, setDebouncedSearch] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350)
    return () => clearTimeout(t)
  }, [search])
  const [statusFilter, setStatusFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [resolutionFilter, setResolutionFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [authorFilter, setAuthorFilter] = useState('')
  const [sortBy, setSortBy] = useState('created_desc')
  const [facets, setFacets] = useState<{ categories: string[]; resolutions: string[]; sources: string[]; authors: string[]; statuses: string[] }>({
    categories: [], resolutions: [], sources: [], authors: [], statuses: [],
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Requests sync is global (shared with the Dashboard's "Peticiones" button
  // and the progress banner), so it can't be launched twice across tabs.
  const { requestsSyncing, requestsStatus, startRequestsSync, lastCompletedAt, isAnySyncing } = useSync()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<RequestDetailResponse | null>(null)
  const [readiness, setReadiness] = useState<RequestReadinessResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [showCandidates, setShowCandidates] = useState(false)
  const [wizardItem, setWizardItem] = useState<LibraryItemResponse | null>(null)
  const [wizardPreselect, setWizardPreselect] = useState<{ season?: number | null; episode?: number | null } | undefined>(undefined)

  // "Subir a eMuwarez" — reuse the exact same upload wizard as Biblioteca by
  // loading the matched library item and handing it to UploadWizardModal, with
  // the request's scope (season / episode) so the selection is pre-filled.
  const openUpload = useCallback(async (libraryItemId: number, preselect?: { season?: number | null; episode?: number | null }) => {
    try {
      const libItem = await getLibraryItem(libraryItemId)
      setWizardPreselect(preselect)
      setWizardItem(libItem)
    } catch { /* ignore — button only enabled when a match exists */ }
  }, [])

  const computeFacets = (list: RequestItemResponse[]) => {
    const uniq = (vals: (string | null | undefined)[]) =>
      Array.from(new Set(vals.filter((v): v is string => !!v && v.trim() !== ''))).sort()
    return {
      categories: uniq(list.map(i => i.category)),
      resolutions: uniq(list.map(i => i.requested_resolution)),
      sources: uniq(list.map(i => i.requested_source)),
      authors: uniq(list.map(i => i.author)),
      statuses: uniq(list.map(i => i.compatibility_status)),
    }
  }

  // No filter active — loadItems' own response IS the full unfiltered
  // dataset, so it can double as the facets source (see loadItems below)
  // instead of loadFacets firing a second, identical request for it.
  const isUnfiltered = !debouncedSearch && !statusFilter && !categoryFilter && !resolutionFilter && !sourceFilter && !authorFilter

  const loadItems = useCallback(async (off = 0) => {
    setLoading(true)
    setError(null)
    try {
      const res = await getRequests({
        search: debouncedSearch || undefined,
        status: statusFilter || undefined,
        category: categoryFilter || undefined,
        resolution: resolutionFilter || undefined,
        source: sourceFilter || undefined,
        author: authorFilter || undefined,
        sort: sortBy,
        limit: PAGE_SIZE,
        offset: off,
      })
      setItems(res.items)
      setTotal(res.total)
      setOffset(off)
      if (isUnfiltered && off === 0) setFacets(computeFacets(res.items))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error cargando peticiones')
    } finally {
      setLoading(false)
    }
  }, [debouncedSearch, statusFilter, categoryFilter, resolutionFilter, sourceFilter, authorFilter, sortBy, isUnfiltered])

  // Populate filter dropdown options from the full (unfiltered) dataset so they
  // stay stable regardless of the active filters. Only needed when a filter
  // IS currently active — otherwise loadItems' own unfiltered response
  // already covers it (see isUnfiltered above), and calling this too would
  // just fire the exact same request twice.
  const loadFacets = useCallback(async () => {
    try {
      const res = await getRequests({ sort: 'created_desc', limit: PAGE_SIZE, offset: 0 })
      setFacets(computeFacets(res.items))
    } catch { /* optional */ }
  }, [])

  // Reload the table whenever a filter, the search box (debounced), or the
  // sort order changes. On mount this IS the unfiltered load (all filters
  // start empty), so there's no separate loadFacets() call needed here.
  useEffect(() => {
    loadItems(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, statusFilter, categoryFilter, resolutionFilter, sourceFilter, authorFilter, sortBy])

  // Reload table + facets whenever a global sync (peticiones or otra) finishes.
  useEffect(() => {
    if (lastCompletedAt) {
      loadItems(0)
      if (!isUnfiltered) loadFacets()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastCompletedAt])

  // Keeps /requests/:id in sync with whichever request's detail is open.
  const closeRequestDetail = () => {
    closeDetailPath('requests')
    setSelectedId(null)
    setDetail(null)
    setReadiness(null)
    setShowCandidates(false)
  }

  const openRequestDetail = async (id: number) => {
    pushDetailPath('requests', id)
    setSelectedId(id)
    setShowCandidates(false)
    setDetailLoading(true)
    try {
      const [d, rr] = await Promise.allSettled([
        getRequestDetail(id),
        import('../api/requestReadiness').then(m => m.getReadiness(id)).catch(() => null),
      ])
      setDetail(d.status === 'fulfilled' ? d.value : null)
      setReadiness(rr.status === 'fulfilled' && rr.value !== null ? rr.value as RequestReadinessResponse : null)
    } catch { setDetail(null) }
    finally { setDetailLoading(false) }
  }

  const handleRowClick = async (id: number) => {
    if (selectedId === id) { closeRequestDetail(); return }
    await openRequestDetail(id)
  }

  // Deep link from the Dashboard "Recomendaciones" panel: open a specific
  // request's detail on mount when its id was stashed before navigating here.
  useEffect(() => {
    let stashed: string | null = null
    try {
      stashed = sessionStorage.getItem('emuwarez_open_request')
      if (stashed) sessionStorage.removeItem('emuwarez_open_request')
    } catch { /* ignore */ }
    const id = stashed ? parseInt(stashed, 10) : NaN
    if (!Number.isNaN(id)) handleRowClick(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Same hand-off, but live — the sessionStorage read above only fires on
  // mount, so clicking a notification while Peticiones is ALREADY the open
  // page (no remount happens) would otherwise do nothing.
  useEffect(() => {
    const onOpenRequest = (e: Event) => {
      const id = (e as CustomEvent<number>).detail
      if (id == null) return
      try { sessionStorage.removeItem('emuwarez_open_request') } catch { /* ignore */ }
      handleRowClick(id)
    }
    window.addEventListener('emuwarez:open-request', onOpenRequest)
    return () => window.removeEventListener('emuwarez:open-request', onOpenRequest)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Deep link: /requests/:id. On mount this only OPENS (never force-closes on
  // a bare /requests) — the sessionStorage/CustomEvent hand-offs above land
  // on a bare /requests path themselves and may resolve the same tick, so
  // unconditionally closing here on mount would win the race and wipe out
  // whatever they just opened. Closing on a bare path is left to real
  // back/forward navigation (popstate), which happens well after mount.
  useEffect(() => {
    const id = getDetailIdFromPath('requests')
    if (id != null) openRequestDetail(id)

    const onPopState = () => {
      const popId = getDetailIdFromPath('requests')
      if (popId == null) closeRequestDetail()
      else openRequestDetail(popId)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const displayItems = items

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {selectedId !== null ? (
        (detailLoading || !detail) ? (
          <div style={{ padding: 24 }}><LoadingState label="Cargando petición…" /></div>
        ) : (
          <RequestDetailPage
            item={detail}
            readiness={readiness}
            onBack={closeRequestDetail}
            onShowCandidates={() => setShowCandidates(true)}
            onUpload={openUpload}
            onOpenLibraryItem={goToLibraryItem}
          />
        )
      ) : (
      <>
        <div className="page-header">
          <div>
            <div className="page-title">Peticiones eMuwarez</div>
            <div className="page-subtitle">
              {total > 0 ? `${total} peticiones` : 'Peticiones activas cruzadas con tu biblioteca local'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <SyncInfo
              syncStatus={requestsStatus}
              onSync={startRequestsSync}
              syncing={requestsSyncing}
              blocked={isAnySyncing && !requestsSyncing}
              label="Sincronizar peticiones"
              title="Descarga de eMuwarez las peticiones activas y las cruza con tu biblioteca local para ver cuáles puedes cubrir. Limitado a una vez por hora."
            />
          </div>
        </div>

        <div className="filters-bar">
          <input
            className="form-input"
            type="search"
            placeholder="Buscar por título…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadItems(0)}
            style={{ minWidth: 220 }}
          />
          <select className="form-input form-select" value={sortBy} onChange={e => setSortBy(e.target.value)}>
            {SORT_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>

        {loading ? (
          <LoadingState label="Cargando peticiones…" />
        ) : error ? (
          <ErrorState message={error} onRetry={() => loadItems()} />
        ) : displayItems.length === 0 ? (
          <EmptyState
            title="Sin peticiones"
            body={
              total === 0 && !search && !statusFilter && !categoryFilter && !resolutionFilter && !sourceFilter && !authorFilter
                ? 'Sincroniza las peticiones de eMuwarez para verlas aquí.'
                : 'No hay peticiones que coincidan con los filtros.'
            }
            action={total === 0 ? (
              <button className="btn btn-primary btn-sm" onClick={() => startRequestsSync(false)} disabled={isAnySyncing}>Sincronizar peticiones</button>
            ) : undefined}
          />
        ) : (
          <div className="activity-section" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', marginBottom: 0 }}>
            <div style={{ overflow: 'auto', flex: 1, minHeight: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Título</th>
                    <th><HeaderFilter label="Tipo" value={categoryFilter} onChange={setCategoryFilter} options={[
                      { value: '', label: 'Todos' }, ...facets.categories.map(c => ({ value: c, label: c })),
                    ]} /></th>
                    <th><HeaderFilter label="Compatibilidad" value={statusFilter} onChange={setStatusFilter} options={[
                      { value: '', label: 'Todas' }, ...facets.statuses.map(s => ({ value: s, label: s })),
                    ]} /></th>
                    <th><HeaderFilter label="Autor" value={authorFilter} onChange={setAuthorFilter} options={[
                      { value: '', label: 'Todos' }, ...facets.authors.map(a => ({ value: a, label: a })),
                    ]} /></th>
                    <th><HeaderFilter label="Resolución" value={resolutionFilter} onChange={setResolutionFilter} options={[
                      { value: '', label: 'Todas' }, ...facets.resolutions.map(r => ({ value: r, label: r })),
                    ]} /></th>
                    <th><HeaderFilter label="Source" value={sourceFilter} onChange={setSourceFilter} options={[
                      { value: '', label: 'Todos' }, ...facets.sources.map(s => ({ value: s, label: s })),
                    ]} /></th>
                    <th title="Votos (otros usuarios que la quieren)" style={{ textAlign: 'center' }}><VotesIcon /></th>
                    <th title="Comentarios" style={{ textAlign: 'center' }}><CommentsIcon /></th>
                    <th title="Puntos / recompensa" style={{ textAlign: 'center' }}><PointsIcon /></th>
                    <th>Creada</th>
                  </tr>
                </thead>
                <tbody>
                  {displayItems
                    .map(item => {
                    return (
                      <tr
                        key={item.id}
                        onClick={() => handleRowClick(item.id)}
                        className={selectedId === item.id ? 'row-selected' : ''}
                        style={{ cursor: 'pointer' }}
                      >
                        <td>
                          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                            <RequestPoster url={item.poster_url} category={item.category} />
                            <div style={{ minWidth: 0 }}>
                              <HoverTitle
                                className="lib-title-link"
                                onClick={e => { e.stopPropagation(); handleRowClick(item.id) }}
                                tip="Abrir ficha"
                                style={{ fontWeight: 500 }}
                              >
                                {item.title}
                              </HoverTitle>
                            </div>
                          </div>
                        </td>
                        <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{tipoOf(item.category).label}</td>
                        <td><CompatibilityBadge status={item.compatibility_status} /></td>
                        <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}><AuthorCell author={item.author} isMine={item.is_mine} /></td>
                        <td>{item.requested_resolution || '—'}</td>
                        <td>{item.requested_source || '—'}</td>
                        <td style={{ textAlign: 'center', fontSize: 12 }}>{item.votes ?? 0}</td>
                        <td style={{ textAlign: 'center', fontSize: 12 }}>{item.comments ?? 0}</td>
                        <td style={{ textAlign: 'center', fontSize: 12, whiteSpace: 'nowrap' }}>{fmtNum(item.points)}</td>
                        <td style={{ fontSize: 12, whiteSpace: 'nowrap', color: 'var(--text-secondary)' }} title={item.created_at ? formatDate(item.created_at) : ''}>{timeAgo(item.created_at)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="pagination" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
                <button className="btn btn-secondary btn-sm" disabled={offset === 0} onClick={() => loadItems(offset - PAGE_SIZE)}>Anterior</button>
                <span style={{ fontSize: 13, color: 'var(--text-secondary)', alignSelf: 'center' }}>{currentPage} / {totalPages}</span>
                <button className="btn btn-secondary btn-sm" disabled={offset + PAGE_SIZE >= total} onClick={() => loadItems(offset + PAGE_SIZE)}>Siguiente</button>
              </div>
            )}
          </div>
        )}
      </>
      )}

      {showCandidates && selectedId !== null && (
        <div className="modal-overlay" onClick={() => setShowCandidates(false)}>
          <div className="modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
            <CandidatesPanel requestId={selectedId} onClose={() => setShowCandidates(false)} />
          </div>
        </div>
      )}

      {wizardItem && (
        <UploadWizardModal
          item={wizardItem}
          preselect={wizardPreselect}
          onClose={() => setWizardItem(null)}
          onDone={() => { setWizardItem(null); loadItems(offset) }}
          onNavigate={onNavigate}
        />
      )}
    </div>
  )
}
