import { useState, useEffect, useCallback, useRef } from 'react'
import { setUnsavedGuard, guardedLeave } from '../utils/unsavedGuard'
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
import { fetchSettings, updateSettings, type SettingsData } from '../api/settings'
import { testTmdbConnection, testEmuwarezConnection, testQbitConnection, testImghostConnection, type IntegrationTestResult } from '../api/integrationTests'
import { useCooldown } from '../hooks/useCooldown'
import { testDiscordNotification, testTelegramNotification } from '../api/notifications'
import { ProviderPriorityPicker } from '../components/ProviderPriorityPicker'
import { ServiceIcon } from '../components/ServiceIcon'
import { InfoIcon } from '../components/InfoIcon'
import { Favicon, domainOf } from '../components/Favicon'
import { SortableList, DragHandleIcon } from '../components/SortableList'
import { REGION_OPTIONS } from '../constants/regionLanguage'
import { CheckStatusIcon } from '../components/DetailCard'
import { testResultLabel, testResultColor, emuTestCooldownSeconds } from '../utils/integrationResult'
import { getMe, changeCredentials } from '../api/auth'
import { useTooltip, HoverTitle } from '../components/Tooltip'
import { isValidHttpUrl } from '../utils/validation'

type Tab = 'config' | 'notifications' | 'diagnostics' | 'backup' | 'maintenance'

// A tab exposes its save action so the page-header (top-right) can render the
// button, like the sync buttons in Biblioteca/Peticiones.
export interface SaveExpose {
  dirty: boolean
  saving: boolean
  onSave: () => void
  label: string
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

// Serialize the Config form's values so we can compare current vs. loaded and
// know whether there are unsaved changes. Array order is fixed on purpose.
function configSignature(v: {
  tag: string; providerOrder: string[]; region: string
  emuUsername: string; ignoreSpecials: boolean
  recentLimit: number; uploadMaxConcurrent: number; qbitUrl: string; qbitPort: string; qbitUser: string
  imgEnabled: string[]; allowedRoots: string
  newKey?: string; newEmuKey?: string; qbitPass?: string
  imgKeys?: Record<string, string>
}): string {
  return JSON.stringify([
    v.tag, v.providerOrder, v.region, v.emuUsername,
    v.ignoreSpecials, v.recentLimit, v.uploadMaxConcurrent, v.qbitUrl, v.qbitPort, v.qbitUser, v.imgEnabled, v.allowedRoots,
    v.newKey ?? '', v.newEmuKey ?? '', v.qbitPass ?? '', v.imgKeys ?? {},
  ])
}

function RemoveImgHostButton({ onClick }: { onClick: () => void }) {
  const { triggerProps, tooltipNode } = useTooltip('Quitar')
  return (
    <button className="btn btn-ghost btn-sm" style={{ fontSize: 13, padding: '2px 6px', color: 'var(--text-muted)' }}
      onClick={onClick} type="button" {...triggerProps}>✕{tooltipNode}</button>
  )
}

function RemoveMappingRuleButton({ onClick }: { onClick: () => void }) {
  const { triggerProps, tooltipNode } = useTooltip('Quitar regla')
  return (
    <button className="btn btn-ghost btn-sm" type="button" onClick={onClick} {...triggerProps}>✕{tooltipNode}</button>
  )
}

// ---------- Config tab ----------
function ConfigTab({ onExposeSave }: { onExposeSave: (a: SaveExpose | null) => void }) {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [testingTmdb, setTestingTmdb] = useState(false)
  const [tmdbTestResult, setTmdbTestResult] = useState<IntegrationTestResult | null>(null)
  const [testingEmu, setTestingEmu] = useState(false)
  const [emuTestResult, setEmuTestResult] = useState<IntegrationTestResult | null>(null)
  const emuCooldown = useCooldown()

  // Form state
  const [tag, setTag] = useState('')
  const [providerOrder, setProviderOrder] = useState<string[]>([])
  const [region, setRegion] = useState('')
  const [newKey, setNewKey] = useState('')
  const [newEmuKey, setNewEmuKey] = useState('')
  const [emuUsername, setEmuUsername] = useState('')
  const [ignoreSpecials, setIgnoreSpecials] = useState(true)
  const [recentLimit, setRecentLimit] = useState(100)
  const [uploadMaxConcurrent, setUploadMaxConcurrent] = useState(3)
  const [qbitUrl, setQbitUrl] = useState('')
  const [qbitPort, setQbitPort] = useState('8080')
  const [qbitUser, setQbitUser] = useState('')
  const [qbitPass, setQbitPass] = useState('')
  const [testingQbit, setTestingQbit] = useState(false)
  const [qbitTestResult, setQbitTestResult] = useState<IntegrationTestResult | null>(null)
  const [showQbitUser, setShowQbitUser] = useState(false)
  const qbitUserEyeTip = useTooltip(showQbitUser ? 'Ocultar usuario' : 'Mostrar usuario')
  // Image hosts
  const [imgEnabled, setImgEnabled] = useState<string[]>([])
  const [imgKeys, setImgKeys] = useState<Record<string, string>>({})
  const [imgTest, setImgTest] = useState<Record<string, IntegrationTestResult>>({})
  const [imgTesting, setImgTesting] = useState<string | null>(null)
  const [showAddImg, setShowAddImg] = useState(false)
  // Full displayed order of image hosts, always including imgbox (which may not
  // live in the saved list yet). imgbox is reorderable like the rest.
  const imgOrder = () => (imgEnabled.includes('imgbox') ? [...imgEnabled] : ['imgbox', ...imgEnabled])
  // Uploadrr sandboxing: folder(s) where THIS container reaches the media,
  // comma-separated. Empty means real uploads fail closed until it's set.
  const [allowedRoots, setAllowedRoots] = useState('')

  // Unsaved-changes tracking: compare current form values to the loaded ones.
  const [baseline, setBaseline] = useState('')
  const currentSig = configSignature({
    tag, providerOrder, region, emuUsername,
    ignoreSpecials, recentLimit, uploadMaxConcurrent, qbitUrl, qbitPort, qbitUser, imgEnabled, allowedRoots,
    newKey, newEmuKey, qbitPass, imgKeys,
  })
  const dirty = baseline !== '' && currentSig !== baseline
  const dirtyRef = useRef(false)
  dirtyRef.current = dirty
  useEffect(() => {
    setUnsavedGuard(() => dirtyRef.current)
    return () => setUnsavedGuard(null)
  }, [])

  // Expose the save action to the page-header (top-right button). onSave goes
  // through a ref so it always runs with the latest form values.
  const saveRef = useRef<() => void>(() => {})
  saveRef.current = () => { void handleSave() }
  const stableSave = useRef(() => saveRef.current()).current
  useEffect(() => {
    onExposeSave({ dirty, saving, onSave: stableSave, label: 'Guardar configuración' })
  }, [dirty, saving, onExposeSave, stableSave])
  useEffect(() => () => onExposeSave(null), [onExposeSave])

  async function handleTestImghost(hostId: string) {
    setImgTesting(hostId)
    try {
      const r = await testImghostConnection(hostId, imgKeys[hostId]?.trim() || undefined)
      setImgTest(p => ({ ...p, [hostId]: r }))
    } catch {
      setImgTest(p => ({ ...p, [hostId]: { ok: false, service: 'imghost', status: 'connection_error', message: 'Error al contactar con el servidor' } }))
    } finally { setImgTesting(null) }
  }

  function toggleImgHost(hostId: string) {
    setImgEnabled(p => p.includes(hostId) ? p.filter(x => x !== hostId) : [...p, hostId])
  }

  useEffect(() => {
    fetchSettings()
      .then(s => {
        setSettings(s)
        setTag(s.default_release_tag)
        setProviderOrder(s.provider_priority_order)
        setRegion(s.tmdb_watch_region)
        setEmuUsername(s.emu_username ?? '')
        setIgnoreSpecials(s.series_ignore_specials ?? true)
        setRecentLimit(s.recent_activity_limit ?? 100)
        setUploadMaxConcurrent(s.upload_max_concurrent ?? 1)
        setQbitUrl(s.qbit_url ?? '')
        setQbitPort(s.qbit_port ?? '8080')
        setQbitUser(s.qbit_username ?? '')
        setImgEnabled(s.image_hosts_enabled ?? [])
        setAllowedRoots((s.uploadrr_allowed_roots ?? []).join(', '))
        setBaseline(configSignature({
          tag: s.default_release_tag, providerOrder: s.provider_priority_order,
          region: s.tmdb_watch_region,
          emuUsername: s.emu_username ?? '',
          ignoreSpecials: s.series_ignore_specials ?? true, recentLimit: s.recent_activity_limit ?? 100,
          uploadMaxConcurrent: s.upload_max_concurrent ?? 1,
          qbitUrl: s.qbit_url ?? '', qbitPort: s.qbit_port ?? '8080', qbitUser: s.qbit_username ?? '',
          imgEnabled: s.image_hosts_enabled ?? [],
          allowedRoots: (s.uploadrr_allowed_roots ?? []).join(', '),
        }))
      })
      .catch(() => setMsg({ ok: false, text: 'Error cargando configuración' }))
      .finally(() => setLoading(false))
  }, [])

  async function handleTestTmdb() {
    setTestingTmdb(true)
    setTmdbTestResult(null)
    try {
      const params: { api_key?: string; region?: string } = {}
      if (newKey.trim()) params.api_key = newKey.trim()
      if (region.trim()) params.region = region.trim()
      const r = await testTmdbConnection(params)
      setTmdbTestResult(r)
    } catch {
      setTmdbTestResult({ ok: false, service: 'tmdb', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setTestingTmdb(false)
    }
  }

  async function handleTestEmu() {
    if (emuCooldown.active) return
    setTestingEmu(true)
    setEmuTestResult(null)
    try {
      const params: { api_key?: string } = {}
      if (newEmuKey.trim()) params.api_key = newEmuKey.trim()
      const r = await testEmuwarezConnection(params)
      setEmuTestResult(r)
      emuCooldown.start(emuTestCooldownSeconds(r))
    } catch {
      setEmuTestResult({ ok: false, service: 'emuwarez', status: 'connection_error', message: 'Error al contactar con el servidor' })
      emuCooldown.start(60)
    } finally {
      setTestingEmu(false)
    }
  }

  async function handleTestQbit() {
    setTestingQbit(true)
    setQbitTestResult(null)
    try {
      const r = await testQbitConnection({
        url: qbitUrl.trim() || undefined,
        port: qbitPort.trim() || undefined,
        username: qbitUser.trim() || undefined,
        password: qbitPass.trim() || undefined,
      })
      setQbitTestResult(r)
    } catch {
      setQbitTestResult({ ok: false, service: 'qbittorrent', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setTestingQbit(false)
    }
  }

  async function handleSave() {
    if (qbitUrl.trim() && !isValidHttpUrl(qbitUrl)) {
      setMsg({ ok: false, text: 'La URL de qBittorrent debe empezar por http:// o https:// e incluir un host válido' })
      return
    }
    setSaving(true)
    setMsg(null)
    try {
      const payload: Parameters<typeof updateSettings>[0] = {
        default_release_tag: tag.trim(),
        provider_priority_order: providerOrder,
        tmdb_watch_region: region.trim(),
        // No longer a user-facing toggle — always on.
        tmdb_localize_series_titles: true,
        emu_username: emuUsername.trim(),
        series_ignore_specials: ignoreSpecials,
        recent_activity_limit: recentLimit,
        upload_max_concurrent: uploadMaxConcurrent,
        qbit_url: qbitUrl.trim(),
        qbit_port: qbitPort.trim(),
        qbit_username: qbitUser.trim(),
        image_hosts_enabled: imgEnabled,
        uploadrr_allowed_roots: allowedRoots,
      }
      if (newKey.trim()) payload.tmdb_api_key = newKey.trim()
      if (newEmuKey.trim()) payload.emu_api_key = newEmuKey.trim()
      if (qbitPass.trim()) payload.qbit_password = qbitPass.trim()
      const keysToSend = Object.fromEntries(Object.entries(imgKeys).filter(([, v]) => v.trim()))
      if (Object.keys(keysToSend).length) payload.image_host_keys = keysToSend
      const updated = await updateSettings(payload)
      setSettings(updated)
      setTag(updated.default_release_tag)
      setProviderOrder(updated.provider_priority_order)
      setRegion(updated.tmdb_watch_region)
      setEmuUsername(updated.emu_username ?? '')
      setIgnoreSpecials(updated.series_ignore_specials ?? true)
      setRecentLimit(updated.recent_activity_limit ?? 100)
      setUploadMaxConcurrent(updated.upload_max_concurrent ?? 1)
      setQbitUrl(updated.qbit_url ?? '')
      setQbitPort(updated.qbit_port ?? '8080')
      setQbitUser(updated.qbit_username ?? '')
      setQbitPass('')
      setImgEnabled(updated.image_hosts_enabled ?? [])
      setImgKeys({})
      setNewKey('')
      setNewEmuKey('')
      setAllowedRoots((updated.uploadrr_allowed_roots ?? []).join(', '))
      setBaseline(configSignature({
        tag: updated.default_release_tag, providerOrder: updated.provider_priority_order,
        region: updated.tmdb_watch_region,
        emuUsername: updated.emu_username ?? '',
        ignoreSpecials: updated.series_ignore_specials ?? true, recentLimit: updated.recent_activity_limit ?? 100,
        uploadMaxConcurrent: updated.upload_max_concurrent ?? 1,
        qbitUrl: updated.qbit_url ?? '', qbitPort: updated.qbit_port ?? '8080', qbitUser: updated.qbit_username ?? '',
        imgEnabled: updated.image_hosts_enabled ?? [],
        allowedRoots: (updated.uploadrr_allowed_roots ?? []).join(', '),
      }))
      setMsg({ ok: true, text: '✓ Configuración guardada' })
    } catch (e: unknown) {
      setMsg({ ok: false, text: `✗ ${e instanceof Error ? e.message : String(e)}` })
    } finally {
      setSaving(false)
      setTimeout(() => setMsg(null), 5000)  // no dejar el mensaje empujando las tarjetas
    }
  }

  if (loading) return <p style={{ padding: 20, color: 'var(--text-muted)', fontSize: 13 }}>Cargando…</p>

  return (
    <div data-tour="settings-content" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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

      <div className="settings-config-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 16, alignItems: 'stretch' }}>
      <AccountCard />

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="emu" size={18} /> Emuwarez
        </h3>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Estado de la API key</label>
          <div style={{ fontSize: 13 }}>
            {settings?.emu_api_key_configured
              ? <><span style={{ color: '#22c55e', display: 'inline-flex', alignItems: 'center', gap: 5 }}><CheckStatusIcon status="ok" /> Configurada</span>{settings.emu_api_key_masked && <code style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)' }}>{settings.emu_api_key_masked}</code>}</>
              : <span style={{ color: '#ef4444' }}>✗ No configurada</span>}
          </div>
        </div>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Nueva API key <span className="form-hint">(dejar vacío para mantener la actual)</span></label>
          <input
            type="password"
            className="form-input"
            value={newEmuKey}
            onChange={e => setNewEmuKey(e.target.value)}
            placeholder="API key de Emuwarez"
            autoComplete="new-password"
          />
          <span className="form-hint">Usada para leer el catálogo y las peticiones de Emuwarez.</span>
        </div>
        <div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleTestEmu}
            disabled={testingEmu || emuCooldown.active}
            type="button"
          >
            {testingEmu ? 'Probando…' : emuCooldown.active ? `Espera ${emuCooldown.remaining}s` : 'Probar conexión'}
          </button>
          {emuTestResult && (
            <span style={{ marginLeft: 10, fontSize: 12, color: testResultColor(emuTestResult) }}>
              {testResultLabel(emuTestResult)}
            </span>
          )}
        </div>
        <div className="form-group" style={{ marginTop: 14 }}>
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Mi usuario de eMuwarez
            <InfoIcon text="Tu nombre de usuario en eMuwarez. Se usa para reconocer cuáles de todas las peticiones descargadas las has creado tú, y así poder mostrártelas en 'Mis peticiones'." />
          </label>
          <input
            className="form-input"
            value={emuUsername}
            onChange={e => setEmuUsername(e.target.value)}
            placeholder="Tu nombre de usuario en eMuwarez"
          />
        </div>
        <div className="form-group" style={{ marginTop: 14 }}>
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Tag del grupo de subida
            <InfoIcon text="El tag que va tras el último «-» en el nombre del torrent (tu grupo/usuario)." />
          </label>
          <input className="form-input" value={tag} onChange={e => setTag(e.target.value)} placeholder="EMUWAREZ" />
        </div>
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="tmdb" size={18} /> TMDb
        </h3>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Estado de la API key</label>
          <div style={{ fontSize: 13 }}>
            {settings?.tmdb_api_key_configured
              ? <><span style={{ color: '#22c55e', display: 'inline-flex', alignItems: 'center', gap: 5 }}><CheckStatusIcon status="ok" /> Configurada</span>{settings.tmdb_api_key_masked && <code style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)' }}>{settings.tmdb_api_key_masked}</code>}</>
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
            placeholder="API key de TMDb"
            autoComplete="new-password"
          />
          <span className="form-hint">Usada para marcar proveedores disponibles en TMDb y para traducir los títulos de las series al español (eMuwarez exige el título siempre en español).</span>
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
            <span style={{ marginLeft: 10, fontSize: 12, color: testResultColor(tmdbTestResult) }}>
              {testResultLabel(tmdbTestResult)}
            </span>
          )}
        </div>
        <div className="form-group">
          <label className="form-label">Región</label>
          <select className="form-input form-select" value={region} onChange={e => setRegion(e.target.value)}>
            {REGION_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label} ({o.value})</option>)}
          </select>
          <span className="form-hint">País para filtrar proveedores.</span>
        </div>
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="qbittorrent" size={18} /> qBittorrent
        </h3>
        <div className="form-group" style={{ marginBottom: 10 }}>
          <label className="form-label">URL del WebUI</label>
          <input className="form-input" value={qbitUrl} onChange={e => setQbitUrl(e.target.value)} placeholder="http://127.0.0.1" />
        </div>
        <div className="form-group" style={{ marginBottom: 10 }}>
          <label className="form-label">Puerto</label>
          <input className="form-input" value={qbitPort} onChange={e => setQbitPort(e.target.value)} placeholder="8080" />
        </div>
        <div className="form-group" style={{ marginBottom: 10 }}>
          <label className="form-label">Usuario</label>
          <div style={{ position: 'relative' }}>
            <input
              className="form-input"
              type={showQbitUser ? 'text' : 'password'}
              value={qbitUser}
              onChange={e => setQbitUser(e.target.value)}
              placeholder="admin"
              autoComplete="off"
              style={{ paddingRight: 38 }}
            />
            <button
              type="button"
              onClick={() => setShowQbitUser(s => !s)}
              aria-label={showQbitUser ? 'Ocultar usuario' : 'Mostrar usuario'}
              style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', padding: 2 }}
              {...qbitUserEyeTip.triggerProps}
            >
              {qbitUserEyeTip.tooltipNode}
              {showQbitUser ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                  <line x1="1" y1="1" x2="23" y2="23" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
            </button>
          </div>
        </div>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Contraseña <span className="form-hint">(dejar vacío para mantener la actual)</span></label>
          <input type="password" className="form-input" value={qbitPass} onChange={e => setQbitPass(e.target.value)} placeholder={settings?.qbit_password_configured ? '••••••••' : 'Contraseña del WebUI'} autoComplete="new-password" />
        </div>
        <div>
          <button className="btn btn-secondary btn-sm" onClick={handleTestQbit} disabled={testingQbit} type="button">
            {testingQbit ? 'Probando…' : 'Probar conexión'}
          </button>
          {qbitTestResult && (
            <span style={{ marginLeft: 10, fontSize: 12, color: testResultColor(qbitTestResult) }}>
              {testResultLabel(qbitTestResult)}
            </span>
          )}
        </div>
      </div>

      <div className="placeholder-card provider-card">
        <h3 style={{ marginTop: 0, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" aria-hidden>
            <rect x="2.5" y="5" width="19" height="14" rx="2.5" stroke="#8b5cf6" strokeWidth="1.6" />
            <path d="M10 9.2v5.6l4.5-2.8z" fill="#8b5cf6" />
          </svg>
          Proveedores de vídeo
        </h3>
        <span className="form-hint" style={{ display: 'block', marginBottom: 6 }}>
          Se usa para elegir automáticamente el proveedor cuando TMDb devuelve varios. Arrastra para reordenar. El icono de cada uno enlaza a su web oficial.
        </span>
        <div className="form-group provider-card__body">
          <label className="form-label">Prioridad de proveedores</label>
          <ProviderPriorityPicker order={providerOrder} onChange={setProviderOrder} />
        </div>
      </div>

      <div className="placeholder-card provider-card">
        <h3 style={{ marginTop: 0, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="imghost" size={18} /> Proveedores de imágenes
        </h3>
        <span className="form-hint" style={{ display: 'block', marginBottom: 12 }}>
          Para las capturas que Uploadrr sube junto al torrent. Se prueban por orden de prioridad; arrastra para reordenar. <strong>imgbox</strong> es el fallback sin API key.
        </span>
        <label className="form-label" style={{ display: 'block', marginBottom: 8 }}>Prioridad de proveedores</label>
        {(() => {
          const avail = settings?.image_hosts_available ?? []
          const configuredIds = imgOrder()
          const notConfigured = avail.filter(h => !configuredIds.includes(h.id))
          const metaOf = (id: string) => avail.find(h => h.id === id)
          return (
            <>
            <div className="provider-card__body">
              <div className="provider-card__list" style={{ maxHeight: 234 }}>
                <SortableList ids={configuredIds} onChange={setImgEnabled} gap={8} renderRow={(id, idx, { dragging, handleProps }) => {
                  const h = metaOf(id); if (!h) return null
                  const isDefault = id === 'imgbox'
                  const t = imgTest[id]
                  return (
                    <div style={{
                      padding: '8px 10px', borderRadius: 8,
                      background: dragging ? 'rgba(37,99,235,0.15)' : 'rgba(139,92,246,0.06)',
                      border: `1px solid ${dragging ? 'var(--text-accent, #2563eb)' : 'var(--border)'}`,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ color: 'var(--text-muted)', fontSize: 11, width: 16, textAlign: 'center' }}>{idx + 1}</span>
                        <HoverTitle
                          as="span"
                          tip="Arrastrar para reordenar"
                          onMouseDown={handleProps.onMouseDown}
                          onMouseUp={handleProps.onMouseUp}
                          className="drag-handle"
                          style={{ ...handleProps.style, color: 'var(--text-accent)', width: 16, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginLeft: 8, marginRight: 8 }}
                        ><DragHandleIcon /></HoverTitle>
                        <a href={h.url} target="_blank" rel="noreferrer" title={`Abrir ${h.label}`}
                          onClick={e => e.stopPropagation()} onMouseDown={e => e.stopPropagation()}
                          style={{ display: 'inline-flex' }}>
                          <Favicon domain={domainOf(h.url)} src={h.favicon} size={15} background="#fff" fallback={<ServiceIcon type="imghost" size={15} />} />
                        </a>
                        <span style={{ fontSize: 13, fontWeight: 500 }}>{h.label}</span>
                        {isDefault && <span className="badge status-available" style={{ fontSize: 10 }}>por defecto</span>}
                        {h.needs_key && <span className="badge nom-na" style={{ fontSize: 10 }}>API key</span>}
                        <button className="btn btn-secondary btn-sm" style={{ marginLeft: 'auto', fontSize: 11, padding: '2px 8px' }}
                          onClick={() => handleTestImghost(id)} disabled={imgTesting === id} type="button">
                          {imgTesting === id ? 'Probando…' : 'Probar'}
                        </button>
                        {!isDefault && (
                          <RemoveImgHostButton onClick={() => toggleImgHost(id)} />
                        )}
                      </div>
                      {h.needs_key && (
                        <input type="password" className="form-input" style={{ marginTop: 6 }} autoComplete="new-password"
                          value={imgKeys[id] ?? ''} onChange={e => setImgKeys(p => ({ ...p, [id]: e.target.value }))}
                          placeholder={settings?.image_host_keys_configured?.includes(id) ? '•••••••• (guardada, vacío para mantener)' : `API key de ${h.label}`} />
                      )}
                      {t && <div style={{ fontSize: 11, marginTop: 4, color: testResultColor(t) }}>{testResultLabel(t)}</div>}
                    </div>
                  )
                }} />
              </div>
              {notConfigured.length > 0 && (
                <button className="btn btn-secondary btn-sm provider-card__add-btn" onClick={() => setShowAddImg(true)} type="button">
                  + Añadir proveedor ({notConfigured.length})
                </button>
              )}
            </div>
              {showAddImg && (
                <div className="modal-overlay" onClick={() => setShowAddImg(false)}>
                  <div className="modal-panel" onClick={e => e.stopPropagation()} style={{ maxWidth: 480 }}>
                    <div className="modal-header">
                      <h2 className="modal-title">Añadir proveedor de imágenes</h2>
                      <button className="modal-close" onClick={() => setShowAddImg(false)}>✕</button>
                    </div>
                    <div className="modal-body">
                      {notConfigured.length === 0 ? (
                        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>Ya están todos añadidos.</p>
                      ) : (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 6, maxHeight: '55vh', overflowY: 'auto' }}>
                          {notConfigured.map(h => (
                            <button key={h.id} className="btn btn-ghost btn-sm" type="button"
                              style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-start', justifySelf: 'start', fontSize: 12 }}
                              onClick={() => toggleImgHost(h.id)}>
                              <Favicon domain={domainOf(h.url)} src={h.favicon} size={16} background="#fff" fallback={<ServiceIcon type="imghost" size={16} />} /> {h.label} {h.needs_key && <span className="badge nom-na" style={{ fontSize: 9 }}>API key</span>}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </>
          )
        })()}
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="1.75" aria-hidden>
            <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
          </svg>
          Acceso a la biblioteca
          <InfoIcon text="Antes de subir un archivo, la app comprueba que su ruta está dentro de una de estas carpetas: una red de seguridad para que nunca se toque un archivo fuera de donde debería. Si la dejas vacía, las subidas reales se bloquearán hasta que la rellenes." />
        </h3>
        <p className="form-hint" style={{ marginTop: 0, marginBottom: 12 }}>
          La carpeta donde este contenedor accede a tu biblioteca (el punto de montaje del volumen, no necesariamente
          el mismo que reportan Radarr/Sonarr). Por ejemplo: <code>/data</code> si lo montas igual que Radarr/Sonarr.
          Varias rutas separadas por comas.
        </p>
        <div className="form-group">
          <label className="form-label">Rutas permitidas</label>
          <input
            className="form-input"
            value={allowedRoots}
            onChange={e => setAllowedRoots(e.target.value)}
            placeholder="/data"
          />
        </div>
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="1.75" aria-hidden>
            <line x1="4" y1="21" x2="4" y2="14" /><line x1="4" y1="10" x2="4" y2="3" />
            <line x1="12" y1="21" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="3" />
            <line x1="20" y1="21" x2="20" y2="16" /><line x1="20" y1="12" x2="20" y2="3" />
            <line x1="1" y1="14" x2="7" y2="14" /><line x1="9" y1="8" x2="15" y2="8" /><line x1="17" y1="16" x2="23" y2="16" />
          </svg>
          Otros
        </h3>
        <div className="form-group">
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Máximo de Subidas en Paralelo
            <InfoIcon text="Cuántas subidas pueden hacer a la vez el hasheo del torrent y la transferencia a eMuwarez, la parte más pesada del proceso. Las demás esperan su turno en cola y arrancan solas en cuanto se libera un hueco. Sin límite las deja correr todas a la vez." />
          </label>
          <select className="form-input form-select" value={uploadMaxConcurrent} onChange={e => setUploadMaxConcurrent(Number(e.target.value))}>
            <option value={0}>Sin límite</option>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Máximo de Elementos en Recomendaciones
            <InfoIcon text="Cuántos elementos como máximo se muestran en Recomendaciones. Sin límite los muestra todos." />
          </label>
          <select className="form-input form-select" value={recentLimit} onChange={e => setRecentLimit(Number(e.target.value))}>
            <option value={0}>Sin límite</option>
            {[50, 100, 150, 200, 250, 300].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Ignorar Temporadas especiales
            <InfoIcon text="Excluye la temporada especial (temporada 0) del estado global de una serie. Si tienes todas las temporadas y capítulos salvo los especiales, la serie aparece como completa en las columnas Estado y eMuwarez de la Biblioteca. Sus atributos consolidados (resolución, source, códecs, audio y subtítulos) se calculan ignorando los especiales, y en el Panel sus capítulos faltantes no cuentan como faltantes." />
          </label>
          <select className="form-input form-select" value={ignoreSpecials ? 'true' : 'false'} onChange={e => setIgnoreSpecials(e.target.value === 'true')}>
            <option value="true">Sí</option>
            <option value="false">No</option>
          </select>
        </div>
      </div>
      </div>
    </div>
  )
}

// ---------- Account (username/password) card ----------
// Self-contained: its own "Guardar" instead of joining ConfigTab's shared
// save button — changing credentials always needs the current password
// re-entered, so it can't silently ride along with the rest of the form.
function AccountCard() {
  const [username, setUsername] = useState('')
  const [newUsername, setNewUsername] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => { getMe().then(u => setUsername(u.username)).catch(() => {}) }, [])

  const dirty = newUsername.trim() !== '' || newPassword !== ''

  async function handleSave() {
    setMsg(null)
    if (!currentPassword) { setMsg({ ok: false, text: 'Introduce tu contraseña actual para confirmar el cambio.' }); return }
    if (!dirty) { setMsg({ ok: false, text: 'No hay ningún cambio que guardar.' }); return }
    setSaving(true)
    try {
      const resp = await changeCredentials({
        current_password: currentPassword,
        new_username: newUsername.trim() || undefined,
        new_password: newPassword || undefined,
      })
      setUsername(resp.username)
      setNewUsername('')
      setNewPassword('')
      setCurrentPassword('')
      setMsg({ ok: true, text: '✓ Credenciales actualizadas correctamente.' })
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="placeholder-card">
      <h3 style={{ marginTop: 0, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
        <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="1.75" aria-hidden>
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg> Cuenta
      </h3>
      <p className="form-hint" style={{ marginTop: 0, marginBottom: 14 }}>
        Cambia el usuario y/o la contraseña con la que inicias sesión en esta aplicación.
      </p>
      <div className="form-group" style={{ marginBottom: 12 }}>
        <label className="form-label">Usuario actual</label>
        <input className="form-input" value={username || '…'} disabled />
      </div>
      <div className="form-group" style={{ marginBottom: 12 }}>
        <label className="form-label">Nuevo usuario <span className="form-hint">(dejar vacío para no cambiarlo)</span></label>
        <input className="form-input" value={newUsername} onChange={e => setNewUsername(e.target.value)} placeholder={username} autoComplete="off" />
      </div>
      <div className="form-group" style={{ marginBottom: 12 }}>
        <label className="form-label">Nueva contraseña <span className="form-hint">(dejar vacío para no cambiarla)</span></label>
        <input type="password" className="form-input" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Nueva contraseña" autoComplete="new-password" />
      </div>
      <div className="form-group" style={{ marginBottom: 14 }}>
        <label className="form-label">Contraseña actual <span className="form-hint">(obligatoria para confirmar)</span></label>
        <input type="password" className="form-input" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} placeholder="Tu contraseña actual" autoComplete="current-password" />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving || !dirty}>
          {saving ? 'Guardando…' : 'Guardar cambios'}
        </button>
        {msg && <span style={{ fontSize: 12.5, color: msg.ok ? '#22c55e' : '#ef4444' }}>{msg.text}</span>}
      </div>
    </div>
  )
}

// ---------- Path mappings card (library.path_mappings only) ----------
// Self-contained like AccountCard: its own load/save, untouched by
// ConfigTab's dirty-tracking or "Guardar configuración" button. PUT /settings
// only writes fields it's given, so saving here never touches anything else.
function PathMappingsCard() {
  const [mappings, setMappings] = useState<{ from: string; to: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [baseline, setBaseline] = useState('[]')

  useEffect(() => {
    fetchSettings()
      .then(s => {
        const m = s.path_mappings ?? []
        setMappings(m)
        setBaseline(JSON.stringify(m))
      })
      .finally(() => setLoading(false))
  }, [])

  const dirty = JSON.stringify(mappings) !== baseline

  async function handleSave() {
    setSaving(true)
    setMsg(null)
    try {
      const cleaned = mappings.map(m => ({ from: m.from.trim(), to: m.to.trim() })).filter(m => m.from && m.to)
      const updated = await updateSettings({ path_mappings: cleaned })
      const m = updated.path_mappings ?? []
      setMappings(m)
      setBaseline(JSON.stringify(m))
      setMsg({ ok: true, text: '✓ Mapeo de rutas guardado' })
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="placeholder-card">
      <h3 style={{ marginTop: 0, marginBottom: 6 }}>Mapeo de rutas (biblioteca remota)</h3>
      <p className="form-hint" style={{ marginTop: 0, marginBottom: 12 }}>
        Traduce la ruta que reporta Radarr/Sonarr a la ruta donde la app alcanza el archivo
        (monta la biblioteca por SSHFS/NFS/SMB donde quieras). Se aplica al leer MediaInfo,
        verificar y subir. Sin reglas, no cambia nada.
      </p>
      {loading ? (
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Cargando…</p>
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {mappings.length === 0 && (
              <span className="form-hint">No hay reglas. Añade una para acceder a una biblioteca remota.</span>
            )}
            {mappings.map((m, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <input
                  className="form-input" style={{ flex: 1, minWidth: 200 }}
                  value={m.from} placeholder="Ruta de Radarr/Sonarr: /data/media"
                  onChange={e => setMappings(p => p.map((x, j) => j === i ? { ...x, from: e.target.value } : x))}
                />
                <span style={{ color: 'var(--text-muted)' }}>→</span>
                <input
                  className="form-input" style={{ flex: 1, minWidth: 200 }}
                  value={m.to} placeholder="Ruta local: /home/alvaro/mnt/emu-media"
                  onChange={e => setMappings(p => p.map((x, j) => j === i ? { ...x, to: e.target.value } : x))}
                />
                <RemoveMappingRuleButton onClick={() => setMappings(p => p.filter((_, j) => j !== i))} />
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
            <button className="btn btn-secondary btn-sm" type="button"
              onClick={() => setMappings(p => [...p, { from: '', to: '' }])}>+ Añadir regla</button>
            <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving || !dirty}>
              {saving ? 'Guardando…' : 'Guardar cambios'}
            </button>
            {msg && <span style={{ fontSize: 12.5, color: msg.ok ? '#22c55e' : '#ef4444' }}>{msg.text}</span>}
          </div>
        </>
      )}
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
                <tr key={String(k)} style={{ borderBottom: '1px solid var(--border)' }}>
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
      <PathMappingsCard />
    </div>
  )
}

// ---------- Backup tab ----------
function BackupTab({ status, onRefresh }: { status: MaintenanceStatus | null; onRefresh: () => void }) {
  const [backups, setBackups] = useState<BackupInfo[]>([])
  const [backupDir, setBackupDir] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [restorePath, setRestorePath] = useState('')
  const [restoreConfirm, setRestoreConfirm] = useState('')

  // Show a transient message that clears itself after 5s (so it doesn't keep
  // pushing the cards down).
  const showMessage = useCallback((ok: boolean, text: string) => {
    setMessage({ ok, text })
    setTimeout(() => setMessage(null), 5000)
  }, [])

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
    setMessage(null)
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

  async function handleRestore(dry: boolean) {
    if (!restorePath) { showMessage(false, 'Introduce la ruta del backup'); return }
    if (!dry && restoreConfirm !== 'RESTAURAR_CONFIG') {
      showMessage(false, 'Escribe RESTAURAR_CONFIG para confirmar'); return
    }
    setBusy(true)
    setMessage(null)
    try {
      const r = await restoreBackup(restorePath, {
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
        {backups.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No hay backups.</p>
        ) : (
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Nombre', 'Tamaño', 'Fecha'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '4px 8px', borderBottom: '1px solid var(--border)', color: 'var(--text-secondary)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {backups.map(b => (
                <tr key={b.path} style={{ borderBottom: '1px solid var(--border)' }}>
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
          Elige uno de los backups existentes en <code>{backupDir || '…'}</code>.
        </p>
        <select
          className="form-input form-select"
          value={restorePath}
          onChange={e => setRestorePath(e.target.value)}
          style={{ width: '100%', marginBottom: 8 }}
        >
          <option value="">Selecciona un backup…</option>
          {backups.map(b => (
            <option key={b.path} value={b.path}>{b.name} ({formatBytes(b.size_bytes)})</option>
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

// ---------- Maintenance tab ----------
function MaintenanceTab() {
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState<{ key: string; ok: boolean; text: string }[]>([])
  const [vacuumConfirm, setVacuumConfirm] = useState('')
  const [cleanupConfirm, setCleanupConfirm] = useState('')
  const [cleanupDays, setCleanupDays] = useState(30)

  function addResult(key: string, ok: boolean, text: string) {
    const id = `${key}-${Date.now()}-${Math.random().toString(36).slice(2)}`
    setResults(prev => [{ key: id, ok, text }, ...prev.slice(0, 9)])
    // Auto-dismiss after 5s so the message doesn't keep pushing the cards.
    setTimeout(() => setResults(prev => prev.filter(r => r.key !== id)), 5000)
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
        <button className="btn btn-secondary" onClick={handleExportSettings} disabled={busy}>Exportar ajustes (JSON)</button>
      </div>

      <div className="placeholder-card">
        <h3>Integridad de la base de datos</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 10px' }}>Ejecuta <code>PRAGMA integrity_check</code> (solo lectura).</p>
        <button className="btn btn-secondary" onClick={handleIntegrity} disabled={busy}>Verificar integridad</button>
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
          <button className="btn btn-secondary" onClick={() => handleVacuum(true)} disabled={busy}>Previsualizar</button>
          <button className="btn btn-danger" onClick={() => handleVacuum(false)} disabled={busy}>Ejecutar VACUUM</button>
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
          <button className="btn btn-secondary" onClick={() => handleCleanup(true)} disabled={busy}>Previsualizar</button>
          <button className="btn btn-danger" onClick={() => handleCleanup(false)} disabled={busy}>Limpiar logs</button>
        </div>
      </div>
    </div>
  )
}

// Per-channel checkbox list: which event types this channel forwards.
function EventPicker({ title, eventTypes, selected, disabled, onToggle }: {
  title: string
  eventTypes: { code: string; label: string }[]
  selected: string[]
  disabled: boolean
  onToggle: (code: string, checked: boolean) => void
}) {
  if (eventTypes.length === 0) return null
  return (
    <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--border)', opacity: disabled ? 0.5 : 1 }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>{title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {eventTypes.map(ev => (
          <label key={ev.code} className="checkbox-label" style={{ fontSize: 13 }}>
            <input
              type="checkbox"
              checked={selected.includes(ev.code)}
              disabled={disabled}
              onChange={e => onToggle(ev.code, e.target.checked)}
            /> {ev.label}
          </label>
        ))}
      </div>
    </div>
  )
}

function notifSignature(v: {
  uiEnabled: boolean; uiEvents: string[]
  discordEnabled: boolean; discordWebhook?: string; telegramEnabled: boolean
  telegramToken?: string; telegramChatId: string; discordEvents: string[]; telegramEvents: string[]
}): string {
  return JSON.stringify([
    v.uiEnabled, v.uiEvents,
    v.discordEnabled, v.discordWebhook ?? '', v.telegramEnabled, v.telegramToken ?? '',
    v.telegramChatId, v.discordEvents, v.telegramEvents,
  ])
}

// ---------- Notifications tab ----------
function NotificationsTab({ onExposeSave }: { onExposeSave: (a: SaveExpose | null) => void }) {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const [discordEnabled, setDiscordEnabled] = useState(false)
  const [discordWebhook, setDiscordWebhook] = useState('')
  const [testingDiscord, setTestingDiscord] = useState(false)
  const [discordResult, setDiscordResult] = useState<IntegrationTestResult | null>(null)

  const [telegramEnabled, setTelegramEnabled] = useState(false)
  const [telegramToken, setTelegramToken] = useState('')
  const [telegramChatId, setTelegramChatId] = useState('')
  const [testingTelegram, setTestingTelegram] = useState(false)
  const [telegramResult, setTelegramResult] = useState<IntegrationTestResult | null>(null)

  // In-app bell ("UI" card): a configurable channel like Discord/Telegram, but
  // on by default and without credentials.
  const [uiEnabled, setUiEnabled] = useState(true)
  const [uiEvents, setUiEvents] = useState<string[]>([])

  const [eventTypes, setEventTypes] = useState<{ code: string; label: string }[]>([])
  const [discordEvents, setDiscordEvents] = useState<string[]>([])
  const [telegramEvents, setTelegramEvents] = useState<string[]>([])

  const [baseline, setBaseline] = useState('')
  const currentSig = notifSignature({
    uiEnabled, uiEvents,
    discordEnabled, discordWebhook, telegramEnabled, telegramToken, telegramChatId, discordEvents, telegramEvents,
  })
  const dirty = baseline !== '' && currentSig !== baseline
  const dirtyRef = useRef(false)
  dirtyRef.current = dirty
  useEffect(() => {
    setUnsavedGuard(() => dirtyRef.current)
    return () => setUnsavedGuard(null)
  }, [])

  const saveRef = useRef<() => void>(() => {})
  saveRef.current = () => { void handleSave() }
  const stableSave = useRef(() => saveRef.current()).current
  useEffect(() => {
    onExposeSave({ dirty, saving, onSave: stableSave, label: 'Guardar notificaciones' })
  }, [dirty, saving, onExposeSave, stableSave])
  useEffect(() => () => onExposeSave(null), [onExposeSave])

  useEffect(() => {
    fetchSettings()
      .then(s => {
        setSettings(s)
        setUiEnabled(s.notify_ui_enabled)
        setUiEvents(s.notify_ui_events ?? [])
        setDiscordEnabled(s.notify_discord_enabled)
        setTelegramEnabled(s.notify_telegram_enabled)
        setTelegramChatId(s.notify_telegram_chat_id ?? '')
        setEventTypes(s.notify_event_types ?? [])
        setDiscordEvents(s.notify_discord_events ?? [])
        setTelegramEvents(s.notify_telegram_events ?? [])
        setBaseline(notifSignature({
          uiEnabled: s.notify_ui_enabled, uiEvents: s.notify_ui_events ?? [],
          discordEnabled: s.notify_discord_enabled, telegramEnabled: s.notify_telegram_enabled,
          telegramChatId: s.notify_telegram_chat_id ?? '', discordEvents: s.notify_discord_events ?? [],
          telegramEvents: s.notify_telegram_events ?? [],
        }))
      })
      .catch(() => setMsg({ ok: false, text: 'Error cargando configuración' }))
      .finally(() => setLoading(false))
  }, [])

  function toggleEvent(setter: React.Dispatch<React.SetStateAction<string[]>>, code: string, checked: boolean) {
    setter(prev => (checked ? [...new Set([...prev, code])] : prev.filter(c => c !== code)))
  }

  async function handleSave() {
    setSaving(true)
    setMsg(null)
    try {
      const payload: Parameters<typeof updateSettings>[0] = {
        notify_ui_enabled: uiEnabled,
        notify_ui_events: uiEvents,
        notify_discord_enabled: discordEnabled,
        notify_telegram_enabled: telegramEnabled,
        notify_telegram_chat_id: telegramChatId.trim(),
        notify_discord_events: discordEvents,
        notify_telegram_events: telegramEvents,
      }
      if (discordWebhook.trim()) payload.notify_discord_webhook_url = discordWebhook.trim()
      if (telegramToken.trim()) payload.notify_telegram_bot_token = telegramToken.trim()
      const updated = await updateSettings(payload)
      setSettings(updated)
      setUiEvents(updated.notify_ui_events ?? [])
      setDiscordEvents(updated.notify_discord_events ?? [])
      setTelegramEvents(updated.notify_telegram_events ?? [])
      setDiscordWebhook('')
      setTelegramToken('')
      setBaseline(notifSignature({
        uiEnabled: updated.notify_ui_enabled, uiEvents: updated.notify_ui_events ?? [],
        discordEnabled: updated.notify_discord_enabled, telegramEnabled: updated.notify_telegram_enabled,
        telegramChatId: updated.notify_telegram_chat_id ?? '', discordEvents: updated.notify_discord_events ?? [],
        telegramEvents: updated.notify_telegram_events ?? [],
      }))
      setMsg({ ok: true, text: '✓ Notificaciones guardadas' })
    } catch (e: unknown) {
      setMsg({ ok: false, text: `✗ ${e instanceof Error ? e.message : String(e)}` })
    } finally {
      setSaving(false)
      setTimeout(() => setMsg(null), 5000)
    }
  }

  async function handleTestDiscord() {
    setTestingDiscord(true)
    setDiscordResult(null)
    try {
      const params: { webhook_url?: string } = {}
      if (discordWebhook.trim()) params.webhook_url = discordWebhook.trim()
      setDiscordResult(await testDiscordNotification(params))
    } catch {
      setDiscordResult({ ok: false, service: 'discord', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setTestingDiscord(false)
    }
  }

  async function handleTestTelegram() {
    setTestingTelegram(true)
    setTelegramResult(null)
    try {
      const params: { bot_token?: string; chat_id?: string } = {}
      if (telegramToken.trim()) params.bot_token = telegramToken.trim()
      if (telegramChatId.trim()) params.chat_id = telegramChatId.trim()
      setTelegramResult(await testTelegramNotification(params))
    } catch {
      setTelegramResult({ ok: false, service: 'telegram', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setTestingTelegram(false)
    }
  }

  function renderResult(result: IntegrationTestResult | null) {
    if (!result) return null
    return (
      <span style={{
        marginLeft: 10, fontSize: 12,
        color: result.ok ? '#22c55e' : result.status === 'not_configured' ? '#f59e0b' : '#ef4444',
      }}>
        {result.ok ? '✓ Enviada'
          : result.status === 'not_configured' ? '⚠ Sin configurar'
          : result.status === 'invalid_key' ? '✗ Credenciales inválidas'
          : result.status === 'invalid_chat_id' ? '✗ Chat ID inválido'
          : result.status === 'timeout' ? '✗ Timeout'
          : `✗ ${result.message}`}
      </span>
    )
  }

  if (loading) return <p style={{ padding: 20, color: 'var(--text-muted)', fontSize: 13 }}>Cargando…</p>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 16, alignItems: 'stretch' }}>
      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="emu" size={20} /> Notificaciones UI
        </h3>
        <label className="checkbox-label" style={{ marginBottom: 12 }}>
          <input type="checkbox" checked={uiEnabled} onChange={e => setUiEnabled(e.target.checked)} /> Mostrar avisos en la campana
        </label>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 0 }}>
          Avisos dentro de la propia app (icono de la campana en la barra superior).
        </p>
        <EventPicker
          title="Qué mostrar en la campana"
          eventTypes={eventTypes}
          selected={uiEvents}
          disabled={!uiEnabled}
          onToggle={(code, checked) => toggleEvent(setUiEvents, code, checked)}
        />
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="discord" size={20} /> Discord
        </h3>
        <label className="checkbox-label" style={{ marginBottom: 12, display: 'block' }}>
          <input type="checkbox" checked={discordEnabled} onChange={e => setDiscordEnabled(e.target.checked)} /> Activar notificaciones por Discord
        </label>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Webhook URL</label>
          <div style={{ fontSize: 13, marginBottom: 6 }}>
            {settings?.notify_discord_webhook_configured
              ? <><span style={{ color: '#22c55e', display: 'inline-flex', alignItems: 'center', gap: 5 }}><CheckStatusIcon status="ok" /> Configurado</span>{settings.notify_discord_webhook_masked && <code style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)' }}>{settings.notify_discord_webhook_masked}</code>}</>
              : <span style={{ color: '#ef4444' }}>✗ No configurado</span>}
          </div>
          <input
            type="password"
            className="form-input"
            value={discordWebhook}
            onChange={e => setDiscordWebhook(e.target.value)}
            placeholder="https://discord.com/api/webhooks/… (dejar vacío para mantener el actual)"
            autoComplete="new-password"
          />
        </div>
        <button className="btn btn-secondary btn-sm" onClick={handleTestDiscord} disabled={testingDiscord} type="button">
          {testingDiscord ? 'Enviando…' : 'Probar notificación'}
        </button>
        {renderResult(discordResult)}
        <EventPicker
          title="Qué notificar por Discord"
          eventTypes={eventTypes}
          selected={discordEvents}
          disabled={!discordEnabled}
          onToggle={(code, checked) => toggleEvent(setDiscordEvents, code, checked)}
        />
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="telegram" size={20} /> Telegram
        </h3>
        <label className="checkbox-label" style={{ marginBottom: 12, display: 'block' }}>
          <input type="checkbox" checked={telegramEnabled} onChange={e => setTelegramEnabled(e.target.checked)} /> Activar notificaciones por Telegram
        </label>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Bot token</label>
          <div style={{ fontSize: 13, marginBottom: 6 }}>
            {settings?.notify_telegram_bot_token_configured
              ? <><span style={{ color: '#22c55e', display: 'inline-flex', alignItems: 'center', gap: 5 }}><CheckStatusIcon status="ok" /> Configurado</span>{settings.notify_telegram_bot_token_masked && <code style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)' }}>{settings.notify_telegram_bot_token_masked}</code>}</>
              : <span style={{ color: '#ef4444' }}>✗ No configurado</span>}
          </div>
          <input
            type="password"
            className="form-input"
            value={telegramToken}
            onChange={e => setTelegramToken(e.target.value)}
            placeholder="123456:ABC-DEF… (dejar vacío para mantener el actual)"
            autoComplete="new-password"
          />
        </div>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Chat ID</label>
          <input className="form-input" value={telegramChatId} onChange={e => setTelegramChatId(e.target.value)} placeholder="-100123456789" />
        </div>
        <button className="btn btn-secondary btn-sm" onClick={handleTestTelegram} disabled={testingTelegram} type="button">
          {testingTelegram ? 'Enviando…' : 'Probar notificación'}
        </button>
        {renderResult(telegramResult)}
        <EventPicker
          title="Qué notificar por Telegram"
          eventTypes={eventTypes}
          selected={telegramEvents}
          disabled={!telegramEnabled}
          onToggle={(code, checked) => toggleEvent(setTelegramEvents, code, checked)}
        />
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
  const [saveAction, setSaveAction] = useState<SaveExpose | null>(null)

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
    { key: 'notifications', label: 'Notificaciones' },
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
        {saveAction && (
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            {saveAction.dirty && <span style={{ fontSize: 12, color: '#f59e0b' }}>Cambios sin guardar</span>}
            <button
              className={`btn btn-primary btn-sm${saveAction.dirty ? ' btn-unsaved' : ''}`}
              onClick={saveAction.onSave}
              disabled={saveAction.saving}
            >
              {saveAction.saving ? 'Guardando…' : saveAction.label}
            </button>
          </div>
        )}
      </div>

      {loadError && (
        <div style={{ padding: '8px 14px', marginBottom: 12, background: 'var(--color-error-bg, #2e1a1a)', borderRadius: 6, fontSize: 13 }}>
          ✗ No se pudo cargar el estado de mantenimiento: {loadError}
        </div>
      )}

      <div style={{ display: 'flex', gap: 2, marginBottom: 20, borderBottom: '1px solid var(--border)' }}>
        {tabs.map(t => (
          <button
            key={t.key}
            className={`settings-tab${tab === t.key ? ' active' : ''}`}
            onClick={() => { if (t.key !== tab) guardedLeave(() => setTab(t.key)) }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'config' && <ConfigTab onExposeSave={setSaveAction} />}
      {tab === 'notifications' && <NotificationsTab onExposeSave={setSaveAction} />}
      {tab === 'diagnostics' && <DiagnosticsTab status={status} />}
      {tab === 'backup' && <BackupTab status={status} onRefresh={loadStatus} />}
      {tab === 'maintenance' && <MaintenanceTab />}
    </div>
  )
}
