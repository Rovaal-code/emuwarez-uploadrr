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
import { fetchSettings, updateSettings, type SettingsData, type UploadrrRuntimeType } from '../api/settings'
import { testTmdbConnection, testUploadrrConnection, type IntegrationTestResult } from '../api/integrationTests'

type Tab = 'config' | 'diagnostics' | 'backup' | 'maintenance'

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

// ---------- Config tab ----------
function ConfigTab() {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [testingTmdb, setTestingTmdb] = useState(false)
  const [tmdbTestResult, setTmdbTestResult] = useState<IntegrationTestResult | null>(null)

  // Form state
  const [tag, setTag] = useState('')
  const [priorityRaw, setPriorityRaw] = useState('')
  const [region, setRegion] = useState('')
  const [language, setLanguage] = useState('')
  const [newKey, setNewKey] = useState('')

  // Uploadrr runtime form state (Phase 10F)
  const [uploadrrPath, setUploadrrPath] = useState('')
  const [uploadrrRuntimeType, setUploadrrRuntimeType] = useState<UploadrrRuntimeType>('uploadrr_emu')
  const [uploadrrPythonPath, setUploadrrPythonPath] = useState('')
  const [uploadrrTimeout, setUploadrrTimeout] = useState(7200)
  const [uploadrrAllowedRootsRaw, setUploadrrAllowedRootsRaw] = useState('')
  const [testingUploadrr, setTestingUploadrr] = useState(false)
  const [uploadrrTestResult, setUploadrrTestResult] = useState<IntegrationTestResult | null>(null)

  useEffect(() => {
    fetchSettings()
      .then(s => {
        setSettings(s)
        setTag(s.default_release_tag)
        setPriorityRaw(s.provider_priority_order.join(','))
        setRegion(s.tmdb_watch_region)
        setLanguage(s.tmdb_language)
        setUploadrrPath(s.uploadrr_path ?? '')
        setUploadrrRuntimeType(s.uploadrr_runtime_type)
        setUploadrrPythonPath(s.uploadrr_python_path ?? '')
        setUploadrrTimeout(s.uploadrr_timeout)
        setUploadrrAllowedRootsRaw((s.uploadrr_allowed_roots ?? []).join(','))
      })
      .catch(() => setMsg({ ok: false, text: 'Error cargando configuración' }))
      .finally(() => setLoading(false))
  }, [])

  async function handleTestUploadrr() {
    setTestingUploadrr(true)
    setUploadrrTestResult(null)
    try {
      const params: { path?: string; python_path?: string } = {}
      if (uploadrrPath.trim()) params.path = uploadrrPath.trim()
      if (uploadrrPythonPath.trim()) params.python_path = uploadrrPythonPath.trim()
      const r = await testUploadrrConnection(params)
      setUploadrrTestResult(r)
    } catch {
      setUploadrrTestResult({ ok: false, service: 'uploadrr', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setTestingUploadrr(false)
    }
  }

  async function handleTestTmdb() {
    setTestingTmdb(true)
    setTmdbTestResult(null)
    try {
      const params: { api_key?: string; language?: string; region?: string } = {}
      if (newKey.trim()) params.api_key = newKey.trim()
      if (language.trim()) params.language = language.trim()
      if (region.trim()) params.region = region.trim()
      const r = await testTmdbConnection(params)
      setTmdbTestResult(r)
    } catch {
      setTmdbTestResult({ ok: false, service: 'tmdb', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setTestingTmdb(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    setMsg(null)
    try {
      const priority = priorityRaw.split(',').map(s => s.trim()).filter(Boolean)
      const payload: Parameters<typeof updateSettings>[0] = {
        default_release_tag: tag.trim(),
        provider_priority_order: priority,
        tmdb_watch_region: region.trim(),
        tmdb_language: language.trim(),
        uploadrr_path: uploadrrPath.trim(),
        uploadrr_runtime_type: uploadrrRuntimeType,
        uploadrr_python_path: uploadrrPythonPath.trim(),
        uploadrr_timeout: uploadrrTimeout,
        uploadrr_allowed_roots: uploadrrAllowedRootsRaw,
      }
      if (newKey.trim()) payload.tmdb_api_key = newKey.trim()
      const updated = await updateSettings(payload)
      setSettings(updated)
      setTag(updated.default_release_tag)
      setPriorityRaw(updated.provider_priority_order.join(','))
      setRegion(updated.tmdb_watch_region)
      setLanguage(updated.tmdb_language)
      setNewKey('')
      setUploadrrPath(updated.uploadrr_path ?? '')
      setUploadrrRuntimeType(updated.uploadrr_runtime_type)
      setUploadrrPythonPath(updated.uploadrr_python_path ?? '')
      setUploadrrTimeout(updated.uploadrr_timeout)
      setUploadrrAllowedRootsRaw((updated.uploadrr_allowed_roots ?? []).join(','))
      setMsg({ ok: true, text: '✓ Configuración guardada' })
    } catch (e: unknown) {
      setMsg({ ok: false, text: `✗ ${e instanceof Error ? e.message : String(e)}` })
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p style={{ padding: 20, color: 'var(--text-muted)', fontSize: 13 }}>Cargando…</p>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 640 }}>
      {msg && (
        <div style={{
          padding: '10px 14px', borderRadius: 6, fontSize: 13,
          background: msg.ok ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
          border: `1px solid ${msg.ok ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)'}`,
          color: msg.ok ? '#86efac' : '#fca5a5',
        }}>
          {msg.text}
        </div>
      )}

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14 }}>TMDb</h3>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Estado de la API key</label>
          <div style={{ fontSize: 13 }}>
            {settings?.tmdb_api_key_configured
              ? <><span style={{ color: '#22c55e' }}>✓ Configurada</span>{settings.tmdb_api_key_masked && <code style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)' }}>{settings.tmdb_api_key_masked}</code>}</>
              : <span style={{ color: '#ef4444' }}>✗ No configurada</span>}
          </div>
        </div>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Nueva API key <span className="form-hint">(dejar vacío para mantener la actual)</span></label>
          <input
            type="password"
            className="form-input"
            value={newKey}
            onChange={e => setNewKey(e.target.value)}
            placeholder="sk-…"
            autoComplete="new-password"
          />
          <span className="form-hint">Usada para marcar providers disponibles en TMDb.</span>
        </div>
        <div style={{ marginBottom: 12 }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleTestTmdb}
            disabled={testingTmdb}
            type="button"
          >
            {testingTmdb ? 'Probando…' : 'Probar conexión'}
          </button>
          {tmdbTestResult && (
            <span style={{
              marginLeft: 10, fontSize: 12,
              color: tmdbTestResult.ok ? '#22c55e'
                : tmdbTestResult.status === 'not_configured' ? '#f59e0b'
                : '#ef4444',
            }}>
              {tmdbTestResult.ok ? '✓ Conectado'
                : tmdbTestResult.status === 'not_configured' ? '⚠ Sin configurar'
                : tmdbTestResult.status === 'invalid_key' ? '✗ API key inválida'
                : tmdbTestResult.status === 'timeout' ? '✗ Timeout'
                : `✗ ${tmdbTestResult.message}`}
            </span>
          )}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="form-group">
            <label className="form-label">Región</label>
            <input className="form-input" value={region} onChange={e => setRegion(e.target.value)} placeholder="ES" />
            <span className="form-hint">Código ISO de país para filtrar providers.</span>
          </div>
          <div className="form-group">
            <label className="form-label">Idioma</label>
            <input className="form-input" value={language} onChange={e => setLanguage(e.target.value)} placeholder="es-ES" />
          </div>
        </div>
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14 }}>Nomenclatura</h3>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Default release tag</label>
          <input className="form-input" value={tag} onChange={e => setTag(e.target.value)} placeholder="EMUWAREZ" />
          <span className="form-hint">Propuesta por defecto al generar el torrent name.</span>
        </div>
        <div className="form-group">
          <label className="form-label">Orden de providers (separados por coma)</label>
          <input
            className="form-input"
            value={priorityRaw}
            onChange={e => setPriorityRaw(e.target.value)}
            placeholder="AMZN,NF,DSNP,MAX,ATVP"
          />
          <span className="form-hint">Se usa para elegir automáticamente el provider cuando TMDb devuelve varios. Códigos válidos: AMZN, NF, DSNP, MAX, ATVP, HMAX, PCOK, MUBI, SKY…</span>
        </div>
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14 }}>Uploadrr</h3>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Ruta Uploadrr</label>
          <input className="form-input" value={uploadrrPath} onChange={e => setUploadrrPath(e.target.value)} placeholder="/opt/Uploadrr" />
          <span className="form-hint">Directorio que contiene upload.py (nunca se incluye dentro de la imagen Docker).</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="form-group">
            <label className="form-label">Runtime</label>
            <select
              className="form-input"
              value={uploadrrRuntimeType}
              onChange={e => setUploadrrRuntimeType(e.target.value as UploadrrRuntimeType)}
            >
              <option value="uploadrr_emu">uploadrr_emu (recomendado)</option>
              <option value="uploadrr_generic">uploadrr_generic</option>
            </select>
            <span className="form-hint">La ejecución controlada real solo está soportada para uploadrr_emu.</span>
          </div>
          <div className="form-group">
            <label className="form-label">Timeout (segundos)</label>
            <input
              type="number"
              min={1}
              className="form-input"
              value={uploadrrTimeout}
              onChange={e => setUploadrrTimeout(Number(e.target.value))}
            />
          </div>
        </div>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Python</label>
          <input className="form-input" value={uploadrrPythonPath} onChange={e => setUploadrrPythonPath(e.target.value)} placeholder="/usr/local/bin/python" />
          <span className="form-hint">Intérprete usado para ejecutar Uploadrr-EMU. En Docker: /usr/local/bin/python. En host: la ruta del venv de Uploadrr-EMU.</span>
        </div>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Allowed roots</label>
          <textarea
            className="form-input"
            rows={2}
            value={uploadrrAllowedRootsRaw}
            onChange={e => setUploadrrAllowedRootsRaw(e.target.value)}
            placeholder="/data/uploads/emu,/data/media"
          />
          <span className="form-hint">Rutas (separadas por coma) donde debe estar el archivo preparado antes de ejecutar Uploadrr-EMU. Vacío = usa hardlink_base.</span>
        </div>
        <div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleTestUploadrr}
            disabled={testingUploadrr}
            type="button"
          >
            {testingUploadrr ? 'Probando…' : 'Probar configuración'}
          </button>
          {uploadrrTestResult && (
            <span style={{
              marginLeft: 10, fontSize: 12,
              color: uploadrrTestResult.ok ? '#22c55e'
                : uploadrrTestResult.status === 'not_configured' ? '#f59e0b'
                : '#ef4444',
            }}>
              {uploadrrTestResult.ok
                ? (uploadrrTestResult.status === 'connected_no_config' ? '⚠ Ruta OK, sin config.yaml todavía' : '✓ Ruta y script encontrados')
                : `✗ ${uploadrrTestResult.message}`}
            </span>
          )}
        </div>
      </div>

      <div>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Guardando…' : 'Guardar configuración'}
        </button>
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
