import { useState } from 'react'

// Shows the real favicon of a website (via Google's favicon service, which
// returns a normalized icon for any domain), falling back to `fallback` if the
// domain is missing or the icon fails to load.
export function Favicon({ domain, size = 16, fallback = null, radius = 3 }: {
  domain?: string | null
  size?: number
  fallback?: React.ReactNode
  radius?: number
}) {
  const [failed, setFailed] = useState(false)
  if (!domain || failed) return <>{fallback}</>
  return (
    <img
      src={`https://www.google.com/s2/favicons?sz=64&domain=${domain}`}
      width={size}
      height={size}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      style={{ borderRadius: radius, display: 'block', flexShrink: 0 }}
    />
  )
}

// Extract the hostname from a URL string (for hosts that expose a full URL).
export function domainOf(url?: string | null): string {
  if (!url) return ''
  try { return new URL(url).hostname } catch { return '' }
}
