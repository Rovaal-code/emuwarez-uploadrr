import type { MaintenanceStatus } from '../../api/maintenance'
import { formatBytes } from '../../utils/format'
import { VersionCard } from './diagnostico/VersionCard'
import { DatabaseActions } from './diagnostico/DatabaseActions'
import { PathMappingsCard } from './diagnostico/PathMappingsCard'
import { CabeceraTarjeta } from './CabeceraTarjeta'

export function DiagnosticsTab({ status, onRefresh }: { status: MaintenanceStatus | null; onRefresh: () => void }) {
  const db = status?.database
  return (
    <div className="aj-col-16">
      <VersionCard />
      <div className="placeholder-card">
        <CabeceraTarjeta titulo="Base de datos" />
        {!db ? (
          <p className="aj-sec-13">Cargando…</p>
        ) : !db.ok ? (
          <p className="aj-err-13">✗ {db.error}</p>
        ) : (
          <table className="aj-tabla aj-fs-13">
            <tbody>
              {[
                ['Ruta', db.db_path],
                ['Tamaño', formatBytes(db.size_bytes)],
                ['Páginas', db.page_count],
                ['Páginas libres', db.freelist_count],
                ['Fragmentación', `${db.fragmentation_pct ?? 0} %`],
              ].map(([k, v]) => (
                <tr key={String(k)} className="aj-fila-borde">
                  {/* El mismo ancho de etiqueta que la tabla de Versión, para que los valores casen en columna. */}
                  <td className="aj-td-etq-150">{k}</td>
                  {/* La ruta es un dato que se copia: en mono, y partida donde haga falta en vez de salirse. */}
                  <td className="aj-td-6">{k === 'Ruta' ? <span className="aj-ruta">{String(v ?? '—')}</span> : String(v ?? '—')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <DatabaseActions onRefresh={onRefresh} />
      </div>
      <div className="placeholder-card">
        <CabeceraTarjeta titulo="Inventario de configuración" />
        {!status ? (
          <p className="aj-sec-13">Cargando…</p>
        ) : (
          <>
            <p className="aj-fs-13 aj-m-0-8">
              Directorio: <code>{status.config_inventory.config_dir}</code><br />
              Archivos: {status.config_inventory.files.length} &nbsp;·&nbsp;
              Tamaño: {formatBytes(status.config_inventory.total_size_bytes)}
            </p>
          </>
        )}
      </div>
      <PathMappingsCard />
    </div>
  )
}
