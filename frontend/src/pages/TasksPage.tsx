import { EmptyState } from '../components/EmptyState'

export function TasksPage() {
  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Tareas</div>
          <div className="page-subtitle">Historial de tareas ejecutadas en el sistema</div>
        </div>
      </div>
      <div className="activity-section">
        <div className="section-header">
          <div className="section-title">Últimas tareas</div>
        </div>
        <EmptyState
          icon="⚙️"
          title="Sin tareas registradas"
          body="Las tareas de sincronización, análisis y subida aparecerán aquí con su estado y resumen."
        />
      </div>
    </div>
  )
}
