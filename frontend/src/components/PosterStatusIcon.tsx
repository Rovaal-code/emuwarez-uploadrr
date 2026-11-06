import { getLocalStatusInfo } from '../utils/status'
import { useTooltip } from './Tooltip'

// Availability marker for poster cards only. A translucent text badge was hard
// to read over artwork, so this is a solid, opaque circle with a white icon and
// ring: green ✓ for Disponible, red ✕ for Faltante, and the status colour with
// a dot for any other state.
export function PosterStatusIcon({ status }: { status: string }) {
  const available = status === 'Disponible'
  const missing = status === 'Faltante'
  const color = available ? 'var(--color-uploaded)' : missing ? 'var(--color-alert-strong)' : getLocalStatusInfo(status).color
  const symbol = available ? '✓' : missing ? '✕' : '•'
  const { triggerProps, tooltipNode } = useTooltip(status)
  return (
    <span
      role="img"
      aria-label={status}
      className="menores-poster-estado"
      style={{ background: color }}
      {...triggerProps}
    >
      {symbol}
      {tooltipNode}
    </span>
  )
}
