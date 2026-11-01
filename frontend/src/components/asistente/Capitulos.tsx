import { useTooltip } from '../Tooltip'

// library_items.title for an episode is built (integrations/sonarr.py's
// episode_to_library_item) as "{Serie} SxxExx - {título del capítulo}" —
// needed for Biblioteca's own listing, but redundant inside a season
// target's own MediaInfo/Remux accordion (EpisodeAccordionRow already
// prepends "Exx — " itself, and you're already looking at that one
// season). Strips everything up to and including the first " - ", keeping
// only the episode's own title; falls back to the full string if there's
// no " - " at all (an episode with no per-episode title in Sonarr).
function episodeOnlyTitle(fullTitle?: string | null): string | undefined {
  if (!fullTitle) return fullTitle ?? undefined
  const idx = fullTitle.indexOf(' - ')
  return idx === -1 ? fullTitle : fullTitle.slice(idx + 3)
}

// One collapsible episode row — used by the season target's MediaInfo/Remux
// accordions (one entry per episode instead of a single-file table).
// El desplegable con el que se elige capítulo dentro de una tarjeta de
// temporada (MediaInfo, Remux, nombres). Se oculta si solo hay uno: un
// desplegable de una sola opción no navega a ningún sitio.
export function EpisodePicker<T extends { episode_id: number; display_title?: string | null; title?: string | null }>(
  { episodes, currentId, onChange }: { episodes: T[]; currentId: number; onChange: (id: number) => void },
) {
  if (episodes.length <= 1) return null
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
      <select
        className="form-input form-select" style={{ width: 'auto' }}
        value={currentId} onChange={e => onChange(Number(e.target.value))}
      >
        {episodes.map(ep => (
          <option key={ep.episode_id} value={ep.episode_id}>
            {ep.display_title ?? episodeOnlyTitle(ep.title)}
          </option>
        ))}
      </select>
    </div>
  )
}

export function EpisodeAccordionRow({ episodeNumber, title, expanded, onToggle, children }: {
  episodeNumber?: number | null
  title?: string | null
  expanded: boolean
  onToggle: () => void
  children: React.ReactNode
}) {
  const { triggerProps, tooltipNode } = useTooltip(title ?? null)
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, marginBottom: 8, overflow: 'hidden' }}>
      <button
        type="button"
        onClick={onToggle}
        style={{
          width: '100%', textAlign: 'left', padding: '8px 12px', background: 'color-mix(in srgb, var(--overlay-light) 3%, transparent)',
          border: 'none', cursor: 'pointer', display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', gap: 8, color: 'inherit', fontSize: 13,
        }}
        {...triggerProps}
      >
        <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {episodeNumber != null ? `E${String(episodeNumber).padStart(2, '0')}: ` : ''}{title}
        </span>
        <span style={{ color: 'var(--text-muted)', fontSize: 11, flexShrink: 0 }}>{expanded ? '▲' : '▼'}</span>
        {tooltipNode}
      </button>
      {expanded && <div style={{ padding: 10 }}>{children}</div>}
    </div>
  )
}
