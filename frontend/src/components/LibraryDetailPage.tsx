import { useState, useEffect } from 'react'
import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { getLibraryItem } from '../api/library'
import { StatusBadge } from './StatusBadge'
import { LibraryChildrenSection } from './LibraryChildrenSection'
import { EmuComparisonSection } from './EmuComparisonSection'
import { LibraryActionButtons } from './LibraryActionButtons'
import type { LibraryActionKind } from './LibraryTreeRow'
import { formatBytes, formatItemType } from '../utils/format'
import { buildDeepLink, posterUrl, idVerifyUrl } from '../utils/libraryItem'
import { ExternalIdLink } from './ExternalIdLink'
import { ProviderTag } from './ProviderIcon'
import { NomenclatureCheckButton } from './NomenclatureCheckButton'

// Full dedicated detail page (Radarr/Sonarr-style) — replaces the old small
// modal and the large card. Rendered in place of the library list, with a
// back button, a large poster and all the item's fields.
function Field({ label, children, wide, help }: { label: string; children: React.ReactNode; wide?: boolean; help?: string }) {
  return (
    <div style={wide ? { gridColumn: '1 / -1' } : undefined}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 3, display: 'flex', alignItems: 'center', gap: 5 }}>
        {label}
        {help && (
          <span
            title={help}
            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 13, height: 13, borderRadius: '50%', border: '1px solid var(--text-muted)', fontSize: 9, cursor: 'help', flexShrink: 0 }}
          >
            ?
          </span>
        )}
      </div>
      <div style={{ fontSize: 14, wordBreak: 'break-all' }}>{children}</div>
    </div>
  )
}

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
    <div style={{ width: '100%' }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← Volver a la biblioteca</button>
        {parentSeason && (
          <button className="btn btn-ghost btn-sm" onClick={() => onSelect(parentSeason)}>← Volver a la temporada</button>
        )}
        {parentSeries && (
          <button className="btn btn-ghost btn-sm" onClick={() => onSelect(parentSeries)}>← Volver a la serie</button>
        )}
      </div>

      <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap' }}>
        <div style={{ flexShrink: 0, width: 300, maxWidth: '100%' }}>
          <div style={{ width: '100%', aspectRatio: '2 / 3', borderRadius: 12, overflow: 'hidden', background: 'rgba(255,255,255,0.04)' }}>
            {item.poster_url ? (
              <img
                src={posterUrl(item.poster_url, 'w500')}
                alt={item.title}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
              />
            ) : (
              <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 88, opacity: 0.35 }}>
                {item.item_type === 'series' || item.item_type === 'episode' ? '📺' : '🎬'}
              </div>
            )}
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 300 }}>
          <div style={{ fontWeight: 700, fontSize: 28, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            {item.title} {item.year ? <span style={{ color: 'var(--text-muted)', fontWeight: 500 }}>({item.year})</span> : null}
            {deepLink && (
              <a href={deepLink} target="_blank" rel="noreferrer" title={`Ver en ${item.instance_name ?? item.instance_type}`} style={{ fontSize: 18, textDecoration: 'none' }}>🔗</a>
            )}
          </div>

          <div style={{ display: 'flex', gap: 8, margin: '20px 0', flexWrap: 'wrap' }}>
            <LibraryActionButtons item={item} onAction={onAction} title={isRollup ? 'Ver season pack' : undefined} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '16px 28px' }}>
            <Field label="Tipo">{formatItemType(item.item_type)}</Field>
            <Field label="Origen">{item.instance_name ?? '—'}</Field>
            <Field label="Estado"><StatusBadge status={item.local_status} type="local" /></Field>
            <Field label="Petición"><StatusBadge status={item.request_status} type="request" /></Field>
            <Field label="Nomenclatura">
              <NomenclatureCheckButton
                item={item}
                onChecked={async () => {
                  const updated = await getLibraryItem(item.id).catch(() => null)
                  if (updated) onSelect(updated)
                }}
              />
            </Field>
            <Field label="Resolución" help={rollupHelp}>{item.resolution || '–'}</Field>
            <Field label="Source" help={rollupHelp}>{item.source || '–'}</Field>
            <Field label="Provider" help={rollupHelp}>{item.provider ? <ProviderTag code={item.provider} label={item.provider_label} /> : '–'}</Field>
            <Field label="Códec de vídeo" help={rollupHelp}>{item.video_codec || '–'}</Field>
            <Field label="Códec de audio" help={rollupHelp}>{item.audio_codec || '–'}</Field>
            <Field label="Idiomas de audio" help={rollupHelp}>{item.audio_languages || '–'}</Field>
            <Field label="Subtítulos" help={rollupHelp}>{item.subtitle_languages || '–'}</Field>
            <Field label="Tamaño">{formatBytes(item.size_bytes)}</Field>
            {item.tmdb_id && <Field label="TMDb"><ExternalIdLink id={item.tmdb_id} href={idVerifyUrl('tmdb', item.tmdb_id, isTv)} label="TMDb" /></Field>}
            {item.imdb_id && <Field label="IMDb"><ExternalIdLink id={item.imdb_id} href={idVerifyUrl('imdb', item.imdb_id, isTv)} label="IMDb" /></Field>}
            {item.tvdb_id && <Field label="TVDB"><ExternalIdLink id={item.tvdb_id} href={idVerifyUrl('tvdb', item.tvdb_id, isTv)} label="TVDB" /></Field>}
            <Field label="Ruta" wide>{item.path ?? '—'}</Field>
          </div>
        </div>
      </div>

      {(item.item_type === 'movie' || item.item_type === 'season' || item.item_type === 'episode') && (
        <EmuComparisonSection itemId={item.id} />
      )}

      {item.item_type === 'series' && (
        <LibraryChildrenSection parentId={item.id} childType="season" title="Temporadas" instances={instances} onSelect={onSelect} onAction={onAction} />
      )}

      {item.item_type === 'season' && (
        <LibraryChildrenSection parentId={item.id} childType="episode" title="Capítulos" instances={instances} onSelect={onSelect} onAction={onAction} />
      )}
    </div>
  )
}
