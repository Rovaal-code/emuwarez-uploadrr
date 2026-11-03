import { useState } from 'react'
import { iconoDe } from '../utils/iconosSitios'

// El icono de un sitio, el que va dentro del proyecto (utils/iconosSitios), o `fallback` si no hay o no carga.
export function Favicon({ domain, size = 16, fallback = null, radius = 3, background }: {
  domain?: string | null
  size?: number
  fallback?: React.ReactNode
  radius?: number
  // Optional tile background (e.g. white), so favicons with transparent/dark
  // marks stay visible on a dark UI.
  background?: string
}) {
  // La URL que falló, no un sí/no: si el mismo componente recibe otro dominio, su icono se intenta de nuevo.
  const [fallida, setFallida] = useState<string | null>(null)
  const url = domain ? iconoDe(domain) : null
  if (!url || fallida === url) return <>{fallback}</>
  const onError = () => setFallida(url)
  if (background) {
    return (
      <span className="menores-icono-caja" style={{ width: size, height: size, borderRadius: radius, background }}>
        <img src={url} alt="" onError={onError} className="menores-icono-img menores-icono-img-caja" />
      </span>
    )
  }
  return (
    <img src={url} width={size} height={size} alt="" onError={onError}
      style={{ borderRadius: radius, display: 'block', flexShrink: 0 }} />
  )
}

// Extract the hostname from a URL string (for hosts that expose a full URL).
export function domainOf(url?: string | null): string {
  if (!url) return ''
  try { return new URL(url).hostname } catch { return '' }
}
