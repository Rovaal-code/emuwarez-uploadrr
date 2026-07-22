import { getLocalStatusInfo } from '../utils/status'
import { useTooltip } from './Tooltip'

// Availability marker for poster cards only. A translucent text badge was hard
// to read over artwork, so this is a solid, opaque circle with a white icon and
// ring: green ✓ for Disponible, red ✕ for Faltante, and the status colour with
// a dot for any other state.
export function PosterStatusIcon({ status }: { status: string }) {
  const available = status === 'Disponible'
  const missing = status === 'Faltante'
  const color = available ? '#16a34a' : missing ? '#dc2626' : getLocalStatusInfo(status).color
  const symbol = available ? '✓' : missing ? '✕' : '•'
  const { triggerProps, tooltipNode } = useTooltip(status)
  return (
    <span
      aria-label={status}
      style={{
        width: 24, height: 24, borderRadius: '50%', background: color,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        color: '#fff', fontSize: 14, fontWeight: 800, lineHeight: 1,
        border: '2px solid rgba(255,255,255,0.9)',
        boxShadow: '0 1px 4px rgba(0,0,0,0.55)',
      }}
      {...triggerProps}
    >
      {symbol}
      {tooltipNode}
    </span>
  )
}
