import { useTooltip } from './Tooltip'

interface StatCardProps {
  label: string
  value: number | string
  children?: React.ReactNode
  accentColor?: string
  // Custom hover explanation (styled popover, not the native title box).
  info?: React.ReactNode
}

export function StatCard({ label, value, children, accentColor, info }: StatCardProps) {
  const { triggerProps, tooltipNode } = useTooltip(info, 460)
  return (
    <div
      className="stat-card"
      {...(info != null ? triggerProps : {})}
      style={info != null ? { cursor: 'help' } : undefined}
    >
      <div className="stat-card-label">{label}</div>
      <div className="stat-card-value" style={accentColor ? { color: accentColor } : undefined}>
        {value}
      </div>
      {children && <div className="stat-card-sub">{children}</div>}
      {tooltipNode}
    </div>
  )
}
