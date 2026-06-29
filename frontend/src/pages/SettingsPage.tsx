import { useState, useEffect, useCallback } from 'react'
import {
  getMaintenanceStatus,
  exportSettings,
  createBackup,
  listBackups,
  restoreBackup,
  runIntegrityCheck,
  runVacuum,
  cleanupLogs,
  type MaintenanceStatus,
  type BackupInfo,
} from '../api/maintenance'

type Tab = 'config' | 'diagnostics' | 'backup' | 'maintenance'

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

// ---------- Config tab (placeholder — settings edit via setup wizard) ----------
function ConfigTab() {
  return (
    <div className="placeholder-page">
      <div className="placeholder-card">
        <div className="placeholder-tag">Exportar / Importar ajustes</div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.7 }}>
          Usa la pestaña <strong>Backup</strong> para exportar ajustes sin secretos.<br />
          Para modificar la configuración avanzada (API keys, rutas) usa el asistente de configuración
          o la CLI: <code>maintenance export-settings</code>.
        </p>
      </div>
      <div className="placeholder-card">
        <h3>Secciones</h3>
        <ol>
          <li>General — nombre, zona horaria</li>
          <li>TMDb — API key, idioma, región</li>
          <li>eMuwarez — API key, endpoint, intervalo</li>
          <li>Uploadrr — ruta</li>
          <li>Seguridad — cambiar contraseña</li>
        </ol>
      </div>
    </div>
  )
}

// ---------- Diagnostics tab ----------
function DiagnosticsTab({ status }: { status: MaintenanceStatus | null }) {
  const db = status?.database
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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
                <tr key={String(k)} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '6px 8px', color: 'var(--text-secondary)', width: 130 }}>{k}</td>
                  <td style={{ padding: '6px 8px' }}>{String(v ?? '–')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
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
    </div>
  )
}

// ---------- Backup tab ----------
function BackupTab({ status, onRefresh }: { status: MaintenanceStatus | null; onRefresh: () => void }) {
  const [backups, setBackups] = useState<BackupInfo[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [restorePath, setRestorePath] = useState('')
  const [restoreConfirm, setRestoreConfirm] = useState('')

  const loadBackups = useCallback(async () => {
    try {
      const r = await listBackups()
      setBackups(r.backups)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { loadBackups() }, [loadBackups])

  async function handleBackup() {
    setBusy(true)
    setMessage(null)
    try {
      const r = await createBackup()
      setMessage({ ok: r.ok, text: r.ok ? `✓ Backup creado: ${r.archive_name} (${formatBytes(r.size_bytes ?? 0)})` : `✗ ${r.error}` })
      if (r.ok) { loadBackups(); onRefresh() }
    } catch (e: unknown) {
      setMessage({ ok: false, text: `✗ ${e instanceof Error ? e.message : String(e)}` })
    } finally {
      setBusy(false)
    }
  }

  async function handleRestore(dry: boolean) {
    if (!restorePath) { setMessage({ ok: false, text: 'Introduce la ruta del backup' }); return }
    if (!dry && restoreConfirm !== 'RESTAURAR_CONFIG') {
      setMessage({ ok: false, text: 'Escribe RESTAURAR_CONFIG para confirmar' }); return
    }
    setBusy(true)
    setMessage(null)
    try {
      const r = await restoreBackup(restorePath, {
        dry_run: dry,
        apply: !dry,
        confirmation: dry ? undefined : restoreConfirm,
      })
      setMessage({ ok: r.ok, text: r.ok ? `✓ ${r.message}` : `✗ ${r.error}` })
    } catch (e: unknown) {
      setMessage({ ok: false, text: `✗ ${e instanceof Error ? e.message : String(e)}` })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {message && (
        <div style={{ padding: '10px 14px', borderRadius: 6, background: message.ok ? 'var(--color-success-bg, #1a2e1a)' : 'var(--color-error-bg, #2e1a1a)', fontSize: 13 }}>
          {message.text}
        </div>
      )}
      <div className="placeholder-card">
        <h3>Crear backup</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 12px' }}>
          Crea un archivo <code>.tar.gz</code> del directorio de configuración (sin secretos en el nombre).
        </p>
        <button className="btn-primary" onClick={handleBackup} disabled={busy}>
          {busy ? 'Creando…' : 'Crear backup ahora'}
        </button>
      </div>

      <div className="placeholder-card">
        <h3>Backups existentes ({status?.backups_count ?? backups.length})</h3>
        {backups.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No hay backups.</p>
        ) : (
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Nombre', 'Tamaño', 'Fecha'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '4px 8px', borderBottom: '1px solid var(--border-color)', color: 'var(--text-secondary)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {backups.map(b => (
                <tr key={b.path} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '5px 8px' }}>{b.name}</td>
                  <td style={{ padding: '5px 8px' }}>{formatBytes(b.size_bytes)}</td>
                  <td style={{ padding: '5px 8px' }}>{b.created_at.slice(0, 16).replace('T', ' ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="placeholder-card">
        <h3>Restaurar backup</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 10px' }}>
          Introduce la ruta completa del archivo <code>.tar.gz</code> a restaurar.
        </p>
        <input
          type="text"
          placeholder="Ruta del backup, p.ej. /config/backups/emuwarez_config_….tar.gz"
          value={restorePath}
          onChange={e => setRestorePath(e.target.value)}
          style={{ width: '100%', marginBottom: 8, padding: '6px 10px', fontSize: 13, boxSizing: 'border-box' }}
        />
        <input
          type="text"
          placeholder="Confirmación: RESTAURAR_CONFIG (solo para restauración real)"
          value={restoreConfirm}
          onChange={e => setRestoreConfirm(e.target.value)}
          style={{ width: '100%', marginBottom: 10, padding: '6px 10px', fontSize: 13, boxSizing: 'border-box' }}
        />
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-secondary" onClick={() => handleRestore(true)} disabled={busy}>Previsualizar</button>
          <button className="btn-danger" onClick={() => handleRestore(false)} disabled={busy}>Restaurar</button>
        </div>
      </div>
    </div>
  )
}

// ---------- Maintenance tab ----------
function MaintenanceTab() {
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<{ key: string; ok: boolean; text: string }[]>([])
  const [vacuumConfirm, setVacuumConfirm] = useState('')
  const [cleanupConfirm, setCleanupConfirm] = useState('')
  const [cleanupDays, setCleanupDays] = useState(30)

  function addResult(key: string, ok: boolean, text: string) {
    setResults(prev => [{ key: `${key}-${Date.now()}`, ok, text }, ...prev.slice(0, 9)])
  }

  async function handleIntegrity() {
    setBusy(true)
    try {
      const r = await runIntegrityCheck()
      addResult('integrity', r.ok, r.ok ? `✓ ${r.message}` : `✗ ${r.message || r.error}`)
    } catch (e: unknown) {
      addResult('integrity', false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally { setBusy(false) }
  }

  async function handleVacuum(dry: boolean) {
    if (!dry && vacuumConfirm !== 'MANTENIMIENTO_DB') {
      addResult('vacuum', false, 'Escribe MANTENIMIENTO_DB para confirmar'); return
    }
    setBusy(true)
    try {
      const r = await runVacuum({ dry_run: dry, apply: !dry, confirmation: dry ? undefined : vacuumConfirm })
      addResult('vacuum', r.ok ?? false, r.ok ? `✓ ${r.message}` : `✗ ${r.error}`)
    } catch (e: unknown) {
      addResult('vacuum', false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally { setBusy(false) }
  }

  async function handleCleanup(dry: boolean) {
    if (!dry && cleanupConfirm !== 'LIMPIAR_LOGS') {
      addResult('cleanup', false, 'Escribe LIMPIAR_LOGS para confirmar'); return
    }
    setBusy(true)
    try {
      const r = await cleanupLogs({ days: cleanupDays, dry_run: dry, apply: !dry, confirmation: dry ? undefined : cleanupConfirm })
      addResult('cleanup', r.ok ?? false, r.ok ? `✓ ${r.message}` : `✗ ${r.error}`)
    } catch (e: unknown) {
      addResult('cleanup', false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally { setBusy(false) }
  }

  async function handleExportSettings() {
    setBusy(true)
    try {
      const r = await exportSettings(false)
      if (r.ok && r.settings) {
        const blob = new Blob([JSON.stringify(r.settings, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'emuwarez_settings_export.json'
        a.click()
        URL.revokeObjectURL(url)
        addResult('export', true, `✓ Ajustes exportados (secretos enmascarados)`)
      } else {
        addResult('export', false, `✗ ${r.error}`)
      }
    } catch (e: unknown) {
      addResult('export', false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally { setBusy(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {results.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {results.map(r => (
            <div key={r.key} style={{ padding: '8px 12px', borderRadius: 6, fontSize: 13, background: r.ok ? 'var(--color-success-bg, #1a2e1a)' : 'var(--color-error-bg, #2e1a1a)' }}>
              {r.text}
            </div>
          ))}
        </div>
      )}

      <div className="placeholder-card">
        <h3>Ajustes</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 10px' }}>Exporta los ajustes actuales en JSON (secretos enmascarados).</p>
        <button className="btn-secondary" onClick={handleExportSettings} disabled={busy}>Exportar ajustes (JSON)</button>
      </div>

      <div className="placeholder-card">
        <h3>Integridad de la base de datos</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 10px' }}>Ejecuta <code>PRAGMA integrity_check</code> — solo lectura.</p>
        <button className="btn-secondary" onClick={handleIntegrity} disabled={busy}>Verificar integridad</button>
      </div>

      <div className="placeholder-card">
        <h3>VACUUM de la base de datos</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 10px' }}>Compacta la BD y libera espacio. Escribe <code>MANTENIMIENTO_DB</code> para ejecutar.</p>
        <input
          type="text"
          placeholder="Confirmación: MANTENIMIENTO_DB"
          value={vacuumConfirm}
          onChange={e => setVacuumConfirm(e.target.value)}
          style={{ width: '100%', marginBottom: 8, padding: '6px 10px', fontSize: 13, boxSizing: 'border-box' }}
        />
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-secondary" onClick={() => handleVacuum(true)} disabled={busy}>Previsualizar</button>
          <button className="btn-danger" onClick={() => handleVacuum(false)} disabled={busy}>Ejecutar VACUUM</button>
        </div>
      </div>

      <div className="placeholder-card">
        <h3>Limpiar logs internos</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 10px' }}>Elimina archivos de log más antiguos de N días. Escribe <code>LIMPIAR_LOGS</code> para confirmar.</p>
        <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
          <label style={{ fontSize: 13 }}>Días:</label>
          <input type="number" min={1} max={365} value={cleanupDays} onChange={e => setCleanupDays(Number(e.target.value))}
            style={{ width: 70, padding: '4px 8px', fontSize: 13 }} />
        </div>
        <input
          type="text"
          placeholder="Confirmación: LIMPIAR_LOGS"
          value={cleanupConfirm}
          onChange={e => setCleanupConfirm(e.target.value)}
          style={{ width: '100%', marginBottom: 8, padding: '6px 10px', fontSize: 13, boxSizing: 'border-box' }}
        />
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-secondary" onClick={() => handleCleanup(true)} disabled={busy}>Previsualizar</button>
          <button className="btn-danger" onClick={() => handleCleanup(false)} disabled={busy}>Limpiar logs</button>
        </div>
      </div>
    </div>
  )
}

// ---------- Main page ----------
export function SettingsPage() {
  const [tab, setTab] = useState<Tab>('config')
  const [status, setStatus] = useState<MaintenanceStatus | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const loadStatus = useCallback(async () => {
    try {
      const s = await getMaintenanceStatus()
      setStatus(s)
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => { loadStatus() }, [loadStatus])

  const tabs: { key: Tab; label: string }[] = [
    { key: 'config', label: 'Configuración' },
    { key: 'diagnostics', label: 'Diagnóstico' },
    { key: 'backup', label: 'Backup' },
    { key: 'maintenance', label: 'Mantenimiento' },
  ]

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Configuración</div>
          <div className="page-subtitle">Ajustes, diagnóstico, backup y mantenimiento</div>
        </div>
      </div>

      {loadError && (
        <div style={{ padding: '8px 14px', marginBottom: 12, background: 'var(--color-error-bg, #2e1a1a)', borderRadius: 6, fontSize: 13 }}>
          ✗ No se pudo cargar el estado de mantenimiento: {loadError}
        </div>
      )}

      <div style={{ display: 'flex', gap: 2, marginBottom: 20, borderBottom: '1px solid var(--border-color)' }}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '8px 16px',
              fontSize: 13,
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              color: tab === t.key ? 'var(--color-accent, #7c6af7)' : 'var(--text-secondary)',
              borderBottom: tab === t.key ? '2px solid var(--color-accent, #7c6af7)' : '2px solid transparent',
              marginBottom: -1,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'config' && <ConfigTab />}
      {tab === 'diagnostics' && <DiagnosticsTab status={status} />}
      {tab === 'backup' && <BackupTab status={status} onRefresh={loadStatus} />}
      {tab === 'maintenance' && <MaintenanceTab />}
    </div>
  )
}
