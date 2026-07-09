import type { RequestSyncStatusResponse } from '../types/api'

// Shared by RequestsPage and the Dashboard's "Peticiones eMuwarez" sync
// button — both surface the same 1h eMuwarez request-sync throttle
// (services/requests.py::MIN_SYNC_SECONDS), so this used to be duplicated.
export function SyncInfo({ syncStatus, onSync, syncing, label = 'Sincronizar', allowForce = true }: {
  syncStatus: RequestSyncStatusResponse | null
  onSync: (force: boolean) => void
  syncing: boolean
  label?: string
  allowForce?: boolean
}) {
  if (!syncStatus) return null
  const { can_sync, wait_seconds, last_sync_at } = syncStatus
  const mins = Math.ceil(wait_seconds / 60)
  return (
    <div className="sync-info">
      {last_sync_at && (
        <span className="sync-info__last">
          Última sync: {new Date(last_sync_at).toLocaleString('es-ES')}
        </span>
      )}
      {!can_sync && (
        <span className="sync-info__throttle">Disponible en {mins} min</span>
      )}
      <button className="btn btn-primary btn-sm" onClick={() => onSync(false)} disabled={syncing || !can_sync}>
        {syncing ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Sincronizando…</> : `↻ ${label}`}
      </button>
      {!can_sync && allowForce && (
        <button className="btn btn-secondary btn-sm" onClick={() => onSync(true)} disabled={syncing} title="Forzar sync">
          Forzar
        </button>
      )}
    </div>
  )
}
