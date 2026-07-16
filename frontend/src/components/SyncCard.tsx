import { useSync } from '../context/SyncContext'
import { Tooltip } from './Tooltip'
import { EmuSyncButton } from './EmuSyncButton'

// Small "Sincronizar" card grouping the three sync actions (Biblioteca,
// eMuwarez, Peticiones). Backed by the global SyncContext, so the buttons stay
// disabled while their sync runs on any tab and the live progress shows in the
// shared banner.
export function SyncCard() {
  const {
    libSyncing, startLibrarySync,
    requestsSyncing, requestsStatus, startRequestsSync,
  } = useSync()

  const requestsWait = requestsStatus && !requestsStatus.can_sync ? Math.ceil(requestsStatus.wait_seconds / 60) : 0

  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <Tooltip content="Consulta tus instancias de Radarr/Sonarr y actualiza la biblioteca local (títulos, rutas, estado en disco y nomenclatura).">
          <button className="btn btn-primary btn-sm" onClick={startLibrarySync} disabled={libSyncing}>
            {libSyncing
              ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Sincronizando…</>
              : '↻ Biblioteca'}
          </button>
        </Tooltip>

        <EmuSyncButton label="eMuwarez" />

        <Tooltip content={requestsWait
          ? `Disponible en ${requestsWait} min`
          : 'Descarga de eMuwarez las peticiones activas y las cruza con tu biblioteca local para ver cuáles puedes cubrir. Limitado a una vez por hora.'}>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => startRequestsSync(false)}
            disabled={requestsSyncing || requestsWait > 0}
          >
            {requestsSyncing
              ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Sincronizando…</>
              : requestsWait
                ? `↻ Peticiones (${requestsWait} min)`
                : '↻ Peticiones'}
          </button>
        </Tooltip>
    </div>
  )
}
