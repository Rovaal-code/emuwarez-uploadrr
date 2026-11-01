import { useState, useEffect, useCallback, useRef } from 'react'
import {
  createBackup,
  listBackups,
  downloadBackup,
  uploadBackup,
  restoreBackup,
  type MaintenanceStatus,
  type BackupInfo,
} from '../../api/maintenance'
import { formatBytes } from './formatBytes'
import { useSettingsMessage } from './mensajes'

const TIPO_COPIA: Record<BackupInfo['tipo'], string> = { manual: 'Manual', automatica: 'Automática', subida: 'Subida' }

export function BackupTab({ status, onRefresh }: { status: MaintenanceStatus | null; onRefresh: () => void }) {
  const [backups, setBackups] = useState<BackupInfo[]>([])
  const [backupDir, setBackupDir] = useState('')
  const [busy, setBusy] = useState(false)
  const [restoreName, setRestoreName] = useState('')
  const [restoreConfirm, setRestoreConfirm] = useState('')
  const subirRef = useRef<HTMLInputElement>(null)

  const showMessage = useSettingsMessage()

  const loadBackups = useCallback(async () => {
    try {
      const r = await listBackups()
      setBackups(r.backups)
      setBackupDir(r.backup_dir)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { loadBackups() }, [loadBackups])

  async function handleBackup() {
    setBusy(true)
    try {
      const r = await createBackup()
      showMessage(r.ok, r.ok ? `✓ Backup creado: ${r.archive_name} (${formatBytes(r.size_bytes ?? 0)})` : `✗ ${r.error}`)
      if (r.ok) { loadBackups(); onRefresh() }
    } catch (e: unknown) {
      showMessage(false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleDownload(b: BackupInfo) {
    try {
      await downloadBackup(b.name)
    } catch (e: unknown) {
      showMessage(false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  async function handleUpload(file: File | undefined) {
    if (!file) return
    setBusy(true)
    try {
      const r = await uploadBackup(file)
      showMessage(true, `✓ Backup subido: ${r.name} (${formatBytes(r.size_bytes)}). Ya puedes elegirlo para restaurar`)
      loadBackups()
      onRefresh()
    } catch (e: unknown) {
      showMessage(false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
      if (subirRef.current) subirRef.current.value = ''
    }
  }

  async function handleRestore(dry: boolean) {
    if (!restoreName) { showMessage(false, 'Elige un backup'); return }
    if (!dry && restoreConfirm !== 'RESTAURAR_CONFIG') {
      showMessage(false, 'Escribe RESTAURAR_CONFIG para confirmar'); return
    }
    setBusy(true)
    try {
      const r = await restoreBackup(restoreName, {
        dry_run: dry,
        apply: !dry,
        confirmation: dry ? undefined : restoreConfirm,
      })
      showMessage(r.ok, r.ok ? `✓ ${r.message}` : `✗ ${r.error}`)
    } catch (e: unknown) {
      showMessage(false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="placeholder-card">
        <h3>Crear backup</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 12px' }}>
          Crea un archivo <code>.tar.gz</code> del directorio de configuración, sin las claves: las API keys, la
          contraseña de qBittorrent, el webhook de Discord y el token de Telegram van vacíos, y no entran
          el <code>config.yaml</code> ni las cookies de Uploadrr-EMU.
        </p>
        <button className="btn btn-primary" onClick={handleBackup} disabled={busy}>
          {busy ? 'Creando…' : 'Crear backup ahora'}
        </button>
      </div>

      <div className="placeholder-card">
        <h3>Backups existentes ({status?.backups_count ?? backups.length})</h3>
        {backupDir && (
          <p style={{ color: 'var(--text-secondary)', fontSize: 12, margin: '0 0 10px' }}>
            Ubicación: <code>{backupDir}</code>
          </p>
        )}
        <p style={{ color: 'var(--text-secondary)', fontSize: 12, margin: '0 0 10px' }}>
          Las automáticas las crea la tarea Copia de seguridad (en Tareas) y se guardan las últimas; las manuales y
          las que subas no se borran solas.
        </p>
        {backups.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No hay backups.</p>
        ) : (
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Nombre', 'Tipo', 'Tamaño', 'Fecha', ''].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '4px 8px', borderBottom: '1px solid var(--border)', color: 'var(--text-secondary)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {backups.map(b => (
                <tr key={b.path} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '5px 8px' }}>{b.name}</td>
                  <td style={{ padding: '5px 8px' }}>{TIPO_COPIA[b.tipo]}{b.con_claves ? ' · con claves' : b.con_claves === null ? ' · puede llevar claves' : ''}</td>
                  <td style={{ padding: '5px 8px' }}>{formatBytes(b.size_bytes)}</td>
                  <td style={{ padding: '5px 8px' }}>{b.created_at.slice(0, 16).replace('T', ' ')}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right' }}>
                    <button className="btn btn-secondary btn-sm" onClick={() => handleDownload(b)}>Descargar</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div style={{ marginTop: 12 }}>
          <input
            ref={subirRef}
            type="file"
            accept=".gz,.tgz,application/gzip"
            hidden
            onChange={e => handleUpload(e.target.files?.[0])}
          />
          <button className="btn btn-secondary" onClick={() => subirRef.current?.click()} disabled={busy}>
            {busy ? 'Trabajando…' : 'Subir un backup…'}
          </button>
        </div>
      </div>

      <div className="placeholder-card">
        <h3>Restaurar backup</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 10px' }}>
          Elige uno de los backups existentes en <code>{backupDir || '…'}</code>. Las claves que el backup no
          lleve se quedan como las tienes ahora.
        </p>
        <select
          className="form-input form-select"
          value={restoreName}
          onChange={e => setRestoreName(e.target.value)}
          style={{ width: '100%', marginBottom: 8 }}
        >
          <option value="">Selecciona un backup…</option>
          {backups.map(b => (
            <option key={b.path} value={b.name}>{b.name} ({formatBytes(b.size_bytes)})</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Confirmación: RESTAURAR_CONFIG (solo para restauración real)"
          value={restoreConfirm}
          onChange={e => setRestoreConfirm(e.target.value)}
          style={{ width: '100%', marginBottom: 10, padding: '6px 10px', fontSize: 13, boxSizing: 'border-box' }}
        />
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary" onClick={() => handleRestore(true)} disabled={busy}>Previsualizar</button>
          <button className="btn btn-danger" onClick={() => handleRestore(false)} disabled={busy}>Restaurar</button>
        </div>
      </div>
    </div>
  )
}
