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
import { CabeceraTarjeta } from './CabeceraTarjeta'

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
    <div className="aj-col-16">
      <div className="placeholder-card">
        <CabeceraTarjeta
          titulo="Crear backup"
          descripcion={<>
            Crea un archivo <code>.tar.gz</code> del directorio de configuración, sin las claves: las API keys, la
            contraseña de qBittorrent, el webhook de Discord y el token de Telegram van vacíos, y no entran
            el <code>config.yaml</code> ni las cookies de Uploadrr-EMU.
          </>}
        />
        <button className="btn btn-primary" onClick={handleBackup} disabled={busy}>
          {busy ? 'Creando…' : 'Crear backup ahora'}
        </button>
      </div>

      <div className="placeholder-card">
        <CabeceraTarjeta titulo={`Backups existentes (${status?.backups_count ?? backups.length})`} />
        {backupDir && (
          <p className="aj-sec-12 aj-m-0-10">
            Ubicación: <code>{backupDir}</code>
          </p>
        )}
        <p className="aj-sec-12 aj-m-0-10">
          Las automáticas las crea la tarea Copia de seguridad (en Tareas) y se guardan las últimas; las manuales y
          las que subas no se borran solas.
        </p>
        {backups.length === 0 ? (
          <p className="aj-sec-13">No hay backups.</p>
        ) : (
          <table className="aj-tabla aj-fs-12">
            <thead>
              <tr>
                {['Nombre', 'Tipo', 'Tamaño', 'Fecha'].map(h => (
                  <th key={h} className="aj-th">{h}</th>
                ))}
                <th className="aj-th"><span className="solo-lector">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {backups.map(b => (
                <tr key={b.path} className="aj-fila-borde">
                  <td className="aj-td-5">{b.name}</td>
                  <td className="aj-td-5">{TIPO_COPIA[b.tipo]}{b.con_claves ? ' · con claves' : b.con_claves === null ? ' · puede llevar claves' : ''}</td>
                  <td className="aj-td-5">{formatBytes(b.size_bytes)}</td>
                  <td className="aj-td-5">{b.created_at.slice(0, 16).replace('T', ' ')}</td>
                  <td className="aj-td-5 aj-der">
                    <button className="btn btn-secondary btn-sm" onClick={() => handleDownload(b)} aria-label={`Descargar ${b.name}`}>Descargar</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="aj-mt-12">
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
        <CabeceraTarjeta
          titulo="Restaurar backup"
          descripcion={<>
            Elige uno de los backups existentes en <code>{backupDir || '…'}</code>. Las claves que el backup no
            lleve se quedan como las tienes ahora.
          </>}
        />
        <select
          aria-label="Backup que restaurar"
          className="form-input form-select aj-w-100 aj-mb-8"
          value={restoreName}
          onChange={e => setRestoreName(e.target.value)}
        >
          <option value="">Selecciona un backup…</option>
          {backups.map(b => (
            <option key={b.path} value={b.name}>{b.name} ({formatBytes(b.size_bytes)})</option>
          ))}
        </select>
        <input
          type="text"
          aria-label="Confirmación de la restauración"
          autoComplete="off"
          placeholder="Confirmación: RESTAURAR_CONFIG (solo para restauración real)"
          value={restoreConfirm}
          onChange={e => setRestoreConfirm(e.target.value)}
          className="aj-campo-ancho aj-mb-10"
        />
        <div className="aj-flex-8">
          <button className="btn btn-secondary" onClick={() => handleRestore(true)} disabled={busy}>Previsualizar</button>
          <button className="btn btn-danger" onClick={() => handleRestore(false)} disabled={busy}>Restaurar</button>
        </div>
      </div>
    </div>
  )
}
