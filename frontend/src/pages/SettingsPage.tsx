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
import { REGION_OPTIONS, LANGUAGE_OPTIONS } from '../constants/regionLanguage'
import { testResultLabel, testResultColor, emuTestCooldownSeconds } from '../utils/integrationResult'

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
  tag: string; providerOrder: string[]; region: string; language: string
  localizeTitles: boolean; emuUsername: string; ignoreSpecials: boolean
  recentLimit: number; qbitUrl: string; qbitPort: string; qbitUser: string
  imgEnabled: string[]; pathMappings: { from: string; to: string }[]
  newKey?: string; newEmuKey?: string; qbitPass?: string
  imgKeys?: Record<string, string>
}): string {
  return JSON.stringify([
    v.tag, v.providerOrder, v.region, v.language, v.localizeTitles, v.emuUsername,
    v.ignoreSpecials, v.recentLimit, v.qbitUrl, v.qbitPort, v.qbitUser, v.imgEnabled,
    v.pathMappings, v.newKey ?? '', v.newEmuKey ?? '', v.qbitPass ?? '', v.imgKeys ?? {},
  ])
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
  const [language, setLanguage] = useState('')
  const [localizeTitles, setLocalizeTitles] = useState(true)
  const [newKey, setNewKey] = useState('')
  const [newEmuKey, setNewEmuKey] = useState('')
  const [emuUsername, setEmuUsername] = useState('')
  const [ignoreSpecials, setIgnoreSpecials] = useState(true)
  const [recentLimit, setRecentLimit] = useState(50)
  const [qbitUrl, setQbitUrl] = useState('')
  const [qbitPort, setQbitPort] = useState('8080')
  const [qbitUser, setQbitUser] = useState('')
  const [qbitPass, setQbitPass] = useState('')
  const [testingQbit, setTestingQbit] = useState(false)
  const [qbitTestResult, setQbitTestResult] = useState<IntegrationTestResult | null>(null)
  // Image hosts
  const [imgEnabled, setImgEnabled] = useState<string[]>([])
  const [imgKeys, setImgKeys] = useState<Record<string, string>>({})
  const [imgTest, setImgTest] = useState<Record<string, IntegrationTestResult>>({})
  const [imgTesting, setImgTesting] = useState<string | null>(null)
  const [showAddImg, setShowAddImg] = useState(false)
  const [pathMappings, setPathMappings] = useState<{ from: string; to: string }[]>([])

  // Unsaved-changes tracking: compare current form values to the loaded ones.
  const [baseline, setBaseline] = useState('')
  const currentSig = configSignature({
    tag, providerOrder, region, language, localizeTitles, emuUsername,
    ignoreSpecials, recentLimit, qbitUrl, qbitPort, qbitUser, imgEnabled, pathMappings,
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
        setLanguage(s.tmdb_language)
        setLocalizeTitles(s.tmdb_localize_series_titles ?? true)
        setEmuUsername(s.emu_username ?? '')
        setIgnoreSpecials(s.series_ignore_specials ?? true)
        setRecentLimit(s.recent_activity_limit ?? 50)
        setQbitUrl(s.qbit_url ?? '')
        setQbitPort(s.qbit_port ?? '8080')
        setQbitUser(s.qbit_username ?? '')
        setImgEnabled(s.image_hosts_enabled ?? [])
        setPathMappings(s.path_mappings ?? [])
        setBaseline(configSignature({
          tag: s.default_release_tag, providerOrder: s.provider_priority_order,
          region: s.tmdb_watch_region, language: s.tmdb_language,
          localizeTitles: s.tmdb_localize_series_titles ?? true, emuUsername: s.emu_username ?? '',
          ignoreSpecials: s.series_ignore_specials ?? true, recentLimit: s.recent_activity_limit ?? 50,
          qbitUrl: s.qbit_url ?? '', qbitPort: s.qbit_port ?? '8080', qbitUser: s.qbit_username ?? '',
          imgEnabled: s.image_hosts_enabled ?? [], pathMappings: s.path_mappings ?? [],
        }))
      })
      .catch(() => setMsg({ ok: false, text: 'Error cargando configuración' }))
      .finally(() => setLoading(false))
  }, [])

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
    setSaving(true)
    setMsg(null)
    try {
      const payload: Parameters<typeof updateSettings>[0] = {
        default_release_tag: tag.trim(),
        provider_priority_order: providerOrder,
        tmdb_watch_region: region.trim(),
        tmdb_language: language.trim(),
        tmdb_localize_series_titles: localizeTitles,
        emu_username: emuUsername.trim(),
        series_ignore_specials: ignoreSpecials,
        recent_activity_limit: recentLimit,
        qbit_url: qbitUrl.trim(),
        qbit_port: qbitPort.trim(),
        qbit_username: qbitUser.trim(),
        image_hosts_enabled: imgEnabled,
        path_mappings: pathMappings.map(m => ({ from: m.from.trim(), to: m.to.trim() })).filter(m => m.from && m.to),
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
      setLanguage(updated.tmdb_language)
      setLocalizeTitles(updated.tmdb_localize_series_titles ?? true)
      setEmuUsername(updated.emu_username ?? '')
      setIgnoreSpecials(updated.series_ignore_specials ?? true)
      setRecentLimit(updated.recent_activity_limit ?? 50)
      setQbitUrl(updated.qbit_url ?? '')
      setQbitPort(updated.qbit_port ?? '8080')
      setQbitUser(updated.qbit_username ?? '')
      setQbitPass('')
      setImgEnabled(updated.image_hosts_enabled ?? [])
      setImgKeys({})
      setNewKey('')
      setNewEmuKey('')
      setPathMappings(updated.path_mappings ?? [])
      setBaseline(configSignature({
        tag: updated.default_release_tag, providerOrder: updated.provider_priority_order,
        region: updated.tmdb_watch_region, language: updated.tmdb_language,
        localizeTitles: updated.tmdb_localize_series_titles ?? true, emuUsername: updated.emu_username ?? '',
        ignoreSpecials: updated.series_ignore_specials ?? true, recentLimit: updated.recent_activity_limit ?? 50,
        qbitUrl: updated.qbit_url ?? '', qbitPort: updated.qbit_port ?? '8080', qbitUser: updated.qbit_username ?? '',
        imgEnabled: updated.image_hosts_enabled ?? [], pathMappings: updated.path_mappings ?? [],
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
        <h3 style={{ marginTop: 0, marginBottom: 14 }}>Emuwarez</h3>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Estado de la API key</label>
          <div style={{ fontSize: 13 }}>
            {settings?.emu_api_key_configured
              ? <><span style={{ color: '#22c55e' }}>✓ Configurada</span>{settings.emu_api_key_masked && <code style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)' }}>{settings.emu_api_key_masked}</code>}</>
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
          <label className="form-label">Mi usuario de eMuwarez</label>
          <input
            className="form-input"
            value={emuUsername}
            onChange={e => setEmuUsername(e.target.value)}
            placeholder="Tu nombre de usuario en eMuwarez"
          />
          <span className="form-hint">
            Como eMuwarez no expone tu usuario automáticamente, escríbelo aquí para que el Dashboard pueda
            mostrar cuántas peticiones son tuyas ("Mis peticiones").
          </span>
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
          <input className="form-input" value={qbitUser} onChange={e => setQbitUser(e.target.value)} placeholder="admin" autoComplete="off" />
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
        <span className="form-hint" style={{ display: 'block', marginTop: 10 }}>
          El cliente de torrents que usa Uploadrr para añadir el .torrent tras subir a eMuwarez.
        </span>
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="imghost" size={18} /> Proveedores de imágenes
        </h3>
        <span className="form-hint" style={{ display: 'block', marginBottom: 12 }}>
          Para las capturas que Uploadrr sube junto al torrent. <strong>imgbox</strong> es el fallback por
          defecto (sin key); se prueban en orden e imgbox va siempre el último.
        </span>
        {(() => {
          const avail = settings?.image_hosts_available ?? []
          const configuredIds = ['imgbox', ...imgEnabled.filter(id => id !== 'imgbox')]
          const notConfigured = avail.filter(h => !configuredIds.includes(h.id))
          const metaOf = (id: string) => avail.find(h => h.id === id)
          return (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 230, overflowY: 'auto' }}>
                {configuredIds.map(id => {
                  const h = metaOf(id); if (!h) return null
                  const isDefault = id === 'imgbox'
                  const t = imgTest[id]
                  return (
                    <div key={id} style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 8, background: 'rgba(139,92,246,0.06)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <ServiceIcon type="imghost" size={15} />
                        <span style={{ fontSize: 13, fontWeight: 500 }}>{h.label}</span>
                        {isDefault && <span className="badge status-available" style={{ fontSize: 10 }}>por defecto</span>}
                        {h.needs_key && <span className="badge nom-na" style={{ fontSize: 10 }}>API key</span>}
                        <button className="btn btn-secondary btn-sm" style={{ marginLeft: 'auto', fontSize: 11, padding: '2px 8px' }}
                          onClick={() => handleTestImghost(id)} disabled={imgTesting === id} type="button">
                          {imgTesting === id ? 'Probando…' : 'Probar'}
                        </button>
                        {!isDefault && (
                          <button className="btn btn-ghost btn-sm" style={{ fontSize: 13, padding: '2px 6px', color: 'var(--text-muted)' }}
                            title="Quitar" onClick={() => toggleImgHost(id)} type="button">✕</button>
                        )}
                      </div>
                      {h.needs_key && (
                        <input type="password" className="form-input" style={{ marginTop: 6 }} autoComplete="new-password"
                          value={imgKeys[id] ?? ''} onChange={e => setImgKeys(p => ({ ...p, [id]: e.target.value }))}
                          placeholder={settings?.image_host_keys_configured?.includes(id) ? '•••••••• (guardada — vacío para mantener)' : `API key de ${h.label}`} />
                      )}
                      {t && <div style={{ fontSize: 11, marginTop: 4, color: testResultColor(t) }}>{testResultLabel(t)}</div>}
                    </div>
                  )
                })}
              </div>
              {notConfigured.length > 0 && (
                <button className="btn btn-secondary btn-sm" style={{ marginTop: 10 }} onClick={() => setShowAddImg(v => !v)} type="button">
                  {showAddImg ? 'Cerrar' : '+ Añadir proveedor'}
                </button>
              )}
              {showAddImg && (
                <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 6, maxHeight: 180, overflowY: 'auto', padding: 8, border: '1px solid var(--border)', borderRadius: 8 }}>
                  {notConfigured.map(h => (
                    <button key={h.id} className="btn btn-ghost btn-sm" type="button"
                      style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-start', fontSize: 12 }}
                      onClick={() => { toggleImgHost(h.id); }}>
                      <ServiceIcon type="imghost" size={13} /> {h.label} {h.needs_key && <span className="badge nom-na" style={{ fontSize: 9 }}>API key</span>}
                    </button>
                  ))}
                </div>
              )}
            </>
          )
        })()}
      </div>

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
            placeholder="API key de TMDb"
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
            <span style={{ marginLeft: 10, fontSize: 12, color: testResultColor(tmdbTestResult) }}>
              {testResultLabel(tmdbTestResult)}
            </span>
          )}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="form-group">
            <label className="form-label">Región</label>
            <select className="form-input form-select" value={region} onChange={e => setRegion(e.target.value)}>
              {REGION_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label} ({o.value})</option>)}
            </select>
            <span className="form-hint">País para filtrar providers.</span>
          </div>
          <div className="form-group">
            <label className="form-label">Idioma</label>
            <select className="form-input form-select" value={language} onChange={e => setLanguage(e.target.value)}>
              {LANGUAGE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <label className="checkbox-label" style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginTop: 4, gridColumn: '1 / -1' }}>
            <input type="checkbox" checked={localizeTitles} onChange={e => setLocalizeTitles(e.target.checked)} style={{ marginTop: 3 }} />
            <span style={{ fontSize: 13 }}>
              Traducir títulos de series con TMDb
              <span className="form-hint" style={{ display: 'block' }}>
                Sonarr toma los títulos de TVDB (a menudo en inglés). Con esto, las series usan el título de TMDb en el idioma de arriba (p. ej. «The Serrano» → «Los Serrano»). Se aplica en la próxima sincronización de biblioteca.
              </span>
            </span>
          </label>
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
          <label className="form-label">Prioridad de providers</label>
          <ProviderPriorityPicker order={providerOrder} onChange={setProviderOrder} />
          <span className="form-hint">Se usa para elegir automáticamente el provider cuando TMDb devuelve varios. Arrastra para reordenar.</span>
        </div>
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14 }}>Otros</h3>
        <div className="form-group" style={{ marginBottom: 14 }}>
          <label className="checkbox-label" style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <input type="checkbox" checked={ignoreSpecials} onChange={e => setIgnoreSpecials(e.target.checked)} style={{ marginTop: 3 }} />
            <span>
              Ignorar episodios especiales en el estado de una serie
              <span className="form-hint" style={{ display: 'block' }}>
                Excluye la temporada especial (temporada 0) de los datos globales de la serie: si tienes todas las temporadas y capítulos salvo los especiales, la serie contará como completa en <strong>Estado</strong>, <strong>Nomenclatura</strong> y <strong>¿En eMuwarez?</strong>, y sus atributos consolidados (<strong>resolución, source, códecs, audio y subtítulos</strong>) se calculan ignorando los especiales.
              </span>
            </span>
          </label>
        </div>
        <div className="form-group">
          <label className="form-label">Elementos en «Actividad reciente»</label>
          <select className="form-input form-select" value={recentLimit} onChange={e => setRecentLimit(Number(e.target.value))}>
            {[50, 100, 150, 200, 250, 300].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          <span className="form-hint">Cuántos elementos muestra el panel «Actividad reciente» del dashboard.</span>
        </div>
      </div>
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 6 }}>Mapeo de rutas (biblioteca remota)</h3>
        <p className="form-hint" style={{ marginTop: 0, marginBottom: 12 }}>
          Traduce la ruta que reporta Radarr/Sonarr a la ruta donde la app alcanza el archivo
          (monta la biblioteca por SSHFS/NFS/SMB donde quieras). Se aplica al leer MediaInfo,
          verificar y subir. Sin reglas, no cambia nada.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {pathMappings.length === 0 && (
            <span className="form-hint">No hay reglas. Añade una para acceder a una biblioteca remota.</span>
          )}
          {pathMappings.map((m, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                className="form-input" style={{ flex: 1, minWidth: 200 }}
                value={m.from} placeholder="Ruta de Radarr/Sonarr — /data/media"
                onChange={e => setPathMappings(p => p.map((x, j) => j === i ? { ...x, from: e.target.value } : x))}
              />
              <span style={{ color: 'var(--text-muted)' }}>→</span>
              <input
                className="form-input" style={{ flex: 1, minWidth: 200 }}
                value={m.to} placeholder="Ruta local — /home/alvaro/mnt/emu-media"
                onChange={e => setPathMappings(p => p.map((x, j) => j === i ? { ...x, to: e.target.value } : x))}
              />
              <button className="btn btn-ghost btn-sm" type="button" title="Quitar regla"
                onClick={() => setPathMappings(p => p.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
        </div>
        <button className="btn btn-secondary btn-sm" style={{ marginTop: 10 }} type="button"
          onClick={() => setPathMappings(p => [...p, { from: '', to: '' }])}>+ Añadir regla</button>
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
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 10px' }}>Ejecuta <code>PRAGMA integrity_check</code> — solo lectura.</p>
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
          <label key={ev.code} className="checkbox-label" style={{ fontSize: 13, display: 'block' }}>
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
        <label className="checkbox-label" style={{ marginBottom: 12, display: 'block' }}>
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
              ? <><span style={{ color: '#22c55e' }}>✓ Configurado</span>{settings.notify_discord_webhook_masked && <code style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)' }}>{settings.notify_discord_webhook_masked}</code>}</>
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
              ? <><span style={{ color: '#22c55e' }}>✓ Configurado</span>{settings.notify_telegram_bot_token_masked && <code style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)' }}>{settings.notify_telegram_bot_token_masked}</code>}</>
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
            onClick={() => { if (t.key !== tab) guardedLeave(() => setTab(t.key)) }}
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

      {tab === 'config' && <ConfigTab onExposeSave={setSaveAction} />}
      {tab === 'notifications' && <NotificationsTab onExposeSave={setSaveAction} />}
      {tab === 'diagnostics' && <DiagnosticsTab status={status} />}
      {tab === 'backup' && <BackupTab status={status} onRefresh={loadStatus} />}
      {tab === 'maintenance' && <MaintenanceTab />}
    </div>
  )
}
