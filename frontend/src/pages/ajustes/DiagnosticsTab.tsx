import type { MaintenanceStatus } from '../../api/maintenance'
import { formatBytes } from './formatBytes'
import { VersionCard } from './diagnostico/VersionCard'
import { DatabaseActions } from './diagnostico/DatabaseActions'
import { PathMappingsCard } from './diagnostico/PathMappingsCard'

export function DiagnosticsTab({ status, onRefresh }: { status: MaintenanceStatus | null; onRefresh: () => void }) {
  const db = status?.database
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <VersionCard />
      <div className="placeholder-card">
        <h3>Base de datos</h3>
        {!db ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Cargando…</p>
        ) : !db.ok ? (
          <p style={{ color: 'var(--color-error)', fontSize: 13 }}>✗ {db.error}</p>
        ) : (
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <tbody>
              {[
                ['Ruta', db.db_path],
                ['Tamaño', formatBytes(db.size_bytes ?? 0)],
                ['Páginas', db.page_count],
                ['Freelist', db.freelist_count],
                ['Fragmentación', `${db.fragmentation_pct ?? 0} %`],
              ].map(([k, v]) => (
                <tr key={String(k)} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '6px 8px', color: 'var(--text-secondary)', width: 130 }}>{k}</td>
                  <td style={{ padding: '6px 8px' }}>{String(v ?? '—')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <DatabaseActions onRefresh={onRefresh} />
      </div>
      <div className="placeholder-card">
        <h3>Inventario de configuración</h3>
        {!status ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Cargando…</p>
        ) : (
          <>
            <p style={{ fontSize: 13, margin: '0 0 8px' }}>
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
