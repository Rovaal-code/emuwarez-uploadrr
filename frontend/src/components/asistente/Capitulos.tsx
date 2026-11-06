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
    <div className="asist-selector-fila">
      <select
        className="form-input form-select asist-select-auto"
        aria-label="Capítulo"
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
    <div className="asist-acordeon">
      <button
        type="button"
        onClick={onToggle}
        className="asist-acordeon-cabecera"
        {...triggerProps}
      >
        <span className="asist-truncar">
          {episodeNumber != null ? `E${String(episodeNumber).padStart(2, '0')}: ` : ''}{title}
        </span>
        <span className="asist-acordeon-flecha">{expanded ? '▲' : '▼'}</span>
        {tooltipNode}
      </button>
      {expanded && <div className="asist-acordeon-cuerpo">{children}</div>}
    </div>
  )
}
