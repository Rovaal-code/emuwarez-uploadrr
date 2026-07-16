import { useState } from 'react'

// Shows the real favicon of a website (via Google's favicon service, which
// returns a normalized icon for any domain), falling back to `fallback` if the
// domain is missing or the icon fails to load.
export function Favicon({ domain, size = 16, fallback = null, radius = 3, background }: {
  domain?: string | null
  size?: number
  fallback?: React.ReactNode
  radius?: number
  // Optional tile background (e.g. white), so favicons with transparent/dark
  // marks stay visible on a dark UI.
  background?: string
}) {
  const [failed, setFailed] = useState(false)
  if (!domain || failed) return <>{fallback}</>
  const src = `https://www.google.com/s2/favicons?sz=64&domain=${domain}`
  const onError = () => setFailed(true)
  if (background) {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: size, height: size, borderRadius: radius, background, flexShrink: 0, overflow: 'hidden',
      }}>
        <img src={src} alt="" loading="lazy" onError={onError}
          style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 2, boxSizing: 'border-box' }} />
      </span>
    )
  }
  return (
    <img src={src} width={size} height={size} alt="" loading="lazy" onError={onError}
      style={{ borderRadius: radius, display: 'block', flexShrink: 0 }} />
  )
}

// Extract the hostname from a URL string (for hosts that expose a full URL).
export function domainOf(url?: string | null): string {
  if (!url) return ''
  try { return new URL(url).hostname } catch { return '' }
}
