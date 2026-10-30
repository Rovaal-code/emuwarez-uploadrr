import { IconoBandeja } from './Iconos'
interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  body?: string
  action?: React.ReactNode
}

export function EmptyState({ icon = <IconoBandeja />, title, body, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon}</div>
      <div className="empty-state-title">{title}</div>
      {body && <div className="empty-state-body">{body}</div>}
      {action}
    </div>
  )
}

// Vacío dentro de la tabla, para que la cabecera (y sus filtros) siga a mano.
export function FilaVacia({ columnas, ...props }: EmptyStateProps & { columnas: number }) {
  return (
    <tbody>
      <tr className="fila-hueco"><td colSpan={columnas}><EmptyState {...props} /></td></tr>
    </tbody>
  )
}
