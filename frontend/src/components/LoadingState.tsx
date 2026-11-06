interface LoadingStateProps {
  label?: string
}

export function LoadingState({ label = 'Cargando…' }: LoadingStateProps) {
  return (
    <div className="empty-state" role="status">
      <div className="spinner spinner-lg" aria-hidden="true" />
      <div className="empty-state-title">{label}</div>
    </div>
  )
}
