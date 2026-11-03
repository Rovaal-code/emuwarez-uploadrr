import { useState } from 'react'

// Shows a website's real favicon, falling back to `fallback` if nothing loads.
// Two-step chain: `src` (a known-good direct icon URL, e.g. one resolved by
// hand from the site's own <link rel="icon">) is tried first — Google's s2
// favicon proxy often returns a wrong/generic icon for low-traffic sites, so
// it's now only the fallback for domains without a verified direct URL.
export function Favicon({ domain, src, size = 16, fallback = null, radius = 3, background }: {
  domain?: string | null
  src?: string | null
  size?: number
  fallback?: React.ReactNode
  radius?: number
  // Optional tile background (e.g. white), so favicons with transparent/dark
  // marks stay visible on a dark UI.
  background?: string
}) {
  const [stage, setStage] = useState<'direct' | 'google' | 'failed'>(src ? 'direct' : 'google')
  const google = domain ? `https://www.google.com/s2/favicons?sz=64&domain=${domain}` : null
  const current = stage === 'direct' ? src : stage === 'google' ? google : null
  if (!current) return <>{fallback}</>
  const onError = () => setStage(s => (s === 'direct' && google ? 'google' : 'failed'))
  if (background) {
    return (
      <span className="menores-icono-caja" style={{ width: size, height: size, borderRadius: radius, background }}>
        <img src={current} alt="" loading="lazy" onError={onError}
          className="menores-icono-img menores-icono-img-caja" />
      </span>
    )
  }
  return (
    <img src={current} width={size} height={size} alt="" loading="lazy" onError={onError}
      style={{ borderRadius: radius, display: 'block', flexShrink: 0 }} />
  )
}

// Extract the hostname from a URL string (for hosts that expose a full URL).
export function domainOf(url?: string | null): string {
  if (!url) return ''
  try { return new URL(url).hostname } catch { return '' }
}
