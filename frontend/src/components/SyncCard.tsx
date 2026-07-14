import { useSync } from '../context/SyncContext'
import { Tooltip } from './Tooltip'

// Small "Sincronizar" card grouping the three sync actions (Biblioteca,
// eMuwarez, Peticiones). Backed by the global SyncContext, so the buttons stay
// disabled while their sync runs on any tab and the live progress shows in the
// shared banner.
export function SyncCard() {
  const {
    libSyncing, startLibrarySync,
    catalogSyncing, catalogStatus, startCatalogSync,
    requestsSyncing, requestsStatus, startRequestsSync,
  } = useSync()

  const catalogWait = catalogStatus && !catalogStatus.can_sync ? Math.ceil(catalogStatus.wait_seconds / 60) : 0
  const requestsWait = requestsStatus && !requestsStatus.can_sync ? Math.ceil(requestsStatus.wait_seconds / 60) : 0

  return (
    <div className="activity-section" style={{ padding: '12px 16px', marginBottom: 16 }}>
      <div className="section-title" style={{ marginBottom: 10 }}>Sincronizar</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Tooltip content="Consulta tus instancias de Radarr/Sonarr y actualiza la biblioteca local (títulos, rutas, estado en disco y nomenclatura).">
          <button className="btn btn-primary btn-sm" onClick={startLibrarySync} disabled={libSyncing}>
            {libSyncing
              ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Sincronizando…</>
              : '↻ Biblioteca'}
          </button>
        </Tooltip>

        <Tooltip content={catalogWait
          ? `Disponible en ${catalogWait} min`
          : 'Descarga el catálogo de eMuwarez y compara con tu biblioteca (1 vez/hora).'}>
          <button
            className="btn btn-primary btn-sm"
            onClick={startCatalogSync}
            disabled={catalogSyncing || catalogWait > 0}
          >
            {catalogSyncing
              ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Comparando…</>
              : catalogWait
                ? `⇅ eMuwarez (${catalogWait} min)`
                : '⇅ eMuwarez'}
          </button>
        </Tooltip>

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
    </div>
  )
}
