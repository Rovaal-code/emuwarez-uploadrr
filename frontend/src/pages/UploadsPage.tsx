import { EmptyState } from '../components/EmptyState'

export function UploadsPage() {
  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Subidas</div>
          <div className="page-subtitle">Historial y estado de trabajos de subida con Uploadrr</div>
        </div>
      </div>
      <div className="activity-section">
        <div className="section-header">
          <div className="section-title">Trabajos de subida</div>
          <span className="badge status-unknown">Pendiente — Fase 5B</span>
        </div>
        <EmptyState
          icon="📤"
          title="Sin subidas registradas"
          body="Los trabajos de subida iniciados desde Biblioteca o Peticiones aparecerán aquí con progreso en tiempo real."
        />
      </div>
    </div>
  )
}
