import { useState, useEffect } from 'react'
import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { getLibraryItem } from '../api/library'
import { StatusBadge } from './StatusBadge'
import { LibraryChildrenSection } from './LibraryChildrenSection'
import { EmuFieldChip } from './EmuComparisonSection'
import { LibraryActionButtons } from './LibraryActionButtons'
import type { LibraryActionKind } from './LibraryTreeRow'
import { formatBytes, formatDate, formatItemType } from '../utils/format'
import { buildDeepLink, posterUrl, idVerifyUrl } from '../utils/libraryItem'
import { ExternalIdLink } from './ExternalIdLink'
import { ProviderTag } from './ProviderIcon'
import { ServiceLabel } from './ServiceIcon'
import { useTooltip } from './Tooltip'
import {
  Card, FieldRow, DetailPoster, ValueChip, ValueIcon, DETAIL_CARD_HEIGHT, DetailHero, DetailTitle, DetailTitleText,
  StatusCardIcon, TechInfoCardIcon, ExternalIdsCardIcon,
  TypeValueIcon, ResolutionValueIcon, SourceValueIcon, VideoCodecValueIcon,
  AudioCodecValueIcon, LanguageValueIcon, SubtitleValueIcon, SizeValueIcon,
  FolderIcon, CalendarValueIcon,
} from './DetailCard'

// Full dedicated detail page (Radarr/Sonarr-style) — replaces the old small
// modal and the large card. Rendered in place of the library list, with a
// back button, a compact header (title + actions, fixed-size poster) and the
// item's fields grouped into semantic cards instead of one long grid.

export function LibraryDetailPage({ item, instances, onBack, onSelect, onAction }: {
  item: LibraryItemResponse
  instances: InstanceSafeResponse[]
  onBack: () => void
  onSelect: (item: LibraryItemResponse) => void
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
}) {
  const deepLink = buildDeepLink(item, instances)
  const isRollup = item.item_type === 'series' || item.item_type === 'season'
  const isTv = item.item_type !== 'movie'
  // Same restriction the old standalone "Comparación con eMuwarez" section
  // used: series is a rollup (drill into seasons instead), episodes roll
  // into their season — only movie/season/episode have a real comparison.
  const isEmuComparable = item.item_type === 'movie' || item.item_type === 'season' || item.item_type === 'episode'
  // Consolidated fields (quality, provider, codecs, audio, subs) only appear on
  // a rollup when every child shares the value — the "?" explains that.
  const rollupHelp = item.item_type === 'series'
    ? 'Todas las temporadas deben tener el mismo valor para que se muestre aquí.'
    : item.item_type === 'season'
    ? 'Todos los capítulos deben tener el mismo valor para que se muestre aquí.'
    : undefined

  // Ancestor navigation: a season can go up to its series; an episode can go up
  // to its season and to its series. We only have parent_id, so fetch the chain
  // (episode -> season -> series) and offer a "back to …" button per ancestor.
  const [parentSeason, setParentSeason] = useState<LibraryItemResponse | null>(null)
  const [parentSeries, setParentSeries] = useState<LibraryItemResponse | null>(null)
  const [showRuta, setShowRuta] = useState(false)
  const originTip = useTooltip(deepLink ? `Abrir en ${item.instance_name ?? item.instance_type}` : null)

  useEffect(() => {
    let alive = true
    setParentSeason(null)
    setParentSeries(null)
    async function loadAncestors() {
      if (item.item_type === 'season' && item.parent_id != null) {
        const series = await getLibraryItem(item.parent_id).catch(() => null)
        if (alive && series) setParentSeries(series)
      } else if (item.item_type === 'episode' && item.parent_id != null) {
        const season = await getLibraryItem(item.parent_id).catch(() => null)
        if (alive && season) {
          setParentSeason(season)
          if (season.parent_id != null) {
            const series = await getLibraryItem(season.parent_id).catch(() => null)
            if (alive && series) setParentSeries(series)
          }
        }
      }
    }
    loadAncestors()
    return () => { alive = false }
  }, [item.id, item.item_type, item.parent_id])

  return (
    <div style={{ width: '100%', height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ flexShrink: 0 }}>
      <DetailHero backdropUrl={item.backdrop_url}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-ghost btn-sm" onClick={onBack}>← Volver a la biblioteca</button>
          {parentSeason && (
            <button className="btn btn-ghost btn-sm" onClick={() => onSelect(parentSeason)}>← Volver a la temporada</button>
          )}
          {parentSeries && (
            <button className="btn btn-ghost btn-sm" onClick={() => onSelect(parentSeries)}>← Volver a la serie</button>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0, flexWrap: 'wrap' }}>
          <LibraryActionButtons
            item={item}
            onAction={onAction}
            title={isRollup ? 'Ver season pack' : undefined}
           
          />
        </div>
      </div>

      <div style={{ marginBottom: 20 }}>
        <DetailTitle><DetailTitleText title={item.display_title || item.title} /></DetailTitle>
      </div>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <DetailPoster
          url={item.poster_url ? posterUrl(item.poster_url, 'w500') : null}
          alt={item.title}
          fallbackEmoji={item.item_type === 'series' || item.item_type === 'episode' ? '📺' : '🎬'}
        />

        <div style={{ flex: 1, minWidth: 300 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16, minHeight: DETAIL_CARD_HEIGHT }}>
            <Card title="Estado de la biblioteca" icon={<StatusCardIcon />}>
              <FieldRow label="Tipo">
                <ValueChip><ValueIcon><TypeValueIcon /></ValueIcon><span className="txt">{formatItemType(item.item_type)}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Origen">
                {item.instance_type
                  ? (
                    <ValueChip linkable>
                      {deepLink
                        ? <a className="hover-link" href={deepLink} target="_blank" rel="noreferrer" {...originTip.triggerProps}><ServiceLabel type={item.instance_type} label={item.instance_name ?? item.instance_type} size={15} />{originTip.tooltipNode}</a>
                        : <ServiceLabel type={item.instance_type} label={item.instance_name ?? item.instance_type} size={15} />}
                    </ValueChip>
                  )
                  : <span className="muted">–</span>}
              </FieldRow>
              <FieldRow label="Estado"><StatusBadge status={item.local_status} type="local" /></FieldRow>
              <FieldRow label="Petición"><StatusBadge status={item.request_status} type="request" /></FieldRow>
              {isEmuComparable && (
                <FieldRow label="eMuwarez">
                  <EmuFieldChip itemId={item.id} />
                </FieldRow>
              )}
              <FieldRow label="Ruta">
                <ValueChip as="button" linkable onClick={() => setShowRuta(true)} title="Ver ruta completa">
                  <span className="brand-icon"><FolderIcon /></span><span className="txt">Ver ruta</span>
                </ValueChip>
              </FieldRow>
              <FieldRow label="Actualizado">
                <ValueChip><ValueIcon><CalendarValueIcon /></ValueIcon><span className="txt">{formatDate(item.updated_at)}</span></ValueChip>
              </FieldRow>
            </Card>

            {/* En una serie o temporada, el valor de la fila solo está
                relleno cuando TODOS los capítulos coinciden: es la señal que
                usa la regla del pack. Para enseñar es pobre (una temporada
                con x264 y x265 salía con un guion), así que la ficha usa la
                suma de lo que hay debajo: "x264, x265". */}
            <Card title="Información técnica" icon={<TechInfoCardIcon />}>
              <FieldRow label="Resolución" help={rollupHelp}>
                <ValueChip><ValueIcon><ResolutionValueIcon /></ValueIcon><span className="txt">{item.rollup_all?.resolution || item.resolution || '–'}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Proveedor" help={rollupHelp}>
                {/* Con varios proveedores bajo una temporada no hay una
                    etiqueta con logo que valga para todos, así que se listan
                    en texto igual que el resto de campos sumados. */}
                {item.rollup_all?.provider && item.rollup_all.provider.includes(',')
                  ? <ValueChip><span className="txt">{item.rollup_all.provider}</span></ValueChip>
                  : item.provider
                  ? <ValueChip linkable><ProviderTag code={item.provider} label={item.provider_label} /></ValueChip>
                  : item.rollup_all?.provider
                  ? <ValueChip><span className="txt">{item.rollup_all.provider}</span></ValueChip>
                  : <span className="muted">–</span>}
              </FieldRow>
              <FieldRow label="Source" help={rollupHelp}>
                <ValueChip><ValueIcon><SourceValueIcon /></ValueIcon><span className="txt">{item.rollup_all?.source || item.source || '–'}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Códec de vídeo" help={rollupHelp}>
                <ValueChip><ValueIcon><VideoCodecValueIcon /></ValueIcon><span className="txt">{item.rollup_all?.video_codec || item.video_codec || '–'}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Códec de audio" help={rollupHelp}>
                <ValueChip><ValueIcon><AudioCodecValueIcon /></ValueIcon><span className="txt">{item.rollup_all?.audio_codec || item.audio_codec || '–'}</span></ValueChip>
              </FieldRow>
              {/* These two are the only fields that can carry a dozen values
                  (a multi-language release), so they're the ones the card's
                  width truncates — the tooltip is where the full list stays
                  reachable. */}
              <FieldRow label="Idiomas de audio" help={rollupHelp}>
                <ValueChip title={item.rollup_all?.audio_languages || item.audio_languages || undefined}>
                  <ValueIcon><LanguageValueIcon /></ValueIcon><span className="txt">{item.rollup_all?.audio_languages || item.audio_languages || '–'}</span>
                </ValueChip>
              </FieldRow>
              <FieldRow label="Subtítulos" help={rollupHelp}>
                <ValueChip title={item.rollup_all?.subtitle_languages || item.subtitle_languages || undefined}>
                  <ValueIcon><SubtitleValueIcon /></ValueIcon><span className="txt">{item.rollup_all?.subtitle_languages || item.subtitle_languages || '–'}</span>
                </ValueChip>
              </FieldRow>
              <FieldRow label="Tamaño">
                <ValueChip><ValueIcon><SizeValueIcon /></ValueIcon><span className="txt">{formatBytes(item.size_bytes)}</span></ValueChip>
              </FieldRow>
            </Card>

            <Card title="Identificadores externos" icon={<ExternalIdsCardIcon />}>
              <FieldRow label="TMDb">
                {item.tmdb_id ? <ValueChip linkable={Boolean(idVerifyUrl('tmdb', item.tmdb_id, isTv))}><ExternalIdLink id={item.tmdb_id} href={idVerifyUrl('tmdb', item.tmdb_id, isTv)} label="TMDb" /></ValueChip> : <span className="muted">–</span>}
              </FieldRow>
              <FieldRow label="IMDb">
                {item.imdb_id ? <ValueChip linkable={Boolean(idVerifyUrl('imdb', item.imdb_id, isTv))}><ExternalIdLink id={item.imdb_id} href={idVerifyUrl('imdb', item.imdb_id, isTv)} label="IMDb" /></ValueChip> : <span className="muted">–</span>}
              </FieldRow>
              {/* Radarr no trae tvdbId para películas (TVDB es una base de series) —
                  siempre sería un "–" fijo, así que directamente no se muestra. */}
              {item.item_type !== 'movie' && (
                <FieldRow label="TVDB">
                  {item.tvdb_id ? <ValueChip linkable={Boolean(idVerifyUrl('tvdb', item.tvdb_id, isTv))}><ExternalIdLink id={item.tvdb_id} href={idVerifyUrl('tvdb', item.tvdb_id, isTv)} label="TVDB" /></ValueChip> : <span className="muted">–</span>}
                </FieldRow>
              )}
              <FieldRow label="MAL">
                {item.mal_id ? <ValueChip linkable={Boolean(idVerifyUrl('mal', item.mal_id, isTv))}><ExternalIdLink id={item.mal_id} href={idVerifyUrl('mal', item.mal_id, isTv)} label="MAL" /></ValueChip> : <span className="muted">–</span>}
              </FieldRow>
            </Card>
          </div>
        </div>
      </div>
      </DetailHero>

      {showRuta && (
        <div className="modal-overlay" onClick={() => setShowRuta(false)}>
          <div className="modal-panel" onClick={e => e.stopPropagation()} style={{ width: 'max-content', maxWidth: '90vw', minWidth: 320 }}>
            <div className="modal-header">
              <h2 className="modal-title">Ruta</h2>
              <button className="modal-close" onClick={() => setShowRuta(false)}>✕</button>
            </div>
            <div className="modal-body">
              <div style={{ fontFamily: 'monospace', fontSize: 13, color: 'var(--text-secondary)', wordBreak: 'break-all', lineHeight: 1.6 }}>{item.prepared_path || item.path || '–'}</div>
            </div>
          </div>
        </div>
      )}
      </div>

      {item.item_type === 'series' && (
        <LibraryChildrenSection parentId={item.id} childType="season" title="Temporadas" instances={instances} onSelect={onSelect} onAction={onAction} />
      )}

      {item.item_type === 'season' && (
        <LibraryChildrenSection parentId={item.id} childType="episode" title="Capítulos" instances={instances} onSelect={onSelect} onAction={onAction} />
      )}
    </div>
  )
}
