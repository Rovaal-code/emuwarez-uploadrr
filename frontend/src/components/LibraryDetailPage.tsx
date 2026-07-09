import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { StatusBadge } from './StatusBadge'
import { SeriesSeasonsSection } from './SeriesSeasonsSection'
import { LibraryActionButtons } from './LibraryActionButtons'
import type { LibraryActionKind } from './LibraryTreeRow'
import { formatBytes, formatItemType } from '../utils/format'
import { buildDeepLink } from '../utils/libraryItem'

// Full dedicated detail page (Radarr/Sonarr-style) — replaces the old small
// modal and the large card. Rendered in place of the library list, with a
// back button, a large poster and all the item's fields.
function Field({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <div style={wide ? { gridColumn: '1 / -1' } : undefined}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 3 }}>{label}</div>
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

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <button className="btn btn-ghost btn-sm" onClick={onBack} style={{ marginBottom: 16 }}>← Volver a la biblioteca</button>

      <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap' }}>
        <div style={{ flexShrink: 0, width: 300, maxWidth: '100%' }}>
          <div style={{ width: '100%', aspectRatio: '2 / 3', borderRadius: 12, overflow: 'hidden', background: 'rgba(255,255,255,0.04)' }}>
            {item.poster_url ? (
              <img
                src={item.poster_url}
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
            <Field label="Nomenclatura"><StatusBadge status={item.nomenclature_status} type="nomenclature" /></Field>
            <Field label="Resolución">{item.resolution || '–'}</Field>
            <Field label="Source">{item.source || '–'}</Field>
            <Field label="Provider">{item.provider || '–'}</Field>
            <Field label="Códec de vídeo">{item.video_codec || '–'}</Field>
            <Field label="Códec de audio">{item.audio_codec || '–'}</Field>
            <Field label="Idiomas de audio">{item.audio_languages || '–'}</Field>
            <Field label="Subtítulos">{item.subtitle_languages || '–'}</Field>
            <Field label="Tamaño">{formatBytes(item.size_bytes)}</Field>
            <Field label="TMDb / IMDb">{item.tmdb_id ?? '—'} / {item.imdb_id ?? '—'}</Field>
            <Field label="Ruta" wide>{item.path ?? '—'}</Field>
          </div>

          {(item.recommended_action || item.diagnostic_summary) && (
            <div style={{ marginTop: 20, padding: '14px 16px', background: 'rgba(255,255,255,0.03)', borderRadius: 8, border: '1px solid var(--border)' }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Diagnóstico</div>
              {item.diagnostic_summary && <div style={{ fontSize: 13 }}>{item.diagnostic_summary}</div>}
              {item.recommended_action && (
                <div style={{ fontSize: 13, marginTop: 4 }}>
                  <span style={{ color: 'var(--text-muted)' }}>Acción recomendada: </span>
                  <span style={{ color: '#a78bfa', fontWeight: 600 }}>{item.recommended_action}</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {item.item_type === 'series' && (
        <div style={{ marginTop: 28 }}>
          <SeriesSeasonsSection seriesId={item.id} instances={instances} onSelect={onSelect} onAction={onAction} />
        </div>
      )}
    </div>
  )
}
