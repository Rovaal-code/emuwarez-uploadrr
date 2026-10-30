import { useState, useEffect, useCallback } from 'react'
import { getRequests, getRequestDetail } from '../api/requests'
import { getCandidates } from '../api/requestReadiness'
import type {
  RequestItemResponse, RequestDetailResponse,
  RequestReadinessResponse, RequestCandidateResponse,
} from '../types/api'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState, FilaVacia } from '../components/EmptyState'
import { SyncInfo } from '../components/SyncInfo'
import { StatusBadge } from '../components/StatusBadge'
import { getRequestStatusInfo } from '../utils/status'
import { HoverTitle, useTooltip } from '../components/Tooltip'
import { useSync } from '../context/SyncContext'
import { UploadWizardModal } from '../components/UploadWizardModal'
import { getLibraryItem } from '../api/library'
import { getInstances } from '../api/instances'
import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { posterUrl, idVerifyUrl, buildDeepLink } from '../utils/libraryItem'
import { ServiceLabel } from '../components/ServiceIcon'
import { ExternalIdLink } from '../components/ExternalIdLink'
import { InfoIcon } from '../components/InfoIcon'
import {
  Card, FieldRow, DetailPoster, ValueChip, ValueIcon, PlainValue, TechChip, CheckStatusIcon, DETAIL_CARD_HEIGHT, DetailHero, DetailTitle, DetailTitleText,
  StatusCardIcon, RequestCardIcon, ExternalIdsCardIcon,
  UploadButtonIcon, ExternalLinkButtonIcon, LibraryButtonIcon,
  TypeValueIcon, AuthorValueIcon, CalendarValueIcon,
  SeasonValueIcon, EpisodeValueIcon, ResolutionValueIcon, SourceValueIcon, AnyValueIcon,
  VideoCodecValueIcon, LanguageValueIcon, SizeValueIcon,
  PointsValueIcon, ThumbsUpValueIcon, CommentValueIcon,
} from '../components/DetailCard'
import { HeaderFilter } from '../components/HeaderFilter'
import { formatBytes, timeAgo, formatDate, formatNumero } from '../utils/format'
import { getDetailIdFromPath, pushDetailPath, closeDetailPath } from '../utils/detailUrl'
import { useAlEntrar, useAlSalir } from '../context/SeccionVisible'
import { EMU_URL } from '../constants/emu'
import { IconoBloqueado, IconoDocumental, IconoPelicula, IconoSerie } from '../components/Iconos'
import { Modal } from '../components/Modal'

// Fallback for "Consultar en eMuwarez" while we don't have the exact
// per-request URL yet — points at the general requests listing instead of
// leaving the button disabled.
const EMU_REQUESTS_FALLBACK_URL = `${EMU_URL}/requests`

// A request's category maps to a friendly "Tipo" with an icon.
// The raw eMuwarez title is whatever the requester typed there — for a
// season/episode-scoped request it doesn't reliably say WHICH one, so the
// suffix is appended here, same format as the one this app itself builds
// when creating a petición (RequestFormModal): " - Temporada X" / " - SxxExx".
// Skipped if the title already ends in something matching that pattern (the
// requester already spelled it out on eMuwarez's own site).
// The year (when matched to a library item) is inserted right after `base`,
// before the " - Temporada X"/" - SxxEyy" suffix — same "Serie (Año) - …"
// convention as every other table/dedicated page (see DetailTitleText,
// which the callers below wrap this in for the muted-gray styling).
function requestDisplayTitle(item: RequestItemResponse): string {
  const base = item.title || ''
  const year = item.library_year ? ` (${item.library_year})` : ''
  if (item.req_scope === 'season' && item.req_season != null && !/temporada\s*\d+\s*$/i.test(base)) {
    return `${base}${year} - Temporada ${item.req_season}`
  }
  if (item.req_scope === 'episode' && item.req_season != null && item.req_episode != null && !/S\d{1,2}E\d{1,3}\s*$/i.test(base)) {
    const code = `S${String(item.req_season).padStart(2, '0')}E${String(item.req_episode).padStart(2, '0')}`
    return `${base}${year} - ${code}`
  }
  return `${base}${year}`
}

// eMuwarez categories arrive in whatever wording the tracker uses ("TV",
// "Movie", "Películas"…), so they're normalised once here and everything else
// keys off the result. Reading the raw string in several places is what let
// "TV" slip through every check: the Tipo column printed "TV" instead of
// "Serie", and isTv/isSeriesLike below — which decide whether a request shows
// its TVDB and MAL ids — came out false for every TV request.
type ContentKind = 'movie' | 'series' | 'doc' | null

export function contentKind(category: string | null): ContentKind {
  const c = (category || '').toLowerCase()
  if (c.includes('serie') || c.includes('tv') || c.includes('show')) return 'series'
  if (c.includes('docu')) return 'doc'
  if (c.includes('pel') || c.includes('movie') || c.includes('film')) return 'movie'
  return null
}

function tipoOf(category: string | null): { icon: React.ReactNode; label: string } {
  switch (contentKind(category)) {
    case 'series': return { icon: <IconoSerie />, label: 'Serie' }
    case 'doc': return { icon: <IconoDocumental />, label: 'Documental' }
    case 'movie': return { icon: <IconoPelicula />, label: 'Película' }
    // Something we don't recognise: show it verbatim rather than guessing.
    default: return { icon: <IconoPelicula />, label: category || '—' }
  }
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
]

const fmtNum = (n: number | null | undefined) => formatNumero(n)

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
  if (isMine) return <span style={{ color: 'var(--color-available)', fontWeight: 600 }}>{author} (Yo)</span>
  return <span>{author}</span>
}

// Comparison-table helpers.
const isAny = (v: string | null | undefined) =>
  !v || ['any', 'cualquiera', 'todos', 'all'].includes(v.trim().toLowerCase())

function noReq(v: string | null): string {
  return isAny(v) ? 'Cualquiera' : (v as string)
}

// Resolución/Source pedidos — same mini-tarjeta as the dedicated detail page
// (ValueChip + field icon), swapping in AnyValueIcon (∞) instead of the
// Resolución/Source glyph when the request has no real restriction, so
// "Cualquiera" reads as "no restriction" rather than "no data".
function SpecValueChip({ value, icon: BaseIcon }: { value: string | null; icon: React.ComponentType }) {
  const Icon = isAny(value) ? AnyValueIcon : BaseIcon
  return <ValueChip><ValueIcon><Icon /></ValueIcon><span className="txt">{noReq(value)}</span></ValueChip>
}

// Misma lógica, en texto plano para la tabla de peticiones — ahí no hay
// enlace que dar, así que no hace falta la caja de la ficha de detalle.
function SpecPlainValue({ value, icon: BaseIcon }: { value: string | null; icon: React.ComponentType }) {
  const Icon = isAny(value) ? AnyValueIcon : BaseIcon
  return <PlainValue icon={<Icon />}>{noReq(value)}</PlainValue>
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
  if (v === null) return null
  return <span style={{ display: 'inline-flex', marginLeft: 5, verticalAlign: 'middle' }}><CheckStatusIcon status={v ? 'ok' : 'fail'} /></span>
}

const baseName = (path: string | null) => (path ? path.split('/').pop() || null : null)

function CompatibilityBadge({ status }: { status: string | null }) {
  // No status at all means nothing in your library matches — the backend now
  // says so explicitly ("Sin coincidencia" → "No importada"), and this only
  // covers rows that predate that.
  return <StatusBadge status={status || 'Sin coincidencia'} type="request" />
}

// Origen: la instancia de Radarr/Sonarr donde tienes el contenido. Mismo
// aspecto y mismo enlace que la columna Origen de Biblioteca y Subidas, para
// que las cuatro pantallas digan lo mismo del mismo dato. Una petición que no
// cruza con nada ("No importada") no tiene instancia: guion, como cualquier
// otra celda sin valor. Es un componente y no JSX suelto porque useTooltip no
// puede vivir dentro del .map() de la tabla.
function OriginCell({ item, instances, size = 13, alwaysChip = true }: {
  item: RequestItemResponse | RequestDetailResponse
  instances: InstanceSafeResponse[]
  size?: number
  // La ficha de detalle enseña todos sus campos en caja, abran algo o no; la
  // tabla de peticiones solo pone caja a lo que de verdad abre algo (3.4).
  alwaysChip?: boolean
}) {
  const deepLink = buildDeepLink({
    instance_id: item.instance_id,
    instance_type: item.instance_type,
    // El tmdb del item de biblioteca, que es el que existe en esa instancia;
    // el de la petición solo como respaldo.
    tmdb_id: item.library_tmdb_id ?? item.tmdb_id,
    title_slug: item.title_slug,
  }, instances)
  const label = item.instance_name ?? item.instance_type ?? ''
  const { triggerProps, tooltipNode } = useTooltip(deepLink ? `Abrir en ${label}` : null)
  if (!item.instance_type) return <span style={{ color: 'var(--text-muted)' }}>—</span>
  const inner = deepLink
    ? <a className="hover-link" href={deepLink} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} {...triggerProps}><ServiceLabel type={item.instance_type} label={label} size={size} />{tooltipNode}</a>
    : <ServiceLabel type={item.instance_type} label={label} size={size} />
  if (!deepLink && !alwaysChip) return inner
  return <ValueChip linkable={!!deepLink}>{inner}</ValueChip>
}

function ReadinessBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>
  const color =
    status === 'ready_to_upload' ? 'var(--color-available-soft)' :
    status === 'needs_nomenclature' ? 'var(--color-warning)' :
    status === 'preflight_needed' ? 'var(--color-accent-soft)' :
    status === 'downloading' ? 'var(--color-downloading)' :
    status === 'uploaded' ? 'var(--color-available-pale)' :
    status === 'no_local_match' ? 'var(--text-muted)' :
    status.includes('error') || status.includes('missing') || status === 'blocked' ? 'var(--color-missing)' :
    'var(--text-secondary)'
  return <span style={{ fontSize: 11, color, fontWeight: 500 }}>{status}</span>
}

function CandidatesPanel({ requestId }: { requestId: number }) {
  const [candidates, setCandidates] = useState<RequestCandidateResponse[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCandidates(requestId)
      .then(setCandidates)
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false))
  }, [requestId])

  return (
    <div className="modal-body">
      {loading ? <LoadingState label="Cargando candidatos…" /> : candidates.length === 0 ? (
        <div className="empty-inline">Sin candidatos en biblioteca. Ejecuta “Recalcular readiness”.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 0' }}>
          {candidates.map(c => (
            <div key={c.id} className="detail-card" style={{ padding: '10px 14px', borderRadius: 6, fontSize: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>#{c.candidate_rank}: {c.lib_title || `Lib #${c.library_item_id}`}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 12px', color: 'var(--text-secondary)' }}>
                <span>Compat: <strong>{c.compatibility_score?.toFixed(0) ?? '—'}</strong></span>
                <span>Readiness: <strong>{c.readiness_score?.toFixed(0) ?? '—'}</strong></span>
                <span>Estado: {c.local_status || '—'}</span>
                <span>Resolución: {c.resolution || '—'}</span>
              </div>
              {c.blockers.length > 0 && (
                <div style={{ marginTop: 4, color: 'var(--color-missing)', fontSize: 11 }}>
                  <IconoBloqueado /> {c.blockers.join(', ')}
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

function CreatedAtCell({ createdAt }: { createdAt: string | null | undefined }) {
  const { triggerProps, tooltipNode } = useTooltip(createdAt ? formatDate(createdAt) : null)
  return (
    <td style={{ fontSize: 12, whiteSpace: 'nowrap', color: 'var(--text-secondary)' }} {...triggerProps}>
      {timeAgo(createdAt)}
      {tooltipNode}
    </td>
  )
}

// Full dedicated request page — same visual format as the library item detail
// page (back button, big poster left, title + fields grid right).
function RequestDetailPage({ item, readiness, instances, onBack, onShowCandidates, onUpload, onOpenLibraryItem }: {
  item: RequestDetailResponse
  readiness: RequestReadinessResponse | null
  instances: InstanceSafeResponse[]
  onBack: () => void
  onShowCandidates: () => void
  onUpload: (libraryItemId: number, preselect?: { season?: number | null; episode?: number | null }) => void
  onOpenLibraryItem?: (id: number) => void
}) {
  const m = item.match
  const effectiveStatus = m ? m.status : (item.compatibility_status ?? null)
  const libId = m?.library_item_id ?? item.library_item_id
  // What a link out of this request should open: the season's own row for a
  // season request, the matched row otherwise.
  const libraryTargetId = m?.library_target_id ?? libId
  const titleLinkTip = useTooltip('Ver en la biblioteca')
  const t = tipoOf(item.category)
  // External IDs: prefer the request's own, fall back to the matched library
  // item. TVDB only ever comes from the library item (Radarr/Sonarr); MAL
  // comes from eMuwarez on the request side, or from the library item's own
  // Fribb/anime-lists resolution (see services/anime_lists.py) otherwise.
  const kind = contentKind(item.category)
  const isTv = kind === 'series'
  const isSeriesLike = kind === 'series' || kind === 'doc'
  const tmdbId = item.tmdb_id || m?.local_tmdb_id || null
  const imdbId = item.imdb_id || m?.local_imdb_id || null
  const tvdbId = item.tvdb_id || m?.local_tvdb_id || null
  const malId = item.mal_id || m?.local_mal_id || null
  const hasSeason = item.req_scope === 'season' || item.req_scope === 'episode'
  const temporadaLabel = hasSeason ? String(item.req_season ?? '?') : 'Todas'
  const consultarTip = useTooltip(item.url
    ? 'Abrir la petición en eMuwarez (reclamarla, marcarla como llena, ver el ID del torrent…)'
    : 'Todavía no tenemos la URL exacta de esta petición: abre el listado general de peticiones en eMuwarez')
  const subirTip = useTooltip(libId
    ? 'Subir el contenido de tu biblioteca a eMuwarez (mismo asistente que en Biblioteca)'
    : 'No tienes este contenido en tu biblioteca')
  const reqNameTip = useTooltip(m?.content_name || null)
  const libNameTip = useTooltip(m?.content_name || baseName(m?.local_path ?? null) || m?.library_title || null)
  return (
    <div style={{ width: '100%', flex: 1, minHeight: 0, overflowY: 'auto' }}>
      <DetailHero backdropUrl={item.backdrop_url}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-ghost btn-sm" onClick={onBack}>Volver a peticiones</button>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0, flexWrap: 'wrap' }}>
          <a
            className="btn btn-primary btn-sm"
            href={item.url || EMU_REQUESTS_FALLBACK_URL}
            target="_blank"
            rel="noreferrer"
            style={{ textDecoration: 'none' }}
            {...consultarTip.triggerProps}
          >
            <ExternalLinkButtonIcon /> Consultar en eMuwarez
            {consultarTip.tooltipNode}
          </a>
          <button
            className="btn btn-primary btn-sm"
            disabled={!libraryTargetId}
            // libraryTargetId, no libId: el asistente tiene que abrirse sobre
            // la fila a la que se refiere la petición (la temporada, o el
            // capítulo), no sobre la que cruzó el emparejador, que para una
            // serie es la serie entera. Si no, pedir la Temporada 2 abría el
            // flujo de serie con una preselección, en vez de las tarjetas de
            // "Temporada entera" / "Selección de capítulos" que salen al
            // pulsar Subir en la ficha de esa temporada en Biblioteca.
            onClick={() => libraryTargetId && onUpload(libraryTargetId, {
              season: item.req_season,
              episode: item.req_scope === 'episode' ? item.req_episode : null,
            })}
            {...subirTip.triggerProps}
          >
            <UploadButtonIcon /> Subir a eMuwarez
            {subirTip.tooltipNode}
          </button>
        </div>
      </div>

      <div style={{ marginBottom: 20 }}>
        {/* Follows library_target_id, not the match's library_item_id: for a
            season request the matcher lands on the SERIES row (every season
            shares the series' tmdb_id), so linking that opened the whole
            series instead of the season you clicked. */}
        <DetailTitle>
          {libraryTargetId ? (
            <span
              className="lib-title-link"
              style={{ cursor: 'pointer' }}
              onClick={() => onOpenLibraryItem?.(libraryTargetId)}
              {...titleLinkTip.triggerProps}
            >
              <DetailTitleText title={item.display_title || requestDisplayTitle(item)} />
              {titleLinkTip.tooltipNode}
            </span>
          ) : (
            <DetailTitleText title={item.display_title || requestDisplayTitle(item)} />
          )}
        </DetailTitle>
      </div>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <DetailPoster url={item.poster_url ? posterUrl(item.poster_url, 'w500') : null} alt={item.title} fallbackIcon={t.icon} />

        <div style={{ flex: 1, minWidth: 300 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16, minHeight: DETAIL_CARD_HEIGHT }}>
            <Card title="Estado de la petición" icon={<StatusCardIcon />}>
              <FieldRow label="Estado" help="Aunque salga «Compatible», revisa la petición: el audio y el códec no se pueden comparar del todo (suelen indicarse en la descripción del torrent), y si pide la serie completa puede que no quiera la temporada especial."><CompatibilityBadge status={effectiveStatus} /></FieldRow>
              <FieldRow label="Tipo">
                <ValueChip><ValueIcon><TypeValueIcon /></ValueIcon><span className="txt">{t.label}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Origen">
                <OriginCell item={item} instances={instances} size={15} />
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
                <SpecValueChip value={item.requested_resolution} icon={ResolutionValueIcon} />
              </FieldRow>
              <FieldRow label="Source pedido">
                <SpecValueChip value={item.requested_source} icon={SourceValueIcon} />
              </FieldRow>
              <FieldRow label="Puntos">
                <ValueChip><ValueIcon><PointsValueIcon /></ValueIcon><span className="txt">{fmtNum(item.points)}</span></ValueChip>
              </FieldRow>
              {/* eMuwarez no da votos ni comentarios: sin dato, sin fila. */}
              {item.votes != null && (
                <FieldRow label="Votos">
                  <ValueChip><ValueIcon><ThumbsUpValueIcon /></ValueIcon><span className="txt">{item.votes}</span></ValueChip>
                </FieldRow>
              )}
              {item.comments != null && (
                <FieldRow label="Comentarios">
                  <ValueChip><ValueIcon><CommentValueIcon /></ValueIcon><span className="txt">{item.comments}</span></ValueChip>
                </FieldRow>
              )}
            </Card>

            <Card title="Identificadores externos" icon={<ExternalIdsCardIcon />}>
              <IdField label="TMDb" id={tmdbId} href={idVerifyUrl('tmdb', tmdbId, isTv)} />
              <IdField label="IMDb" id={imdbId} href={idVerifyUrl('imdb', imdbId, isTv)} />
              <IdField label="TVDB" id={tvdbId} href={idVerifyUrl('tvdb', tvdbId, isTv)} />
              {/* MAL always shown (mainly for anime); "—" when the request had none. */}
              <FieldRow label="MAL">
                {malId
                  ? <ValueChip linkable={Boolean(idVerifyUrl('mal', malId, isTv))}><ExternalIdLink id={malId} href={idVerifyUrl('mal', malId, isTv)} label="MAL" /></ValueChip>
                  : <span className="muted">—</span>}
              </FieldRow>
            </Card>
          </div>
        </div>
      </div>
      </DetailHero>

      <div style={{ marginTop: 17 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 15 }}>
          Petición vs. tu biblioteca
        </div>
        <div className="detail-card" style={{ borderRadius: 10, padding: '21px 19px' }}>
          {!m ? (
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Sin coincidencia en tu biblioteca local, no tienes este contenido importado en tus instancias de Radarr o Sonarr.</span>
          ) : (
            <>
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table" style={{ fontSize: 12.5 }}>
                  <thead>
                    <tr>
                      <th>Contenido</th><th>Título</th><th>Resolución</th><th>Source</th>
                      <th><span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>Códec <InfoIcon text="El códec no se puede comparar de forma fiable: en eMuwarez suele indicarse en la descripción del torrent, no en los campos." /></span></th>
                      <th><span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>Idiomas <InfoIcon text="El audio/idiomas no se pueden comparar de forma fiable: suelen indicarse en la descripción del torrent." /></span></th>
                      <th>Tamaño</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>Petición</td>
                      <td style={{ maxWidth: 320 }} {...reqNameTip.triggerProps}>
                        <ValueChip>
                          <ValueIcon><LibraryButtonIcon /></ValueIcon>
                          <span className="txt" style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.content_name || '—'}</span>
                        </ValueChip>
                        {reqNameTip.tooltipNode}
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}><SpecValueChip value={item.requested_resolution} icon={ResolutionValueIcon} /></td>
                      <td style={{ whiteSpace: 'nowrap' }}><SpecValueChip value={item.requested_source} icon={SourceValueIcon} /></td>
                      <td style={{ color: 'var(--text-muted)' }}>—</td>
                      <td style={{ color: 'var(--text-muted)' }}>—</td>
                      <td style={{ color: 'var(--text-muted)' }}>—</td>
                    </tr>
                    <tr style={{ background: 'color-mix(in srgb, var(--color-available) 6%, transparent)' }}>
                      <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>Tu biblioteca</td>
                      <td style={{ maxWidth: 320 }} {...libNameTip.triggerProps}>
                        {libId
                          ? (
                            <ValueChip as="button" linkable onClick={() => libraryTargetId && onOpenLibraryItem?.(libraryTargetId)} title="Ver ficha del contenido">
                              <ValueIcon><LibraryButtonIcon /></ValueIcon>
                              <span className="txt" style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.content_name || baseName(m.local_path) || m.library_title || '—'}</span>
                            </ValueChip>
                          )
                          : (
                            <ValueChip>
                              <ValueIcon><LibraryButtonIcon /></ValueIcon>
                              <span className="txt" style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.content_name || baseName(m.local_path) || m.library_title || '—'}</span>
                            </ValueChip>
                          )}
                        {libNameTip.tooltipNode}
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={ResolutionValueIcon} value={m.local_resolution} />{cellMark(satisfies(item.requested_resolution, m.local_resolution, m.resolution_match))}</td>
                      <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={SourceValueIcon} value={m.local_source} />{cellMark(satisfies(item.requested_source, m.local_source, m.source_match))}</td>
                      <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={VideoCodecValueIcon} value={m.local_video_codec} /></td>
                      <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={LanguageValueIcon} value={m.local_audio_languages} /></td>
                      <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={SizeValueIcon} value={m.local_size ? formatBytes(m.local_size) : null} /></td>
                    </tr>
                  </tbody>
                </table>
                {/* The library row's specs come from a file that isn't on
                    disk, so there is nothing real to compare against. Without
                    saying so, the table reads as a contradiction. */}
                {m.local_status === 'Faltante' && (
                  <p style={{ fontSize: 12.5, margin: '10px 0 0', color: 'var(--color-warning)' }}>
                    Este contenido está con el estado de Faltante en tu biblioteca local, así que
                    no es posible hacer la comparación.
                  </p>
                )}
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
            <div className="detail-row"><span>Acción</span><span style={{ fontSize: 12, color: 'var(--color-uploading)' }}>{readiness.recommended_action || '—'}</span></div>
            <div className="detail-row"><span>Compat. score</span><span>{readiness.compatibility_score?.toFixed(0) ?? '—'}/100</span></div>
            <div className="detail-row"><span>Readiness score</span><span>{readiness.upload_readiness_score?.toFixed(0) ?? '—'}/100</span></div>
            {readiness.blockers.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>BLOQUEADORES</div>
                {readiness.blockers.map((b, i) => (
                  <div key={i} style={{ fontSize: 11, color: 'var(--color-missing)' }}><IconoBloqueado /> {b}</div>
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
  // Volver aquí no vuelve a enseñar "Cargando…" ni reinicia los filtros: la
  // sección no se desmonta al cambiar de pestaña, se queda montada y oculta
  // (ver AppShell). Esto solo corre la PRIMERA vez que se entra.
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
  const { requestsSyncing, requestsStatus, startRequestsSync, lastInvalidatedAt, isAnySyncing } = useSync()

  // Solo para el enlace de la columna Origen, igual que en Subidas: el nombre
  // de la instancia ya viene en cada petición, pero su URL no.
  const [instances, setInstances] = useState<InstanceSafeResponse[]>([])
  useEffect(() => { getInstances().then(setInstances).catch(() => {}) }, [])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<RequestDetailResponse | null>(null)
  const [readiness, setReadiness] = useState<RequestReadinessResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [showCandidates, setShowCandidates] = useState(false)
  const [wizardItem, setWizardItem] = useState<LibraryItemResponse | null>(null)
  const [wizardPreselect, setWizardPreselect] = useState<{ season?: number | null; episode?: number | null } | undefined>(undefined)
  const votesHeaderTip = useTooltip('Votos (otros usuarios que la quieren)')
  const commentsHeaderTip = useTooltip('Comentarios')
  const pointsHeaderTip = useTooltip('Puntos / recompensa')

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
      // Null reads as "no library match", which the filter knows by name —
      // don't let uniq() drop it or that state stays unfilterable.
      statuses: uniq(list.map(i => i.compatibility_status || 'Sin coincidencia')),
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
      if (isUnfiltered && off === 0) {
        setFacets(computeFacets(res.items))
        if (sortBy === 'created_desc') {
        }
      }
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

  // Reload table + facets whenever what's loaded stops being valid: a global
  // sync finishing (peticiones u otra), or coming back to the tab.
  useEffect(() => {
    if (lastInvalidatedAt) {
      loadItems(0)
      if (!isUnfiltered) loadFacets()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastInvalidatedAt])

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
  // request's detail when its id se apuntó antes de venir aquí. Al ENTRAR y
  // no al montar: la sección ya no se levanta de cero en cada visita (ver
  // context/SeccionVisible).
  useAlEntrar(() => {
    let stashed: string | null = null
    try {
      stashed = sessionStorage.getItem('emuwarez_open_request')
      if (stashed) sessionStorage.removeItem('emuwarez_open_request')
    } catch { /* ignore */ }
    const id = stashed ? parseInt(stashed, 10) : NaN
    if (!Number.isNaN(id)) handleRowClick(id)
  })

  function quitarFiltros() {
    setSearch(''); setDebouncedSearch('')
    setStatusFilter(''); setCategoryFilter(''); setResolutionFilter('')
    setSourceFilter(''); setAuthorFilter('')
    setOffset(0)
  }
  // Al salir, de vuelta a la tabla sin filtros y con el orden por defecto.
  useAlSalir(() => {
    closeRequestDetail()
    quitarFiltros()
    setSortBy('created_desc')
  })

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
  // Las peticiones reales no traen votos ni comentarios: sin dato, sin columna.
  const hayVotos = displayItems.some(i => i.votes != null)
  const hayComentarios = displayItems.some(i => i.comments != null)

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div data-tour="requests-content" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {selectedId !== null ? (
        (detailLoading || !detail) ? (
          <div style={{ padding: 24 }}><LoadingState label="Cargando petición…" /></div>
        ) : (
          <RequestDetailPage
            instances={instances}
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
            <div className="page-title">Peticiones</div>
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

        {/* Solo bloquea la PRIMERA vez, cuando todavía no hay nada que enseñar.
            Al ordenar o filtrar la tabla se queda puesta: cambiarla por un
            "Cargando…" para volver medio segundo después es un parpadeo, y
            encima te deja sin la referencia de lo que estabas mirando. */}
        {loading && items.length === 0 && isUnfiltered ? (
          <LoadingState label="Cargando peticiones…" />
        ) : error ? (
          <ErrorState message={error} onRetry={() => loadItems()} />
        ) : displayItems.length === 0 && isUnfiltered ? (
          <EmptyState
            title="Sin peticiones"
            body="Sincroniza las peticiones de eMuwarez para verlas aquí."
            action={<button className="btn btn-primary btn-sm" onClick={() => startRequestsSync(false)} disabled={isAnySyncing}>Sincronizar peticiones</button>}
          />
        ) : (
          <div className="activity-section" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', marginBottom: 0 }}>
            <div style={{ overflow: 'auto', flex: 1, minHeight: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Título</th>
                    <th><HeaderFilter label="Tipo" value={categoryFilter} onChange={setCategoryFilter} options={[
                      // Same label the Tipo column shows, or the filter would
                      // offer "TV" for a column that says "Serie".
                      { value: '', label: 'Todos' }, ...facets.categories.map(c => ({ value: c, label: tipoOf(c).label })),
                    ]} /></th>
                    <th>Origen</th>
                    <th><HeaderFilter label="Compatibilidad" value={statusFilter} onChange={setStatusFilter} options={[
                      // Labels, not raw values, or the filter would offer
                      // "No disponible" for a column that says "Faltante".
                      { value: '', label: 'Todas' }, ...facets.statuses.map(s => ({ value: s, label: getRequestStatusInfo(s).label })),
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
                    {hayVotos && <th style={{ textAlign: 'center' }} {...votesHeaderTip.triggerProps}><VotesIcon />{votesHeaderTip.tooltipNode}</th>}
                    {hayComentarios && <th style={{ textAlign: 'center' }} {...commentsHeaderTip.triggerProps}><CommentsIcon />{commentsHeaderTip.tooltipNode}</th>}
                    <th style={{ textAlign: 'center' }} {...pointsHeaderTip.triggerProps}><PointsIcon />{pointsHeaderTip.tooltipNode}</th>
                    <th>Creada</th>
                  </tr>
                </thead>
                {displayItems.length === 0 && (
                  <FilaVacia
                    columnas={9 + Number(hayVotos) + Number(hayComentarios)}
                    title="Sin peticiones"
                    body="No hay peticiones que coincidan con los filtros."
                    action={<button className="btn btn-primary btn-sm" onClick={quitarFiltros}>Quitar filtros</button>}
                  />
                )}
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
                                <DetailTitleText title={requestDisplayTitle(item)} />
                              </HoverTitle>
                            </div>
                          </div>
                        </td>
                        <td style={{ whiteSpace: 'nowrap' }}>
                          <PlainValue icon={<TypeValueIcon />}>{tipoOf(item.category).label}</PlainValue>
                        </td>
                        <td style={{ whiteSpace: 'nowrap' }}><OriginCell item={item} instances={instances} alwaysChip={false} /></td>
                        <td><CompatibilityBadge status={item.compatibility_status} /></td>
                        <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}><AuthorCell author={item.author} isMine={item.is_mine} /></td>
                        <td style={{ whiteSpace: 'nowrap' }}><SpecPlainValue value={item.requested_resolution} icon={ResolutionValueIcon} /></td>
                        <td style={{ whiteSpace: 'nowrap' }}><SpecPlainValue value={item.requested_source} icon={SourceValueIcon} /></td>
                        {hayVotos && <td style={{ textAlign: 'center', fontSize: 12 }}>{item.votes ?? '—'}</td>}
                        {hayComentarios && <td style={{ textAlign: 'center', fontSize: 12 }}>{item.comments ?? '—'}</td>}
                        <td style={{ textAlign: 'center', fontSize: 12, whiteSpace: 'nowrap' }}>{fmtNum(item.points)}</td>
                        <CreatedAtCell createdAt={item.created_at} />
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
        <Modal titulo="Candidatos locales" onClose={() => setShowCandidates(false)} style={{ maxWidth: 520 }}>
          <CandidatesPanel requestId={selectedId} />
        </Modal>
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
