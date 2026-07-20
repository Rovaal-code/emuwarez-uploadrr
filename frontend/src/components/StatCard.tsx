import { useTooltip } from './Tooltip'

interface StatCardProps {
  label: string
  value: number | string
  children?: React.ReactNode
  accentColor?: string
  // Custom hover explanation (styled popover, not the native title box).
  info?: React.ReactNode
  // Optional leading icon — only rendered by callers that opt in (e.g. the
  // HUD-styled Panel), so plain stat-card usages elsewhere are unaffected.
  icon?: React.ReactNode
}

export function StatCard({ label, value, children, accentColor, info, icon }: StatCardProps) {
  const { triggerProps, tooltipNode } = useTooltip(info, 460)
  return (
    <div
      className="stat-card"
      {...(info != null ? triggerProps : {})}
      style={info != null ? { cursor: 'help' } : undefined}
    >
      {icon && <div className="stat-card-icon" style={accentColor ? { color: accentColor } : undefined}>{icon}</div>}
      <div className="stat-card-text">
        <div className="stat-card-label">{label}</div>
        <div className="stat-card-value" style={accentColor ? { color: accentColor } : undefined}>
          {value}
        </div>
        {children && <div className="stat-card-sub">{children}</div>}
      </div>
      {tooltipNode}
    </div>
  )
}
