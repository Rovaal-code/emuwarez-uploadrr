import { useSync } from '../context/SyncContext'
import { Tooltip } from './Tooltip'

// «Sincronizar todo»: un solo botón para lo que antes eran tres (Biblioteca, eMuwarez, Peticiones). Lanza uno tras
// otro lo que ya hacía cada uno, por el SyncContext global, así que el progreso sale en la barra de arriba y el botón
// sigue desactivado mientras corre cualquier sincronización, la lance quien la lance.
export function SyncCard() {
  const { startAllSync, isAnySyncing, todoPendiente } = useSync()
  const ocupado = isAnySyncing || todoPendiente

  return (
    <div className="sync-card" data-tour="dashboard-sync-buttons">
      <Tooltip content="Sincroniza una tras otra la biblioteca (Radarr/Sonarr), lo nuevo del catálogo de eMuwarez y las peticiones. Lo que eMuwarez limita a una vez por hora y aún no toca se salta. El catálogo completo se lanza desde Biblioteca.">
        <button type="button" className="btn btn-secondary btn-sm" onClick={startAllSync} disabled={ocupado}>
          {ocupado
            ? <><span className="spinner emusync-spinner" /> Sincronizando…</>
            : '↻ Sincronizar todo'}
        </button>
      </Tooltip>
    </div>
  )
}
