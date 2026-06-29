interface EmptyStateProps {
  icon?: string
  title: string
  body?: string
  action?: React.ReactNode
}

export function EmptyState({ icon = '📭', title, body, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon}</div>
      <div className="empty-state-title">{title}</div>
      {body && <div className="empty-state-body">{body}</div>}
      {action}
    </div>
  )
}
