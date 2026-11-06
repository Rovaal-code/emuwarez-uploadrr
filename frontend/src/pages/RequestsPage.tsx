import { useState, useEffect, useCallback, useRef } from 'react'
import { getRequests, getRequestDetail } from '../api/requests'
import { getCandidates, getReadiness } from '../api/requestReadiness'
import type {
  RequestItemResponse, RequestDetailResponse,
  RequestReadinessResponse, RequestCandidateResponse,
} from '../types/api'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState, FilaVacia } from '../components/EmptyState'
import { SyncInfo } from '../components/SyncInfo'
import { StatusBadge } from '../components/StatusBadge'
import { getReadinessActionLabel, getReadinessLabel, getReclamadaInfo, getRequestStatusInfo } from '../utils/status'
import { HoverTitle, Tooltip, useTooltip } from '../components/Tooltip'
import { useSync } from '../context/SyncContext'
import { UploadWizardModal } from '../components/UploadWizardModal'
import { getLibraryItem } from '../api/library'
import { useInstancias } from '../hooks/useInstancias'
import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { posterUrl, idVerifyUrl, buildDeepLink } from '../utils/libraryItem'
import { ServiceLabel } from '../components/ServiceIcon'
import { ExternalIdLink } from '../components/ExternalIdLink'
import { InfoIcon } from '../components/InfoIcon'
import { GruposDeRelease } from '../components/GruposDeRelease'
import {
  Card, FieldRow, ValueChip, ValueIcon, PlainValue, TechChip, CheckStatusIcon, DetailHero, DetailTitle, DetailTitleText,
  StatusCardIcon, RequestCardIcon, ExternalIdsCardIcon,
  UploadButtonIcon, ExternalLinkButtonIcon, LibraryButtonIcon,
  TypeValueIcon, AuthorValueIcon, CalendarValueIcon,
  SeasonValueIcon, EpisodeValueIcon, ResolutionValueIcon, SourceValueIcon, AnyValueIcon,
  VideoCodecValueIcon, LanguageValueIcon, SizeValueIcon,
  ThumbsUpValueIcon, CommentValueIcon,
} from '../components/DetailCard'
import { HeaderFilter } from '../components/HeaderFilter'
import { HeaderSort } from '../components/HeaderSort'
import { formatBytes, timeAgo, formatDate, formatNumero } from '../utils/format'
import { getDetailIdFromPath, pushDetailPath, closeDetailPath } from '../utils/detailUrl'
import { agruparPeticiones, requestDisplayTitle, motivoDeLaPreparacion, grupoDePeticion, GRUPOS_PETICION, type GrupoPeticion } from '../utils/peticiones'
import { FichaPoster } from '../components/FichaPoster'
import { useAlEntrar, useAlSalir } from '../context/SeccionVisible'
import { EMU_URL } from '../constants/emu'
import { IconoBloqueado, IconoDesplegar, IconoDocumental, IconoPelicula, IconoPuntos, IconoSerie } from '../components/Iconos'
import { Modal } from '../components/Modal'
import { BarraLote } from '../components/lote/BarraLote'
import { CasillaLote } from '../components/lote/CasillaLote'
import { SubidaPorLotesModal } from '../components/lote/SubidaPorLotesModal'
import { useSeleccionLote } from '../hooks/useSeleccionLote'
import { entradaDePeticion, peticionSeleccionableEnLote, type EntradaLote } from '../utils/lote'

// Fallback for "Consultar en eMuwarez" while we don't have the exact
// per-request URL yet — points at the general requests listing instead of
// leaving the button disabled.
const EMU_REQUESTS_FALLBACK_URL = `${EMU_URL}/requests`

// A request's category maps to a friendly "Tipo" with an icon.
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
    : { width: 28, height: 42, radius: 4, font: 14 }
  const t = tipoOf(category)
  return (
    <div className="poster-thumb pet-poster" style={{ width: dims.width, height: dims.height, borderRadius: dims.radius }}>
      {url ? (
        <img
          src={posterUrl(url, size === 'lg' ? 'w342' : 'w154')}
          alt=""
          loading="lazy"
          className="pet-poster-img"
          onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
        />
      ) : (
        <span className="pet-poster-icono" style={{ fontSize: dims.font }}>{t.icon}</span>
      )}
    </div>
  )
}

// Sin orden elegido: la lista va en grupos por lo que se puede hacer y, dentro de cada uno, por recompensa.
// Elegir cualquier otro orden (el selector o una cabecera) la deja plana: la cabecera manda.
const ORDEN_POR_GRUPOS = 'grupos'

const SORT_OPTIONS = [
  { value: ORDEN_POR_GRUPOS, label: 'Orden: Por estado y recompensa' },
  { value: 'created_desc', label: 'Orden: Más recientes' },
  { value: 'created_asc', label: 'Orden: Más antiguas' },
  { value: 'title', label: 'Orden: Título (A-Z)' },
  { value: 'points_desc', label: 'Orden: Más puntos' },
  { value: 'points_asc', label: 'Orden: Menos puntos' },
]

const fmtNum = (n: number | null | undefined) => formatNumero(n)

// Inline SVG icons for the votes/comments/points columns — emoji (👍💬🪙)
// render as bare white outlines on some systems, so use real vector icons.
// La moneda de los puntos es IconoPuntos (Iconos.tsx): la comparte el Panel.
function Svg({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <svg viewBox="0 0 24 24" width={15} height={15} fill={color} className="pet-svg-medio" aria-hidden="true">
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

// Author cell — your own requests (author === emu.username) show in green + "(Yo)".
function AuthorCell({ author, isMine }: { author: string | null; isMine: boolean }) {
  if (!author) return <span className="pet-muted">—</span>
  if (isMine) return <span className="pet-mio">{author} (Yo)</span>
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
  return <span className="pet-marca"><CheckStatusIcon status={v ? 'ok' : 'fail'} /></span>
}

const baseName = (path: string | null) => (path ? path.split('/').pop() || null : null)

function CompatibilityBadge({ status, reclamada }: { status: string | null; reclamada?: string | null }) {
  // No status at all means nothing in your library matches — the backend now
  // says so explicitly ("Sin coincidencia" → "No importada"), and this only
  // covers rows that predate that.
  const estado = status || 'Sin coincidencia'
  const quien = getReclamadaInfo(reclamada)
  const { triggerProps, tooltipNode } = useTooltip(estado === 'Reclamado' ? quien?.hint ?? null : null)
  if (estado === 'Reclamado' && quien) {
    // La petición reclamada por otro (o sin saber por quién) dice quién, en vez de un «Reclamado» a secas.
    return <span className={`badge ${getRequestStatusInfo(estado).cssClass}`} {...triggerProps}>{quien.label}{tooltipNode}</span>
  }
  if (reclamada === 'ti') {
    // La que has reclamado tú se puede subir: se enseña su estado de siempre y que es tuya.
    return (
      <span className="pet-badges">
        <StatusBadge status={estado} type="request" />
        <span className={`badge ${getRequestStatusInfo('Reclamado').cssClass}`}>{quien?.label}</span>
      </span>
    )
  }
  return <StatusBadge status={estado} type="request" />
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
  if (!item.instance_type) return <span className="pet-muted">—</span>
  const inner = deepLink
    ? <a className="hover-link" href={deepLink} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} {...triggerProps}><ServiceLabel type={item.instance_type} label={label} size={size} />{tooltipNode}</a>
    : <ServiceLabel type={item.instance_type} label={label} size={size} />
  if (!deepLink && !alwaysChip) return inner
  return <ValueChip linkable={!!deepLink}>{inner}</ValueChip>
}

function ReadinessBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="pet-muted-11">—</span>
  const color =
    status === 'ready_to_upload' ? 'var(--color-available-soft)' :
    status === 'needs_nomenclature' ? 'var(--color-warning)' :
    status === 'preflight_needed' ? 'var(--color-accent-soft)' :
    status === 'downloading' ? 'var(--color-downloading)' :
    status === 'uploaded' ? 'var(--color-available-pale)' :
    status === 'no_local_match' || status === 'claimed' || status === 'filled' ? 'var(--text-muted)' :
    status === 'spec_mismatch' || status === 'no_castellano' ? 'var(--color-warning)' :
    status.includes('error') || status.includes('missing') || status === 'blocked' ? 'var(--color-missing)' :
    'var(--text-secondary)'
  return <span className="pet-estado-11" style={{ color }}>{getReadinessLabel(status)}</span>
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
        <div className="pet-cand-lista">
          {candidates.map(c => (
            <div key={c.id} className="detail-card pet-cand">
              <div className="pet-cand-titulo">#{c.candidate_rank}: {c.lib_title || `Lib #${c.library_item_id}`}</div>
              <div className="pet-cand-datos">
                <span>Compat: <strong>{c.compatibility_score?.toFixed(0) ?? '—'}</strong></span>
                <span>Readiness: <strong>{c.readiness_score?.toFixed(0) ?? '—'}</strong></span>
                <span>Estado: {c.local_status || '—'}</span>
                <span>Resolución: {c.resolution || '—'}</span>
              </div>
              {c.blockers.length > 0 && (
                <div className="pet-cand-bloq">
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
    <td className="pet-creada pet-sec" {...triggerProps}>
      {timeAgo(createdAt)}
      {tooltipNode}
    </td>
  )
}

// Lo primero de la ficha: qué se puede hacer con esta petición y por qué, con la recompensa al lado. El tono es el
// único color del recuadro y siempre va con símbolo y texto (el mismo patrón que el resultado de una subida).
const VEREDICTO_SIMBOLO: Record<GrupoPeticion, string> = { lista: '✓', parcial: '!', sin_copia: '○', cerrada: '■' }

function VeredictoPeticion({ item, estado, preparacion }: {
  item: RequestDetailResponse
  estado: string | null
  preparacion: RequestReadinessResponse | null
}) {
  const grupo = grupoDePeticion({ readiness_status: preparacion?.status ?? item.readiness_status ?? null, compatibility_status: estado })
  const info = GRUPOS_PETICION.find(g => g.id === grupo)!
  const motivo = motivoDeLaPreparacion({ readiness_status: preparacion?.status ?? item.readiness_status ?? null })
  const quien = getReclamadaInfo(item.reclamada_por)
  return (
    <section className={`detail-card pet-veredicto pet-tono-${grupo}`} aria-label="Qué se puede hacer con esta petición">
      <span className="pet-veredicto-simbolo" aria-hidden="true">{VEREDICTO_SIMBOLO[grupo]}</span>
      <div className="pet-veredicto-texto">
        <p className="pet-veredicto-titulo">
          {info.titulo}
          <InfoIcon text="Aunque salga «Compatible», revisa la petición: el audio y el códec no se pueden comparar del todo (suelen indicarse en la descripción del torrent), y si pide la serie completa puede que no quiera la temporada especial." />
        </p>
        <p className="pet-veredicto-ayuda">{info.ayuda}</p>
        <div className="pet-veredicto-estado">
          <CompatibilityBadge status={estado} reclamada={item.reclamada_por} />
          {motivo && <span className="pet-motivo">{motivo}</span>}
          {item.reclamada_por === 'ti' && quien && <span className="pet-motivo">{quien.label}</span>}
        </div>
      </div>
      <div className="pet-veredicto-premio">
        <span className="pet-veredicto-premio-etiqueta">Recompensa</span>
        <span className="pet-veredicto-premio-valor">
          {item.points != null ? <><IconoPuntos />{fmtNum(item.points)}</> : <span className="pet-muted">Sin puntos</span>}
        </span>
      </div>
    </section>
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
  onUpload: (libraryItemId: number, preselect?: { season?: number | null; episode?: number | null }, requestId?: number) => void
  onOpenLibraryItem?: (id: number) => void
}) {
  const m = item.match
  const effectiveStatus = m ? m.status : (item.compatibility_status ?? null)
  const libId = m?.library_item_id ?? item.library_item_id
  // What a link out of this request should open: the season's own row for a
  // season request, the matched row otherwise.
  const libraryTargetId = m?.library_target_id ?? libId
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
    <div className="pet-detalle">
      <DetailHero backdropUrl={item.backdrop_url}>
      <div className="pet-barra">
        <div className="pet-grupo">
          <button className="btn btn-ghost btn-sm" onClick={onBack}>Volver a peticiones</button>
        </div>
        <div className="pet-grupo pet-no-encoge">
          {/* Secundario: la acción principal de la ficha es «Subir a eMuwarez», y solo ella brilla. */}
          <a
            className="btn btn-secondary btn-sm pet-sin-subrayado"
            href={item.url || EMU_REQUESTS_FALLBACK_URL}
            target="_blank"
            rel="noreferrer"
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
            }, item.id)}
            {...subirTip.triggerProps}
          >
            <UploadButtonIcon /> Subir a eMuwarez
            {subirTip.tooltipNode}
          </button>
        </div>
      </div>

      <div className="pet-mb-20">
        {/* Follows library_target_id, not the match's library_item_id: for a
            season request the matcher lands on the SERIES row (every season
            shares the series' tmdb_id), so linking that opened the whole
            series instead of the season you clicked. */}
        <DetailTitle>
          {libraryTargetId ? (
            // HoverTitle con onClick es un enlace de teclado (Tab e Intro), como el título de cada fila de la lista.
            <HoverTitle as="span" className="lib-title-link" onClick={() => onOpenLibraryItem?.(libraryTargetId)} tip="Ver en la biblioteca">
              <DetailTitleText title={item.display_title || requestDisplayTitle(item)} />
            </HoverTitle>
          ) : (
            <DetailTitleText title={item.display_title || requestDisplayTitle(item)} />
          )}
        </DetailTitle>
      </div>

      <div className="pet-ficha">
        <FichaPoster url={item.poster_url ? posterUrl(item.poster_url, 'w500') : null} alt={item.title} fallbackIcon={t.icon} />

        <div className="pet-ficha-col">
          <VeredictoPeticion item={item} estado={effectiveStatus} preparacion={readiness} />
          <div className="pet-ficha-grid">
            <Card title="La petición" icon={<StatusCardIcon />}>
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

            <Card title="Lo que piden" icon={<RequestCardIcon />}>
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

      <div className="pet-comparar">
        <div className="pet-comparar-titulo">
          Petición vs. tu biblioteca
        </div>
        <div className="detail-card pet-comparar-card">
          {!m ? (
            <span className="pet-sin-coincidencia">Sin coincidencia en tu biblioteca local, no tienes este contenido importado en tus instancias de Radarr o Sonarr.</span>
          ) : (
            <>
              <div className="pet-scroll-x">
                <table className="data-table pet-tabla-comparar">
                  <thead>
                    <tr>
                      <th>Contenido</th><th>Título</th><th>Resolución</th><th>Source</th><th>Grupo</th>
                      <th><span className="pet-th-flex">Códec <InfoIcon text="El códec no se puede comparar de forma fiable: en eMuwarez suele indicarse en la descripción del torrent, no en los campos." /></span></th>
                      <th><span className="pet-th-flex">Idiomas <InfoIcon text="El audio/idiomas no se pueden comparar de forma fiable: suelen indicarse en la descripción del torrent." /></span></th>
                      <th>Tamaño</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="pet-negrita pet-nowrap">Petición</td>
                      <td className="pet-nombre" {...reqNameTip.triggerProps}>
                        <ValueChip>
                          <ValueIcon><LibraryButtonIcon /></ValueIcon>
                          <span className="txt">{m.content_name || '—'}</span>
                        </ValueChip>
                        {reqNameTip.tooltipNode}
                      </td>
                      <td className="pet-nowrap"><SpecValueChip value={item.requested_resolution} icon={ResolutionValueIcon} /></td>
                      <td className="pet-nowrap"><SpecValueChip value={item.requested_source} icon={SourceValueIcon} /></td>
                      <td className="pet-muted">—</td>
                      <td className="pet-muted">—</td>
                      <td className="pet-muted">—</td>
                      <td className="pet-muted">—</td>
                    </tr>
                    <tr className="pet-fila-lib">
                      <td className="pet-negrita pet-nowrap">Tu biblioteca</td>
                      <td className="pet-nombre" {...libNameTip.triggerProps}>
                        {libId
                          ? (
                            <ValueChip as="button" linkable onClick={() => libraryTargetId && onOpenLibraryItem?.(libraryTargetId)} title="Ver ficha del contenido">
                              <ValueIcon><LibraryButtonIcon /></ValueIcon>
                              <span className="txt">{m.content_name || baseName(m.local_path) || m.library_title || '—'}</span>
                            </ValueChip>
                          )
                          : (
                            <ValueChip>
                              <ValueIcon><LibraryButtonIcon /></ValueIcon>
                              <span className="txt">{m.content_name || baseName(m.local_path) || m.library_title || '—'}</span>
                            </ValueChip>
                          )}
                        {libNameTip.tooltipNode}
                      </td>
                      <td className="pet-nowrap"><TechChip icon={ResolutionValueIcon} value={m.local_resolution} />{cellMark(satisfies(item.requested_resolution, m.local_resolution, m.resolution_match))}</td>
                      <td className="pet-nowrap"><TechChip icon={SourceValueIcon} value={m.local_source} />{cellMark(satisfies(item.requested_source, m.local_source, m.source_match))}</td>
                      <td className="pet-nowrap">
                        {m.local_release_groups?.length
                          ? <GruposDeRelease grupos={m.local_release_groups} junto />
                          : <span className="detcard-atenuado">—</span>}
                      </td>
                      <td className="pet-nowrap"><TechChip icon={VideoCodecValueIcon} value={m.local_video_codec} /></td>
                      <td className="pet-nowrap"><TechChip icon={LanguageValueIcon} value={m.local_audio_languages} /></td>
                      <td className="pet-nowrap"><TechChip icon={SizeValueIcon} value={m.local_size ? formatBytes(m.local_size) : null} /></td>
                    </tr>
                  </tbody>
                </table>
                {/* The library row's specs come from a file that isn't on
                    disk, so there is nothing real to compare against. Without
                    saying so, the table reads as a contradiction. */}
                {m.local_status === 'Faltante' && (
                  <p className="pet-aviso">
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
        <details className="cmp-readiness pet-preparacion">
          <summary>Preparación de subida (avanzado)</summary>
          <div className="pet-mt-8">
            <div className="detail-row"><span>Estado</span><ReadinessBadge status={readiness.status} /></div>
            <div className="detail-row"><span>Acción</span><span className="pet-accion">{readiness.recommended_action ? getReadinessActionLabel(readiness.recommended_action) : '—'}</span></div>
            <div className="detail-row"><span>Compat. score</span><span>{readiness.compatibility_score?.toFixed(0) ?? '—'}/100</span></div>
            <div className="detail-row"><span>Readiness score</span><span>{readiness.upload_readiness_score?.toFixed(0) ?? '—'}/100</span></div>
            {readiness.blockers.length > 0 && (
              <div className="pet-mt-8">
                <div className="pet-bloq-titulo">Bloqueadores</div>
                {readiness.blockers.map((b, i) => (
                  <div key={i} className="pet-bloq"><IconoBloqueado /> {b}</div>
                ))}
              </div>
            )}
            <div className="pet-mt-8">
              <button className="btn btn-ghost btn-sm" onClick={onShowCandidates}>Ver candidatos</button>
            </div>
          </div>
        </details>
      )}
    </div>
  )
}

const CLAVE_GRUPOS_PLEGADOS = 'emuwarez_pet_grupos_plegados'
const PAGE_SIZE = 2000  // show everything in one scrollable container (like Biblioteca)
const NINGUNO: string[] = []

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
  // Cuántas hay sin filtro: con un filtro puesto el subtítulo dice «3 de 141», también con 0 resultados.
  const [totalSinFiltro, setTotalSinFiltro] = useState<number | null>(null)
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
  // Las columnas admiten varios valores, como en Biblioteca: lista vacía = sin filtro.
  const [statusFilter, setStatusFilter] = useState<string[]>(NINGUNO)
  const [categoryFilter, setCategoryFilter] = useState<string[]>(NINGUNO)
  const [resolutionFilter, setResolutionFilter] = useState<string[]>(NINGUNO)
  const [sourceFilter, setSourceFilter] = useState<string[]>(NINGUNO)
  const [authorFilter, setAuthorFilter] = useState<string[]>(NINGUNO)
  const [instanceFilter, setInstanceFilter] = useState<string[]>(NINGUNO)
  const [sortBy, setSortBy] = useState(ORDEN_POR_GRUPOS)
  const [facets, setFacets] = useState<{
    categories: string[]; resolutions: string[]; sources: string[]; authors: string[]; statuses: string[]
    instances: { value: string; label: string }[]
  }>({
    categories: [], resolutions: [], sources: [], authors: [], statuses: [], instances: [],
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Requests sync is global (shared with the Dashboard's "Peticiones" button
  // and the progress banner), so it can't be launched twice across tabs.
  const { requestsSyncing, requestsStatus, startRequestsSync, lastInvalidatedAt, isAnySyncing } = useSync()

  // Solo para el enlace de la columna Origen, igual que en Subidas: el nombre
  // de la instancia ya viene en cada petición, pero su URL no.
  const instances = useInstancias()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<RequestDetailResponse | null>(null)
  const [readiness, setReadiness] = useState<RequestReadinessResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [showCandidates, setShowCandidates] = useState(false)
  const [wizardItem, setWizardItem] = useState<LibraryItemResponse | null>(null)
  const [wizardPreselect, setWizardPreselect] = useState<{ season?: number | null; episode?: number | null } | undefined>(undefined)
  const [wizardRequestId, setWizardRequestId] = useState<number | undefined>(undefined)
  // «Subir seleccionadas»: el botón «Seleccionar» pone casillas en las peticiones que se pueden subir (las mismas que
  // «Listo para subir» del Panel). Lo marcado sobrevive a filtrar y ordenar, y se limpia al salir de Peticiones y al
  // encolar el lote.
  const [modoSeleccion, setModoSeleccion] = useState(false)
  const {
    seleccion, total: totalSeleccion, lleno: loteLleno, alternar: alternarLote, limpiar: limpiarLote,
    vigente: seleccionVigente,
  } = useSeleccionLote<RequestItemResponse>()
  const [loteAbierto, setLoteAbierto] = useState<EntradaLote[] | null>(null)
  // Si ya se están pidiendo las fichas del lote, y por qué no se pudo abrir alguna.
  const abriendoLote = useRef(false)
  const [errorLote, setErrorLote] = useState<string | null>(null)
  // Cada salida de Peticiones lo sube: un «Subir seleccionadas» que aún esperaba sus fichas no abre el lote al volver.
  const salidas = useRef(0)
  const alternarModoSeleccion = () => {
    if (modoSeleccion) limpiarLote()
    setErrorLote(null)
    setModoSeleccion(m => !m)
  }
  // Los grupos plegados se recuerdan en este navegador: es una comodidad de quien mira, no un dato.
  const [plegados, setPlegados] = useState<Set<GrupoPeticion>>(() => {
    try {
      const guardado = JSON.parse(localStorage.getItem(CLAVE_GRUPOS_PLEGADOS) ?? '[]')
      return new Set(Array.isArray(guardado) ? guardado.filter((g): g is GrupoPeticion => typeof g === 'string') : [])
    } catch { return new Set() }
  })
  // El actualizador de estado debe ser puro: el siguiente conjunto se calcula aquí y se guarda aparte.
  const alternarGrupo = (id: GrupoPeticion, plegar?: boolean) => {
    const sig = new Set(plegados)
    if (plegar ?? !sig.has(id)) sig.add(id); else sig.delete(id)
    setPlegados(sig)
    try { localStorage.setItem(CLAVE_GRUPOS_PLEGADOS, JSON.stringify([...sig])) } catch { /* ignore */ }
  }
  // «Ir a»: despliega el grupo y lleva la vista a su cabecera.
  const irAlGrupo = (id: GrupoPeticion) => {
    alternarGrupo(id, false)
    requestAnimationFrame(() => document.getElementById(`pet-grupo-${id}`)?.scrollIntoView?.({ block: 'start' }))
  }
  const votesHeaderTip = useTooltip('Votos (otros usuarios que la quieren)')
  const commentsHeaderTip = useTooltip('Comentarios')

  // "Subir a eMuwarez" — reuse the exact same upload wizard as Biblioteca by
  // loading the matched library item and handing it to UploadWizardModal, with
  // the request's scope (season / episode) so the selection is pre-filled.
  const openUpload = useCallback(async (libraryItemId: number, preselect?: { season?: number | null; episode?: number | null }, requestId?: number) => {
    try {
      const libItem = await getLibraryItem(libraryItemId)
      setWizardPreselect(preselect)
      setWizardRequestId(requestId)
      setWizardItem(libItem)
    } catch { /* ignore — button only enabled when a match exists */ }
  }, [])

  const computeFacets = (list: RequestItemResponse[]) => {
    const uniq = (vals: (string | null | undefined)[]) =>
      Array.from(new Set(vals.filter((v): v is string => !!v && v.trim() !== ''))).sort()
    return {
      categories: uniq(list.map(i => i.category)),
      // Sin nada pedido la celda dice «Cualquiera», y por eso se filtra.
      resolutions: uniq(list.map(i => noReq(i.requested_resolution))),
      sources: uniq(list.map(i => noReq(i.requested_source))),
      authors: uniq(list.map(i => i.author)),
      // Null reads as "no library match", which the filter knows by name —
      // don't let uniq() drop it or that state stays unfilterable.
      statuses: uniq(list.map(i => i.compatibility_status || 'Sin coincidencia')),
      // Origen: las instancias que atienden alguna petición, con el nombre que enseña la columna.
      instances: Array.from(new Map(list.filter(i => i.instance_id != null)
        .map(i => [String(i.instance_id), i.instance_name ?? i.instance_type ?? String(i.instance_id)])))
        .map(([value, label]) => ({ value, label }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    }
  }

  // No filter active — loadItems' own response IS the full unfiltered
  // dataset, so it can double as the facets source (see loadItems below)
  // instead of loadFacets firing a second, identical request for it.
  const isUnfiltered = !debouncedSearch && [statusFilter, categoryFilter, resolutionFilter, sourceFilter, authorFilter, instanceFilter]
    .every(f => f.length === 0)

  // Solo cuenta la última petición: marcar varias casillas seguidas lanza
  // varias, y una vieja más lenta no pisa la nueva (igual que en Biblioteca).
  const ultimaCarga = useRef(0)
  const loadItems = useCallback(async (off = 0) => {
    const esta = ++ultimaCarga.current
    setLoading(true)
    setError(null)
    try {
      const res = await getRequests({
        search: debouncedSearch || undefined,
        status: statusFilter,
        category: categoryFilter,
        resolution: resolutionFilter,
        source: sourceFilter,
        author: authorFilter,
        instance_id: instanceFilter.map(Number),
        sort: sortBy === ORDEN_POR_GRUPOS ? 'points_desc' : sortBy,
        limit: PAGE_SIZE,
        offset: off,
      })
      if (esta !== ultimaCarga.current) return
      setItems(res.items)
      setTotal(res.total)
      setOffset(off)
      if (isUnfiltered && off === 0) {
        setFacets(computeFacets(res.items))
        setTotalSinFiltro(res.total)
      }
    } catch (e: unknown) {
      if (esta === ultimaCarga.current) setError(e instanceof Error ? e.message : 'Error cargando peticiones')
    } finally {
      if (esta === ultimaCarga.current) setLoading(false)
    }
  }, [debouncedSearch, statusFilter, categoryFilter, resolutionFilter, sourceFilter, authorFilter, instanceFilter, sortBy, isUnfiltered])

  // Populate filter dropdown options from the full (unfiltered) dataset so they
  // stay stable regardless of the active filters. Only needed when a filter
  // IS currently active — otherwise loadItems' own unfiltered response
  // already covers it (see isUnfiltered above), and calling this too would
  // just fire the exact same request twice.
  const loadFacets = useCallback(async () => {
    try {
      const res = await getRequests({ sort: 'created_desc', limit: PAGE_SIZE, offset: 0 })
      setFacets(computeFacets(res.items))
      setTotalSinFiltro(res.total)
    } catch { /* optional */ }
  }, [])

  // Reload the table whenever a filter, the search box (debounced), or the
  // sort order changes. On mount this IS the unfiltered load (all filters
  // start empty), so there's no separate loadFacets() call needed here.
  useEffect(() => {
    loadItems(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al cambiar un filtro o el orden
  }, [debouncedSearch, statusFilter, categoryFilter, resolutionFilter, sourceFilter, authorFilter, instanceFilter, sortBy])

  // Reload table + facets whenever what's loaded stops being valid: a global
  // sync finishing (peticiones u otra), or coming back to the tab.
  useEffect(() => {
    if (lastInvalidatedAt) {
      loadItems(0)
      if (!isUnfiltered) loadFacets()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo cuando algo invalida la lista
  }, [lastInvalidatedAt])

  // Keeps /requests/:id in sync with whichever request's detail is open.
  // Solo vale el detalle de la última petición abierta: la campana puede abrir dos seguidas, y la primera,
  // si llega la última, dejaba su ficha bajo el id de la segunda.
  const ultimoDetalle = useRef(0)
  const closeRequestDetail = () => {
    ultimoDetalle.current++
    closeDetailPath('requests')
    setSelectedId(null)
    setDetail(null)
    setReadiness(null)
    setDetailLoading(false)
    setShowCandidates(false)
  }

  const openRequestDetail = async (id: number) => {
    const esta = ++ultimoDetalle.current
    pushDetailPath('requests', id)
    setSelectedId(id)
    setShowCandidates(false)
    setDetailLoading(true)
    try {
      const [d, rr] = await Promise.allSettled([
        getRequestDetail(id),
        getReadiness(id).catch(() => null),
      ])
      if (esta !== ultimoDetalle.current) return
      setDetail(d.status === 'fulfilled' ? d.value : null)
      setReadiness(rr.status === 'fulfilled' && rr.value !== null ? rr.value as RequestReadinessResponse : null)
    } catch { if (esta === ultimoDetalle.current) setDetail(null) }
    finally { if (esta === ultimoDetalle.current) setDetailLoading(false) }
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
    setStatusFilter(NINGUNO); setCategoryFilter(NINGUNO); setResolutionFilter(NINGUNO)
    setSourceFilter(NINGUNO); setAuthorFilter(NINGUNO); setInstanceFilter(NINGUNO)
    setOffset(0)
  }
  // Al salir, de vuelta a la tabla sin filtros, con el orden por defecto y sin nada marcado.
  useAlSalir(() => {
    closeRequestDetail()
    quitarFiltros()
    setSortBy(ORDEN_POR_GRUPOS)
    salidas.current++
    limpiarLote()
    setModoSeleccion(false)
    setLoteAbierto(null)
    setErrorLote(null)
  })

  // «Subir seleccionadas»: la fila a la que se refiere cada petición, la misma que abre su «Subir a eMuwarez» (la
  // temporada o el capítulo pedidos, `match.library_target_id`, que la lista no trae: sin temporada pedida es la fila
  // que cruzó), y el modal de «Subir por lotes» con la petición y su alcance. Las que ya no están se dicen y el resto
  // sigue.
  const subirSeleccionadas = async () => {
    if (abriendoLote.current) return
    abriendoLote.current = true
    setErrorLote(null)
    try {
      const fichas = new Map<number, Promise<LibraryItemResponse>>()
      const fichaDe = (id: number) => {
        if (!fichas.has(id)) fichas.set(id, getLibraryItem(id))
        return fichas.get(id)!
      }
      const filaDe = async (p: RequestItemResponse): Promise<LibraryItemResponse> => {
        if (p.req_season == null) return fichaDe(p.library_item_id!)
        const d = await getRequestDetail(p.id)
        return fichaDe(d.match?.library_target_id ?? d.match?.library_item_id ?? p.library_item_id!)
      }
      const salidasAntes = salidas.current
      // Si lo marcado cambia mientras se piden las fichas, se prepara otra vez con lo de ahora (las fichas ya pedidas
      // no se repiten); salir de la página lo deja.
      let marcadas = seleccionVigente()
      let peticiones: RequestItemResponse[]
      let resultados: PromiseSettledResult<LibraryItemResponse>[]
      for (;;) {
        peticiones = [...marcadas.values()]
        resultados = await Promise.allSettled(peticiones.map(filaDe))
        if (salidas.current !== salidasAntes) return
        const ahora = seleccionVigente()
        if (ahora === marcadas) break
        marcadas = ahora
      }
      const entradas: EntradaLote[] = []
      const perdidas: string[] = []
      resultados.forEach((r, i) => {
        if (r.status === 'fulfilled') entradas.push(entradaDePeticion(peticiones[i], r.value))
        else perdidas.push(`«${requestDisplayTitle(peticiones[i])}»`)
      })
      if (perdidas.length > 0) {
        setErrorLote(perdidas.length === 1
          ? `No se pudo abrir ${perdidas[0]}: puede que ya no esté en la biblioteca tras la última sincronización.`
          : `No se pudieron abrir ${perdidas.join(', ')}: puede que ya no estén en la biblioteca tras la última sincronización.`)
      }
      if (entradas.length > 0) setLoteAbierto(entradas)
    } finally {
      abriendoLote.current = false
    }
  }

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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- un solo oyente; handleRowClick se recrea en cada pintado
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
  }, [])

  const displayItems = items
  const agrupada = sortBy === ORDEN_POR_GRUPOS
  const gruposVisibles = agrupada ? agruparPeticiones(displayItems) : []
  // Las peticiones reales no traen votos ni comentarios: sin dato, sin columna.
  const hayVotos = displayItems.some(i => i.votes != null)
  const hayComentarios = displayItems.some(i => i.comments != null)

  const columnas = 9 + Number(hayVotos) + Number(hayComentarios)
  // «Seleccionar» solo sale si hay algo que marcar (o el modo ya está puesto). Lo marcado que el filtro de ahora no
  // enseña se cuenta aparte en la barra.
  const haySeleccionables = displayItems.some(peticionSeleccionableEnLote)
  const idsALaVista = modoSeleccion ? new Set(displayItems.map(i => i.id)) : null
  const ocultasPorFiltro = idsALaVista ? [...seleccion.keys()].filter(id => !idsALaVista.has(id)).length : 0
  const fila = (item: RequestItemResponse) => (
    <tr
      key={item.id}
      onClick={() => handleRowClick(item.id)}
      className={selectedId === item.id ? 'clickable row-selected' : 'clickable'}
    >
      <td>
        <div className="pet-titulo-fila">
          {/* La casilla va dentro de la celda Título, no en una columna nueva: `columnas` cuenta las de la tabla. */}
          {modoSeleccion && (peticionSeleccionableEnLote(item) ? (
            <CasillaLote
              item={item} titulo={requestDisplayTitle(item)} seleccionado={seleccion.has(item.id)}
              bloqueada={loteLleno} onAlternar={alternarLote}
            />
          ) : (
            // El hueco de la casilla, para que los títulos sigan alineados: esta no se puede subir en lote.
            <span className="pet-casilla-hueco" aria-hidden="true" />
          ))}
          <RequestPoster url={item.poster_url} category={item.category} />
          <div className="pet-min-0">
            <HoverTitle
              className="lib-title-link"
              onClick={e => { e.stopPropagation(); handleRowClick(item.id) }}
              tip="Abrir ficha"
            >
              <DetailTitleText title={requestDisplayTitle(item)} />
            </HoverTitle>
          </div>
        </div>
      </td>
      <td className="pet-nowrap pet-tipo">
        <PlainValue icon={<TypeValueIcon />}>{tipoOf(item.category).label}</PlainValue>
      </td>
      <td className="pet-nowrap pet-sec"><OriginCell item={item} instances={instances} alwaysChip={false} /></td>
      <td>
        <CompatibilityBadge status={item.compatibility_status} reclamada={item.reclamada_por} />
        {motivoDeLaPreparacion(item) && <div className="pet-motivo">{motivoDeLaPreparacion(item)}</div>}
      </td>
      <td className="pet-t12 pet-nowrap pet-sec"><AuthorCell author={item.author} isMine={item.is_mine} /></td>
      <td className="pet-nowrap pet-sec"><SpecPlainValue value={item.requested_resolution} icon={ResolutionValueIcon} /></td>
      <td className="pet-nowrap pet-sec"><SpecPlainValue value={item.requested_source} icon={SourceValueIcon} /></td>
      {hayVotos && <td className="pet-centro pet-t12 pet-sec">{item.votes ?? '—'}</td>}
      {hayComentarios && <td className="pet-centro pet-t12 pet-sec">{item.comments ?? '—'}</td>}
      <td className="pet-puntos">{item.points != null ? <><IconoPuntos />{fmtNum(item.points)}</> : <span className="pet-muted">—</span>}</td>
      <CreatedAtCell createdAt={item.created_at} />
    </tr>
  )

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div data-tour="requests-content" className="pet-pagina">
      {selectedId !== null ? (
        (detailLoading || !detail) ? (
          <div className="pet-cargando"><LoadingState label="Cargando petición…" /></div>
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
              {!isUnfiltered && totalSinFiltro != null
                ? `${total} de ${totalSinFiltro} peticiones`
                : total > 0 ? `${total} peticiones` : 'Peticiones activas cruzadas con tu biblioteca local'}
            </div>
          </div>
          <div className="pet-fila">
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
            className="form-input pet-buscar"
            type="search"
            aria-label="Buscar peticiones por título"
            autoComplete="off"
            placeholder="Buscar por título…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadItems(0)}
          />
          <select className="form-input form-select" aria-label="Ordenar peticiones" value={sortBy} onChange={e => setSortBy(e.target.value)}>
            {SORT_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          {(haySeleccionables || modoSeleccion) && (
            <Tooltip content="Marca varias peticiones listas para subirlas de una vez">
              <button
                type="button"
                className={`btn btn-secondary btn-sm${modoSeleccion ? ' lote-boton-activo' : ''}`}
                onClick={alternarModoSeleccion}
                aria-pressed={modoSeleccion}
              >
                Seleccionar
              </button>
            </Tooltip>
          )}
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
          <>
          {agrupada && gruposVisibles.length > 0 && (
          <nav className="pet-resumen" aria-label="Grupos de peticiones">
            {gruposVisibles.map(g => (
              <button key={g.id} type="button" className={`pet-resumen-chip pet-resumen-${g.id}`} onClick={() => irAlGrupo(g.id)}>
                <span className="pet-punto" aria-hidden="true" />
                {g.titulo}
                <span className="pet-resumen-n">{g.items.length}</span>
              </button>
            ))}
          </nav>
        )}

          <div className="activity-section pet-seccion">
            <div className="pet-scroll">
              <table className="data-table pet-tabla">
                <thead>
                  <tr>
                    <th>Título</th>
                    <th className="pet-tipo"><HeaderFilter label="Tipo" value={categoryFilter} onChange={setCategoryFilter} options={[
                      // Same label the Tipo column shows, or the filter would
                      // offer "TV" for a column that says "Serie".
                      { value: '', label: 'Todos' }, ...facets.categories.map(c => ({ value: c, label: tipoOf(c).label })),
                    ]} /></th>
                    <th className="pet-sec"><HeaderFilter label="Origen" value={instanceFilter} onChange={setInstanceFilter} options={[
                      { value: '', label: 'Todos' }, ...facets.instances,
                    ]} /></th>
                    <th><HeaderFilter label="Compatibilidad" value={statusFilter} onChange={setStatusFilter} options={[
                      // Labels, not raw values, or the filter would offer
                      // "No disponible" for a column that says "Faltante".
                      { value: '', label: 'Todas' }, ...facets.statuses.map(s => ({ value: s, label: getRequestStatusInfo(s).label })),
                    ]} /></th>
                    <th className="pet-sec"><HeaderFilter label="Autor" value={authorFilter} onChange={setAuthorFilter} options={[
                      { value: '', label: 'Todos' }, ...facets.authors.map(a => ({ value: a, label: a })),
                    ]} /></th>
                    <th className="pet-sec"><HeaderFilter label="Resolución" value={resolutionFilter} onChange={setResolutionFilter} options={[
                      { value: '', label: 'Todas' }, ...facets.resolutions.map(r => ({ value: r, label: r })),
                    ]} /></th>
                    <th className="pet-sec"><HeaderFilter label="Source" value={sourceFilter} onChange={setSourceFilter} options={[
                      { value: '', label: 'Todos' }, ...facets.sources.map(s => ({ value: s, label: s })),
                    ]} /></th>
                    {hayVotos && <th className="pet-centro pet-sec" {...votesHeaderTip.triggerProps}><VotesIcon />{votesHeaderTip.tooltipNode}</th>}
                    {hayComentarios && <th className="pet-centro pet-sec" {...commentsHeaderTip.triggerProps}><CommentsIcon />{commentsHeaderTip.tooltipNode}</th>}
                    <HeaderSort label={<IconoPuntos />} nombre="Puntos / recompensa" desc="points_desc" asc="points_asc" sortBy={sortBy} onSort={setSortBy} align="center" />
                    <HeaderSort label="Creada" desc="created_desc" asc="created_asc" sortBy={sortBy} onSort={setSortBy} />
                  </tr>
                </thead>
                {displayItems.length === 0 && (
                  <FilaVacia
                    columnas={columnas}
                    title="Sin peticiones"
                    body="No hay peticiones que coincidan con los filtros."
                    action={<button className="btn btn-primary btn-sm" onClick={quitarFiltros}>Quitar filtros</button>}
                  />
                )}
                {agrupada ? gruposVisibles.map(g => {
                  const plegado = plegados.has(g.id)
                  return (
                    <tbody key={g.id} className={`pet-bloque pet-bloque-${g.id}`}>
                      <tr className="pet-grupo-cab" id={`pet-grupo-${g.id}`}>
                        <th scope="rowgroup" colSpan={columnas} className="pet-grupo-th">
                          <button type="button" className="pet-grupo-boton" aria-expanded={!plegado} onClick={() => alternarGrupo(g.id)}>
                            <IconoDesplegar abierto={!plegado} size={12} />
                            <span className="pet-grupo-titulo">{g.titulo}</span>
                            <span className="pet-grupo-n">{g.items.length}</span>
                            <span className="pet-grupo-ayuda">{g.ayuda}</span>
                          </button>
                        </th>
                      </tr>
                      {!plegado && g.items.map(fila)}
                    </tbody>
                  )
                }) : (
                  <tbody>
                    {displayItems.map(fila)}
                  </tbody>
                )}
              </table>
            </div>

            {totalPages > 1 && (
              <div className="pagination pet-paginacion">
                <button className="btn btn-secondary btn-sm" disabled={offset === 0} onClick={() => loadItems(offset - PAGE_SIZE)}>Anterior</button>
                <span className="pet-paginacion-n">{currentPage} / {totalPages}</span>
                <button className="btn btn-secondary btn-sm" disabled={offset + PAGE_SIZE >= total} onClick={() => loadItems(offset + PAGE_SIZE)}>Siguiente</button>
              </div>
            )}
          </div>
          </>
        )}

        {modoSeleccion && (
          <>
            {errorLote && <div className="pet-error-lote" role="alert">{errorLote}</div>}
            <BarraLote
              total={totalSeleccion}
              ocultas={ocultasPorFiltro}
              vacia="Marca las peticiones listas que quieras subir juntas"
              textoSubir={`Subir seleccionadas (${totalSeleccion})`}
              onSubir={subirSeleccionadas}
              onLimpiar={limpiarLote}
            />
          </>
        )}
      </>
      )}

      {showCandidates && selectedId !== null && (
        <Modal titulo="Candidatos locales" onClose={() => setShowCandidates(false)} className="pet-modal-candidatos">
          <CandidatesPanel requestId={selectedId} />
        </Modal>
      )}

      {wizardItem && (
        <UploadWizardModal
          item={wizardItem}
          preselect={wizardPreselect}
          requestId={wizardRequestId}
          onClose={() => setWizardItem(null)}
          onDone={() => { setWizardItem(null); loadItems(offset) }}
          onNavigate={onNavigate}
        />
      )}

      {loteAbierto && (
        <SubidaPorLotesModal
          entradas={loteAbierto}
          onClose={() => setLoteAbierto(null)}
          onDone={() => { limpiarLote(); setModoSeleccion(false); loadItems(offset) }}
          onNavigate={onNavigate}
        />
      )}
    </div>
  )
}
