interface StatCardProps {
  label: string
  value: number | string
  children?: React.ReactNode
  accentColor?: string
}

export function StatCard({ label, value, children, accentColor }: StatCardProps) {
  return (
    <div className="stat-card">
      <div className="stat-card-label">{label}</div>
      <div className="stat-card-value" style={accentColor ? { color: accentColor } : undefined}>
        {value}
      </div>
      {children && <div className="stat-card-sub">{children}</div>}
    </div>
  )
}
