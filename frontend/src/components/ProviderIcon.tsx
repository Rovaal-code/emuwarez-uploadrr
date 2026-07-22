// Favicon-style badge for a video provider (streaming service), meant to sit
// right before the provider name like the Radarr/Sonarr ServiceIcon.
//
// Real brand logos rendered at ~16px are a mess (mixed shapes/colours, some
// need a white tile to be visible, many are wide "wordmarks", and automated
// logo lookups grab wrong marks), so every provider gets the same clean,
// consistent treatment instead: a rounded tile in the brand's colour with a
// short code. If you drop a curated square SVG into src/assets/providers/
// <code>.svg it is used instead.
import { Favicon } from './Favicon'
import { useTooltip } from './Tooltip'

const PROVIDER_SVGS = (import.meta as unknown as {
  glob: (pattern: string, opts: object) => Record<string, string>
}).glob('../assets/providers/*.svg', { eager: true, query: '?url', import: 'default' })

const BY_CODE: Record<string, string> = {}
for (const [path, url] of Object.entries(PROVIDER_SVGS)) {
  BY_CODE[path.split('/').pop()!.replace(/\.svg$/, '').toLowerCase()] = url
}

// Official-site domain per provider code (lowercase), for the real favicon.
// Mirrors services/source_assistant.PROVIDER_DOMAINS.
const DOMAINS: Record<string, string> = {
  amzn: 'primevideo.com', atvp: 'tv.apple.com', dsnp: 'disneyplus.com', f1tv: 'f1tv.formula1.com',
  glb: 'globoplay.globo.com', hs: 'hotstar.com', hulu: 'hulu.com', 'm+': 'movistarplus.es',
  it: 'apple.com', ma: 'moviesanywhere.com', max: 'max.com', hmax: 'max.com', sky: 'sky.com',
  pcok: 'peacocktv.com', pmtp: 'paramountplus.com', ip: 'bbc.co.uk', play: 'play.google.com',
  mubi: 'mubi.com', nf: 'netflix.com', rktn: 'rakuten.tv', sl: 'sonyliv.com', snxt: 'sunnxt.com',
  viu: 'viu.com', rtve: 'rtve.es', hbo: 'hbo.com', cr: 'crunchyroll.com',
  adn: 'animationdigitalnetwork.com', hidive: 'hidive.com', vrv: 'vrv.co', bili: 'bilibili.com',
  animebox: 'animebox.es', a3p: 'atresplayer.com', skst: 'skyshowtime.com', flmn: 'filmin.es',
  flixole: 'flixole.com', mgmp: 'mgmplus.com', strp: 'starplus.com', stz: 'starz.com', cnlp: 'canalplus.com',
}

// Brand colours per provider code (lowercase). Used for the tile background.
const BRAND: Record<string, string> = {
  nf: '#E50914', amzn: '#00A8E1', dsnp: '#0C36A3', atvp: '#374151', f1tv: '#E10600',
  glb: '#CC092F', hs: '#1F80E0', hulu: '#1CE783', 'm+': '#019DF4', it: '#D6249F',
  ma: '#1B3A6B', max: '#1A1CF5', hmax: '#1A1CF5', sky: '#0072C9', pcok: '#111827',
  pmtp: '#0064FF', ip: '#F54997', play: '#00A0C6', mubi: '#1A3EDB', rktn: '#BF0000',
  sl: '#1A1A4B', snxt: '#E50914', viu: '#F7C600', rtve: '#1A2A6B', hbo: '#7E5BEF',
  cr: '#F47521', adn: '#0096FF', hidive: '#00A6E0', vrv: '#E4D000', bili: '#00A1D6',
  animebox: '#6C2BD9', a3p: '#FF6B00', skst: '#2B2B5A', flmn: '#111827', flixole: '#E6017E',
  mgmp: '#B8860B', strp: '#2A9DF4', stz: '#111827', cnlp: '#111827',
}

// Deterministic colour for any provider not in BRAND, so it's still distinct.
function fallbackColor(code: string): string {
  let h = 0
  for (let i = 0; i < code.length; i++) h = (h * 31 + code.charCodeAt(i)) % 360
  return `hsl(${h} 45% 38%)`
}

// Dark text on light tiles (e.g. Viu/VRV yellow), white otherwise.
function textOn(hex: string): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex)
  if (!m) return '#fff'
  const n = parseInt(m[1], 16)
  const lum = (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255
  return lum > 0.62 ? '#1a1a1a' : '#fff'
}

export function ProviderIcon({ code, size = 18, link = true }: { code: string | null | undefined; size?: number; link?: boolean }) {
  // Hooks must run unconditionally every render — computed with safe
  // fallbacks so they're legal even when `code` is null (the early return
  // below happens after every hook call, never before).
  const key = (code ?? '').trim().toLowerCase()
  const domain = DOMAINS[key]
  const codeTip = useTooltip(code ?? null)
  const openTip = useTooltip(domain && link ? `Abrir ${domain}` : null)
  if (!code) return null
  const box: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: size, height: size, borderRadius: 4, flexShrink: 0, overflow: 'hidden',
    verticalAlign: 'middle',
  }
  // Coloured 2-letter tile — the last-resort fallback.
  const bg = BRAND[key] ?? fallbackColor(key)
  const short = code.replace(/[^A-Za-z0-9+]/g, '').slice(0, 2).toUpperCase()
  const codeTile = (
    <span style={{ ...box, background: bg, color: textOn(bg), fontSize: size * 0.44, fontWeight: 700, letterSpacing: '-0.03em' }} {...codeTip.triggerProps}>
      {short}
      {codeTip.tooltipNode}
    </span>
  )

  // A curated square SVG (dropped in assets/providers/) wins over everything;
  // otherwise the provider's real favicon, falling back to the coloured tile.
  const url = BY_CODE[key]
  const visual = url
    ? (
      <span style={{ ...box, background: '#fff' }} {...codeTip.triggerProps}>
        <img src={url} alt="" style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 2 }} />
        {codeTip.tooltipNode}
      </span>
    )
    : domain
      ? <Favicon domain={domain} size={size} radius={4} fallback={codeTile} />
      : codeTile

  // Link the icon to the provider's official site (opens in a new tab; the
  // stopPropagation keeps a table-row click from also firing). `link={false}`
  // lets ProviderTag wrap the icon + name in a single link instead.
  if (domain && link) {
    return (
      <a
        className="hover-link"
        href={`https://${domain}`}
        target="_blank"
        rel="noreferrer"
        onClick={e => e.stopPropagation()}
        draggable={false}
        style={{ display: 'inline-flex', flexShrink: 0 }}
        {...openTip.triggerProps}
      >
        {visual}
        {openTip.tooltipNode}
      </a>
    )
  }
  return visual
}

// Icon + name inline (e.g. "🅰 Amazon (AMZN)"). The whole thing (icon AND name)
// is the link to the provider's site, so hovering the text counts too.
export function ProviderTag({ code, label, size = 18 }: { code: string | null | undefined; label?: string | null; size?: number }) {
  const domain = code ? DOMAINS[code.trim().toLowerCase()] : undefined
  const { triggerProps, tooltipNode } = useTooltip(domain ? `Abrir ${domain}` : null)
  if (!code) return <>{label ?? '—'}</>
  const inner = (
    <>
      <ProviderIcon code={code} size={size} link={false} />
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label ?? code}</span>
    </>
  )
  const style: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }
  return domain
    ? <a className="hover-link" href={`https://${domain}`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} style={style} {...triggerProps}>{inner}{tooltipNode}</a>
    : <span style={style}>{inner}</span>
}
