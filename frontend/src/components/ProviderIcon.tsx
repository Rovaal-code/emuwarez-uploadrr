// Favicon-style icon for a video provider (streaming service). Uses a local
// brand SVG from src/assets/providers/<code>.svg when available (downloaded
// from dashboard-icons); otherwise falls back to a coloured monogram. Meant to
// sit right before the provider name, like the Radarr/Sonarr ServiceIcon.
const PROVIDER_SVGS = (import.meta as unknown as {
  glob: (pattern: string, opts: object) => Record<string, string>
}).glob('../assets/providers/*.svg', { eager: true, query: '?url', import: 'default' })

// filename (lowercased code) -> url
const BY_CODE: Record<string, string> = {}
for (const [path, url] of Object.entries(PROVIDER_SVGS)) {
  const base = path.split('/').pop()!.replace(/\.svg$/, '').toLowerCase()
  BY_CODE[base] = url
}

// Deterministic colour for the monogram fallback so each provider is distinct.
function monoColor(code: string): string {
  let h = 0
  for (let i = 0; i < code.length; i++) h = (h * 31 + code.charCodeAt(i)) % 360
  return `hsl(${h} 45% 40%)`
}

export function ProviderIcon({ code, size = 18 }: { code: string | null | undefined; size?: number }) {
  if (!code) return null
  const key = code.trim().toLowerCase()
  const url = BY_CODE[key]
  const box: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: size, height: size, borderRadius: 4, flexShrink: 0, overflow: 'hidden',
    verticalAlign: 'middle',
  }
  if (url) {
    return (
      <span style={{ ...box, background: '#fff' }} title={code}>
        <img src={url} alt="" style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 2 }} />
      </span>
    )
  }
  // Monogram fallback — first two chars of the code on a coloured tile.
  const short = code.replace(/[^A-Za-z0-9+]/g, '').slice(0, 2).toUpperCase()
  return (
    <span style={{ ...box, background: monoColor(key), color: '#fff', fontSize: size * 0.42, fontWeight: 700 }} title={code}>
      {short}
    </span>
  )
}

// Icon + name inline, for the common "🅰 Amazon (AMZN)" display.
export function ProviderTag({ code, label, size = 18 }: { code: string | null | undefined; label?: string | null; size?: number }) {
  if (!code) return <>{label ?? '—'}</>
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
      <ProviderIcon code={code} size={size} />
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label ?? code}</span>
    </span>
  )
}
