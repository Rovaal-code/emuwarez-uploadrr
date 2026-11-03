import type { RequestSyncStatusResponse } from '../types/api'
import { Tooltip } from './Tooltip'

// Shared by RequestsPage and the Dashboard's "Peticiones eMuwarez" sync
// button — both surface the same 1h eMuwarez request-sync throttle
// (services/requests.py::MIN_SYNC_SECONDS), so this used to be duplicated.
export function SyncInfo({ syncStatus, onSync, syncing, blocked = false, label = 'Sincronizar', allowForce = true, title }: {
  syncStatus: RequestSyncStatusResponse | null
  onSync: (force: boolean) => void
  syncing: boolean
  // True while a DIFFERENT sync is running — disables the buttons without
  // showing this sync's own "Sincronizando…" label (that's reserved for `syncing`).
  blocked?: boolean
  label?: string
  allowForce?: boolean
  title?: string
}) {
  // Render the button even before the throttle status has loaded (or if it
  // failed), so the sync action is always visible; treat unknown as "can sync".
  const can_sync = syncStatus?.can_sync ?? true
  const wait_seconds = syncStatus?.wait_seconds ?? 0
  const last_sync_at = syncStatus?.last_sync_at ?? null
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
      <Tooltip content={!can_sync ? `Disponible en ${mins} min` : blocked ? 'Otra sincronización en curso' : (title ?? 'Sincronizar')}>
        <button className="btn btn-primary btn-sm" onClick={() => onSync(false)} disabled={syncing || blocked || !can_sync}>
          {syncing ? <><span className="spinner emusync-spinner" /> Sincronizando…</> : `↻ ${label}`}
        </button>
      </Tooltip>
      {!can_sync && allowForce && (
        <Tooltip content="Forzar sync">
          <button className="btn btn-secondary btn-sm" onClick={() => onSync(true)} disabled={syncing || blocked}>
            Forzar
          </button>
        </Tooltip>
      )}
    </div>
  )
}
