interface LoadingStateProps {
  label?: string
}

export function LoadingState({ label = 'Cargando…' }: LoadingStateProps) {
  return (
    <div className="empty-state">
      <div className="spinner spinner-lg" />
      <div className="empty-state-title">{label}</div>
    </div>
  )
}
