import { EmptyState } from '../components/EmptyState'

export function LogsPage() {
  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Logs</div>
          <div className="page-subtitle">Logs del sistema — motor heredado y servicios propios</div>
        </div>
      </div>
      <div className="activity-section">
        <div className="section-header">
          <div className="section-title">Logs recientes</div>
          <span className="badge status-unknown">Pendiente — Fase 5B</span>
        </div>
        <EmptyState
          icon="📄"
          title="Logs no disponibles"
          body="El endpoint GET /api/logs está reservado para una fase posterior."
        />
      </div>
    </div>
  )
}
