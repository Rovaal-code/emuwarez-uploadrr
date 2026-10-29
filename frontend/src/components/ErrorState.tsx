import { IconoAviso } from './Iconos'
interface ErrorStateProps {
  title?: string
  message: string
  onRetry?: () => void
}

export function ErrorState({ title = 'Error', message, onRetry }: ErrorStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon"><IconoAviso /></div>
      <div className="empty-state-title">{title}</div>
      <div className="empty-state-body">{message}</div>
      {onRetry && (
        <button className="btn btn-secondary btn-sm" onClick={onRetry}>
          Reintentar
        </button>
      )}
    </div>
  )
}
