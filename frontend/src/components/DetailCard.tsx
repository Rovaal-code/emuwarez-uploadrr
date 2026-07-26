import { InfoIcon } from './InfoIcon'
import { useTooltip } from './Tooltip'

// Shared building blocks for the "dedicated detail page" visual style
// (Radarr/Sonarr-style: back button, compact header with fixed-size poster,
// fields grouped into semantic cards) — used by LibraryDetailPage,
// RequestDetailPage and UploadJobDetailPage so all three stay visually and
// dimensionally identical.

// One shared standard size for every dedicated page's poster + card row —
// Biblioteca's "Información técnica" (8 value-chip rows) is the tallest
// card in the app, so this is calibrated to fit it comfortably; pages with
// fewer fields (Subidas, Peticiones) just stretch their cards up to the
// same standard instead of sizing smaller on their own. Used as the grid's
// `minHeight` (a floor, not a cap — content is never clipped if it ever
// needs more) and as the poster's fixed height, so both always agree.
export const DETAIL_CARD_HEIGHT = 480

// Wraps the header + poster/cards row in a hero banner using the content's
// own fanart/backdrop (Radarr/Sonarr's `images[coverType=fanart].remoteUrl`,
// same origin as the poster) as background, fading to the normal page
// background by the bottom edge — same wrapper on all three dedicated pages
// (Biblioteca/Subidas/Peticiones) so they get it identically. Renders
// children with no wrapper at all when there's no backdrop, so a page
// without one is laid out exactly as it always was.
export function DetailHero({ backdropUrl, children }: { backdropUrl?: string | null; children: React.ReactNode }) {
  if (!backdropUrl) return <>{children}</>
  return (
    <div className="detail-hero" style={{ '--hero-image': `url(${JSON.stringify(backdropUrl)})` } as React.CSSProperties}>
      {children}
    </div>
  )
}

// Wraps a dedicated page's title in the same card look as the other
// dedicated-page cards (e.g. "Estado de la biblioteca") via .detail-card —
// some content backdrops are very light/bright, and the title text
// (light-on-transparent by default) becomes unreadable sitting directly on
// top of one. Used identically by LibraryDetailPage, RequestsPage's detail
// view and UploadJobDetailPage.
export function DetailTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="detail-card" style={{
      display: 'inline-flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
      borderRadius: 10, padding: '10px 18px',
      fontWeight: 700, fontSize: 25, letterSpacing: '-0.01em',
    }}>
      {children}
    </div>
  )
}

// padding/gap/titleGap are overridable per page, but every current usage
// sticks to the defaults — tuned to fit 8 value-chip rows inside
// DETAIL_CARD_HEIGHT.
export function Card({ title, icon, children, padding = '21px 19px', gap = 10, titleGap = 13 }: {
  title: string
  icon?: React.ReactNode
  children: React.ReactNode
  padding?: string
  gap?: number
  titleGap?: number
}) {
  return (
    <div className="detail-card" style={{ borderRadius: 10, padding }}>
      <div className="detail-card-title" style={{
        fontSize: 13.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em',
        marginBottom: titleGap, paddingBottom: titleGap / 2,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        {icon && <span style={{ display: 'inline-flex', color: 'var(--text-accent)', flexShrink: 0 }}>{icon}</span>}
        {title}
      </div>
      {/* `--row-gap` drives the spacing AROUND the divider CSS (below) adds
          between rows — a plain flex `gap` can't have a line running through
          it, so the divider comes from `.detail-card-rows > * + *` in
          components.css instead (its `+` selector also naturally skips a
          FieldRow that rendered null, e.g. a missing external ID — no empty
          divider line where there's no DOM node). */}
      <div className="detail-card-rows" style={{ ['--row-gap' as string]: `${gap}px` } as React.CSSProperties}>
        {children}
      </div>
    </div>
  )
}

export function FieldRow({ label, children, help }: { label: string; children: React.ReactNode; help?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
      <span style={{ fontSize: 13.5, color: 'var(--text-muted)', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 4 }}>
        {label}
        {help && <InfoIcon text={help} />}
      </span>
      <span style={{ textAlign: 'right', wordBreak: 'break-word', minWidth: 0 }}>{children}</span>
    </div>
  )
}

// The mini-card a field's VALUE sits in (not the label — that stays plain
// text, see FieldRow above). `linkable` fields (has a real click/hover
// action — a link or the "Ver ruta" button) light up their whole padded
// area and turn the text accent-blue on hover, not just an inner element's
// own tight hitbox; static fields (plain specs, badges) stay put.
export function ValueChip({ children, linkable = false, as = 'span', onClick, title, blink }: {
  children: React.ReactNode
  linkable?: boolean
  as?: 'span' | 'button'
  onClick?: () => void
  title?: string
  // Pulses the chip's own border/glow between `blink` (green "new"/actionable,
  // red "failed") and its normal linkable-blue — see .chip-blink-new/
  // .chip-blink-alert in components.css.
  blink?: 'new' | 'alert'
}) {
  const { triggerProps, tooltipNode } = useTooltip(title ?? null)
  const className = `value-chip${linkable ? ' linkable' : ''}${blink ? ` chip-blink-${blink}` : ''}`
  if (as === 'button') {
    return <button type="button" className={className} onClick={onClick} {...triggerProps}>{children}{tooltipNode}</button>
  }
  return <span className={className} {...triggerProps}>{children}{tooltipNode}</span>
}

// Wraps a plain contextual icon (currentColor) placed before a field value —
// e.g. Tipo, Resolución, Tamaño. Colored via `.vicon` in components.css so it
// follows the chip's own hover color for the rare linkable case.
export function ValueIcon({ children }: { children: React.ReactNode }) {
  return <span className="vicon">{children}</span>
}

// Same mini-tarjeta (icon + value) the "Información técnica" card uses,
// reused in comparison tables (eMuwarez vs. tu copia, Petición vs. tu
// biblioteca) so their cells read the same way instead of plain text. Falls
// back to plain muted text for "no value"/"unknown" (—, ?, empty) instead of
// an empty-looking chip.
export function TechChip({ icon: Icon, value }: { icon: React.ComponentType; value: string | null | undefined }) {
  if (!value || value === '—' || value === '?') {
    return <span style={{ color: 'var(--text-muted)' }}>{value || '–'}</span>
  }
  return <ValueChip><ValueIcon><Icon /></ValueIcon><span className="txt">{value}</span></ValueChip>
}

// Glowing circular status icon — shared by the "Verificar subida" checklist
// (UploadWizardModal) and any other pass/fail/skip indicator that should
// read as the same affordance (e.g. a comparison table's ✓/✗ marks).
export function CheckStatusIcon({ status }: { status: 'ok' | 'fail' | 'skip' }) {
  const color = status === 'ok' ? '#22c55e' : status === 'skip' ? '#f59e0b' : '#ef4444'
  return (
    <svg viewBox="0 0 24 24" width={16} height={16}
      style={{ color, filter: `drop-shadow(0 0 4px ${color})`, flexShrink: 0 }}>
      <circle cx="12" cy="12" r="9.5" fill="none" stroke="rgba(56,189,255,.18)" strokeWidth="2" />
      <circle cx="12" cy="12" r="9.5" fill="none" stroke="currentColor" strokeWidth="2" />
      {status === 'ok' && (
        <path d="M5.5 12.5l4 4L18.5 7.5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      )}
      {status === 'skip' && (
        <>
          <path d="M12 7.5v5.2" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="12" cy="16.3" r="1.15" fill="currentColor" />
        </>
      )}
      {status === 'fail' && (
        <path d="M7 7l10 10M17 7L7 17" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  )
}

// Fixed-size poster (300px, 2:3) used at the top of every dedicated detail
// page, next to the title/action-buttons header.
export function DetailPoster({ url, alt, fallbackEmoji }: { url?: string | null; alt: string; fallbackEmoji: string }) {
  return (
    <div className="detail-poster" style={{ flexShrink: 0, height: DETAIL_CARD_HEIGHT, maxWidth: '100%', aspectRatio: '2 / 3', borderRadius: 10, overflow: 'hidden' }}>
      {url ? (
        <img
          src={url}
          alt={alt}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
        />
      ) : (
        <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 88, opacity: 0.35 }}>
          {fallbackEmoji}
        </div>
      )}
    </div>
  )
}

// --- Card-title icons (blue, same stroke style as Sidebar's nav icons) -----

function Icon({ children, size = 15 }: { children: React.ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  )
}

// "Estado de la biblioteca / la petición / la subida" — same info-circle
// wherever a card's whole purpose is showing a status.
export function StatusCardIcon() {
  return <Icon><circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="11" /><line x1="12" y1="8" x2="12.01" y2="8" /></Icon>
}

// "Información técnica" — a chip, for codec/resolution/technical specs.
export function TechInfoCardIcon() {
  return (
    <Icon>
      <rect x="5" y="5" width="14" height="14" rx="2" /><rect x="9" y="9" width="6" height="6" />
      <path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3" />
    </Icon>
  )
}

// "Identificadores externos" — a link/chain, for TMDb/IMDb/TVDB/MAL.
export function ExternalIdsCardIcon() {
  return (
    <Icon>
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </Icon>
  )
}

// "Detalle pedido" — a clipboard, same shape family as Sidebar's "requests" icon.
export function RequestCardIcon() {
  return (
    <Icon>
      <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
      <rect x="9" y="3" width="6" height="4" rx="1" /><path d="M9 12h6M9 16h4" />
    </Icon>
  )
}

// "Tiempos" — a clock.
export function ClockCardIcon() {
  return <Icon><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></Icon>
}

// --- Action-button icons (currentColor — inherit the button's own text color) ---

export function UploadButtonIcon() {
  return <Icon size={14}><path d="M12 19V5M5 12l7-7 7 7" /><path d="M5 19h14" /></Icon>
}

export function RequestButtonIcon() {
  return <Icon size={14}><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" /><rect x="9" y="3" width="6" height="4" rx="1" /><path d="M9 12h6M9 16h4" /></Icon>
}

export function LibraryButtonIcon() {
  return (
    <Icon size={14}>
      <path d="M4 19V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14" /><path d="M4 19h16" /><path d="M8 7h8M8 11h5" />
    </Icon>
  )
}

export function ExternalLinkButtonIcon() {
  return (
    <Icon size={14}>
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" />
    </Icon>
  )
}

export function CancelButtonIcon() {
  return <Icon size={14}><circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" /></Icon>
}

export function RetryButtonIcon() {
  return (
    <Icon size={14}>
      <path d="M1 4v6h6" /><path d="M3.51 15a9 9 0 1 0 .49-9.36L1 10" />
    </Icon>
  )
}

export function DeleteButtonIcon() {
  return (
    <Icon size={14}>
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <line x1="10" y1="11" x2="10" y2="17" /><line x1="14" y1="11" x2="14" y2="17" />
    </Icon>
  )
}

// --- Field-value icons (mono, currentColor via .vicon — see ValueIcon) ----
// One per plain-spec field shared across Biblioteca/Peticiones/Subidas, so
// the same concept (Tipo, a date, a source…) always shows the same glyph.

export function TypeValueIcon() {
  return <Icon size={14}><path d="M20.59 13.41 13.42 20.58a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82Z" /><circle cx="7" cy="7" r="1" /></Icon>
}

export function ResolutionValueIcon() {
  return <Icon size={14}><rect x="2" y="4" width="20" height="14" rx="2" /><line x1="8" y1="21" x2="16" y2="21" /><line x1="12" y1="17" x2="12" y2="21" /></Icon>
}

export function SourceValueIcon() {
  return <Icon size={14}><circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="3" /></Icon>
}

// "Cualquiera" — an unrestricted Resolución/Source request (no specific
// value asked for), shown instead of ResolutionValueIcon/SourceValueIcon so
// it reads as "no restriction" rather than "no data". Infinity glyph.
export function AnyValueIcon() {
  return <Icon size={14}><path d="M9.5 8c-1.5 0-3 1.5-3 4s1.5 4 3 4c1.5 0 2.5-1.5 4-4c1.5-2.5 2.5-4 4-4c1.5 0 3 1.5 3 4s-1.5 4-3 4c-1.5 0-2.5-1.5-4-4c-1.5-2.5-2.5-4-4-4z" /></Icon>
}

export function VideoCodecValueIcon() {
  return <Icon size={14}><path d="M23 7l-7 5 7 5V7z" /><rect x="1" y="5" width="15" height="14" rx="2" /></Icon>
}

export function AudioCodecValueIcon() {
  return <Icon size={14}><path d="M2 12h2M6 8v8M10 5v14M14 8v8M18 10v4M22 12h-2" /></Icon>
}

export function LanguageValueIcon() {
  return <Icon size={14}><circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" /></Icon>
}

export function SubtitleValueIcon() {
  return <Icon size={14}><rect x="2" y="4" width="20" height="16" rx="2" /><path d="M6 9h4M6 13h8M13 9h5" /></Icon>
}

export function SizeValueIcon() {
  return <Icon size={14}><line x1="22" y1="12" x2="2" y2="12" /><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" /><line x1="6" y1="16" x2="6.01" y2="16" /><line x1="10" y1="16" x2="10.01" y2="16" /></Icon>
}

export function AuthorValueIcon() {
  return <Icon size={14}><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></Icon>
}

export function CalendarValueIcon() {
  return <Icon size={14}><rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /></Icon>
}

export function SeasonValueIcon() {
  return <Icon size={14}><path d="M12 2 2 7l10 5 10-5-10-5Z" /><path d="M2 17l10 5 10-5" /><path d="M2 12l10 5 10-5" /></Icon>
}

export function EpisodeValueIcon() {
  return <Icon size={14}><circle cx="12" cy="12" r="10" /><polygon points="10 8 16 12 10 16 10 8" fill="currentColor" /></Icon>
}

// Filled star, always yellow regardless of context — unlike the other
// value icons (muted, inherit .vicon's color), a rating/recommendation star
// reads as "star" specifically because of that color.
export function RecommendationValueIcon() {
  return (
    <span style={{ color: '#facc15' }}>
      <Icon size={14}><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" fill="currentColor" /></Icon>
    </span>
  )
}

export function PointsValueIcon() {
  return <Icon size={14}><polygon points="12 2 15 9 22 9 16.5 13.5 18.5 21 12 16.5 5.5 21 7.5 13.5 2 9 9 9 12 2" fill="currentColor" stroke="none" /></Icon>
}

export function ThumbsUpValueIcon() {
  return <Icon size={14}><path d="M7 10v12" /><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z" /></Icon>
}

export function CommentValueIcon() {
  return <Icon size={14}><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" /></Icon>
}

export function ProgressValueIcon() {
  return <Icon size={14}><polyline points="2 12 7 12 9 6 13 18 15 12 22 12" /></Icon>
}

// "Nomenclatura" (Subidas) — a pencil, for the generated/editable name.
export function NomenclatureValueIcon() {
  return <Icon size={14}><path d="M12 20h9" /><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" /></Icon>
}

// "Verificación pre-subida" (Subidas) — same checkmark-in-clipboard as
// Sidebar's "Tareas" nav icon, for consistency (both are "checks passed").
export function ChecksValueIcon() {
  return <Icon size={14}><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></Icon>
}

// "Actividad" (Subidas) — same document-with-lines as Sidebar's "Logs" nav icon.
export function LogsValueIcon() {
  return (
    <Icon size={14}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14,2 14,8 20,8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" />
    </Icon>
  )
}

// Filled brand-blue folder icon for "Ver ruta" — fixed color (not
// currentColor): like Radarr/Sonarr/provider icons, it keeps its own color
// on hover and only grows a touch (via .brand-icon in components.css).
export function FolderIcon({ size = 15 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="#2cbde5">
      <path d="M4 4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2H4z" />
    </svg>
  )
}
