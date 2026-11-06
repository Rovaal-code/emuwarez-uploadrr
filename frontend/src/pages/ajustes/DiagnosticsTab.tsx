import type { MaintenanceStatus } from '../../api/maintenance'
import { formatBytes } from './formatBytes'
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
                ['Tamaño', formatBytes(db.size_bytes ?? 0)],
                ['Páginas', db.page_count],
                ['Páginas libres', db.freelist_count],
                ['Fragmentación', `${db.fragmentation_pct ?? 0} %`],
              ].map(([k, v]) => (
                <tr key={String(k)} className="aj-fila-borde">
                  <td className="aj-td-etq-130">{k}</td>
                  <td className="aj-td-6">{String(v ?? '—')}</td>
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
