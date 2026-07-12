import { useState, useEffect } from 'react'
import {
  setupAdmin, setupTmdb, setupEmu, setupInstances,
  setupNomenclature, setupQbit, setupImghosts, setupComplete,
} from '../api/setup'
import { login } from '../api/auth'
import { syncAll } from '../api/library'
import { fetchSettings } from '../api/settings'
import { testTmdbConnection, testEmuwarezConnection, testArrConnection, testQbitConnection, testImghostConnection, type IntegrationTestResult } from '../api/integrationTests'
import { ServiceIcon } from '../components/ServiceIcon'
import { ProviderPriorityPicker } from '../components/ProviderPriorityPicker'
import { REGION_OPTIONS, LANGUAGE_OPTIONS } from '../constants/regionLanguage'
import { SETUP_STEPS, SETUP_STEP_LABELS } from '../types/domain'
import type { SetupStep } from '../types/domain'
import type { SetupStatusResponse } from '../types/api'
import { testResultLabel, testResultColor, emuTestCooldownSeconds } from '../utils/integrationResult'
import { useCooldown } from '../hooks/useCooldown'

const DISABLE_HARDLINKS_TOKEN = 'DESACTIVAR_HARDLINKS'

// Mirrors validate_password_strength() in web/security.py exactly (same
// regexes) so the checklist never drifts from what the backend enforces.
const PASSWORD_RULES: { label: string; test: (p: string) => boolean }[] = [
  { label: 'Al menos 12 caracteres', test: p => p.length >= 12 },
  { label: 'Una letra minúscula', test: p => /[a-z]/.test(p) },
  { label: 'Una letra mayúscula', test: p => /[A-Z]/.test(p) },
  { label: 'Un número', test: p => /\d/.test(p) },
  { label: 'Un símbolo (no alfanumérico)', test: p => /[^a-zA-Z0-9]/.test(p) },
]

function PasswordChecklist({ password }: { password: string }) {
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: '8px 0 0', display: 'grid', gap: 4 }}>
      {PASSWORD_RULES.map(rule => {
        const ok = rule.test(password)
        return (
          <li key={rule.label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: ok ? '#22c55e' : 'var(--text-muted)' }}>
            <span>{ok ? '✓' : '○'}</span>
            <span>{rule.label}</span>
          </li>
        )
      })}
    </ul>
  )
}

interface SetupWizardProps {
  setupStatus: SetupStatusResponse
  onComplete: () => void
}

interface InstanceDraft {
  id: number
  type: 'radarr' | 'sonarr'
  name: string
  url: string
  api_key: string
  is_4k: boolean
  is_anime: boolean
}

function StepsBar({ current, steps }: { current: string; steps: readonly string[] }) {
  const currentIdx = steps.indexOf(current)
  return (
    <div className="wizard-steps-bar">
      {steps.map((s, i) => (
        <div
          key={s}
          className={`wizard-step-dot${i < currentIdx ? ' done' : i === currentIdx ? ' active' : ''}`}
          title={SETUP_STEP_LABELS[s as SetupStep]}
        />
      ))}
    </div>
  )
}

export function SetupWizard({ setupStatus, onComplete }: SetupWizardProps) {
  const initialStep: SetupStep = !setupStatus.admin_configured
    ? 'welcome'
    : (setupStatus.next_step as SetupStep) ?? 'complete'

  const [step, setStep] = useState<SetupStep>(initialStep)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [adminCreated, setAdminCreated] = useState(false)

  // Admin step state
  const [adminUser, setAdminUser] = useState('')
  const [adminPass, setAdminPass] = useState('')
  const [adminPass2, setAdminPass2] = useState('')

  // TMDb step state
  const [tmdbKey, setTmdbKey] = useState('')
  const [tmdbLang, setTmdbLang] = useState('es-ES')
  const [tmdbRegion, setTmdbRegion] = useState('ES')
  const [tmdbLocalizeTitles, setTmdbLocalizeTitles] = useState(true)
  const [tmdbAckSkip, setTmdbAckSkip] = useState(false)

  // EMU step state
  const [emuKey, setEmuKey] = useState('')
  const [emuAckSkip, setEmuAckSkip] = useState(false)

  // qBittorrent step state
  const [qbitUrl, setQbitUrl] = useState('')
  const [qbitPort, setQbitPort] = useState('8080')
  const [qbitUser, setQbitUser] = useState('')
  const [qbitPass, setQbitPass] = useState('')
  const [qbitTestResult, setQbitTestResult] = useState<IntegrationTestResult | null>(null)
  const [qbitTesting, setQbitTesting] = useState(false)

  async function handleTestQbit() {
    setQbitTesting(true); setQbitTestResult(null)
    try {
      setQbitTestResult(await testQbitConnection({
        url: qbitUrl.trim() || undefined, port: qbitPort.trim() || undefined,
        username: qbitUser.trim() || undefined, password: qbitPass.trim() || undefined,
      }))
    } catch {
      setQbitTestResult({ ok: false, service: 'qbittorrent', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally { setQbitTesting(false) }
  }

  // Image hosts step state
  const [imgAvailable, setImgAvailable] = useState<{ id: string; label: string; needs_key: boolean }[]>([])
  const [imgEnabled, setImgEnabled] = useState<string[]>([])
  const [imgKeys, setImgKeys] = useState<Record<string, string>>({})
  const [imgTest, setImgTest] = useState<Record<string, IntegrationTestResult>>({})
  const [imgTesting, setImgTesting] = useState<string | null>(null)

  useEffect(() => {
    if (step === 'imagehosts' && imgAvailable.length === 0) {
      fetchSettings().then(s => setImgAvailable(s.image_hosts_available)).catch(() => { /* ignore */ })
    }
  }, [step, imgAvailable.length])

  async function handleTestImghost(hostId: string) {
    setImgTesting(hostId)
    try {
      const r = await testImghostConnection(hostId, imgKeys[hostId]?.trim() || undefined)
      setImgTest(p => ({ ...p, [hostId]: r }))
    } catch {
      setImgTest(p => ({ ...p, [hostId]: { ok: false, service: 'imghost', status: 'connection_error', message: 'Error' } }))
    } finally { setImgTesting(null) }
  }

  // Instances step state
  const [instances, setInstances] = useState<InstanceDraft[]>([])
  const [instDraft, setInstDraft] = useState<Partial<InstanceDraft>>({ type: 'radarr', is_4k: false, is_anime: false })
  const [instError, setInstError] = useState<string | null>(null)
  const [instAckSkip, setInstAckSkip] = useState(false)
  const [instPathAckSkip, setInstPathAckSkip] = useState(false)

  // Nomenclature step state (Phase 11C)
  const [nomTag, setNomTag] = useState('EMUWAREZ')
  const [nomHardlinkBase, setNomHardlinkBase] = useState('')
  const [noHardlinks, setNoHardlinks] = useState(false)
  const [hardlinksConfirm, setHardlinksConfirm] = useState('')
  // Same default as the backend's provider_priority_order setting
  // (web/api/settings.py::_DEFAULT_PRIORITY) — offered here too so it's
  // configured from the start instead of only reachable via Settings later.
  const [nomProviderOrder, setNomProviderOrder] = useState<string[]>(['AMZN', 'NF', 'DSNP', 'MAX', 'ATVP'])

  // Connection test state
  const [tmdbTestResult, setTmdbTestResult] = useState<IntegrationTestResult | null>(null)
  const [tmdbTesting, setTmdbTesting] = useState(false)
  const [emuTestResult, setEmuTestResult] = useState<IntegrationTestResult | null>(null)
  const [emuTesting, setEmuTesting] = useState(false)
  const emuCooldown = useCooldown()
  const [instTestResult, setInstTestResult] = useState<IntegrationTestResult | null>(null)
  const [instTesting, setInstTesting] = useState(false)

  function wrap(fn: () => Promise<void>) {
    return async () => {
      setError(null)
      setLoading(true)
      try {
        await fn()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error inesperado')
      } finally {
        setLoading(false)
      }
    }
  }

  async function handleTestTmdb() {
    setTmdbTesting(true)
    setTmdbTestResult(null)
    try {
      const r = await testTmdbConnection({ api_key: tmdbKey || undefined, language: tmdbLang || undefined, region: tmdbRegion || undefined })
      setTmdbTestResult(r)
      if (r.ok) setTmdbAckSkip(false)
    } catch {
      setTmdbTestResult({ ok: false, service: 'tmdb', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setTmdbTesting(false)
    }
  }

  async function handleTestEmu() {
    if (emuCooldown.active) return
    setEmuTesting(true)
    setEmuTestResult(null)
    try {
      const r = await testEmuwarezConnection({ api_key: emuKey || undefined })
      setEmuTestResult(r)
      emuCooldown.start(emuTestCooldownSeconds(r))
      if (r.ok) setEmuAckSkip(false)
    } catch {
      setEmuTestResult({ ok: false, service: 'emuwarez', status: 'connection_error', message: 'Error al contactar con el servidor' })
      emuCooldown.start(60)
    } finally {
      setEmuTesting(false)
    }
  }

  async function handleTestInst() {
    if (!instDraft.url?.trim() || !instDraft.api_key?.trim()) {
      setInstTestResult({ ok: false, service: 'arr', status: 'not_configured', message: 'Introduce URL y API key antes de probar' })
      return
    }
    setInstTesting(true)
    setInstTestResult(null)
    try {
      const r = await testArrConnection({
        kind: instDraft.type ?? 'radarr',
        base_url: instDraft.url!.trim(),
        api_key: instDraft.api_key!.trim(),
      })
      setInstTestResult(r)
    } catch {
      setInstTestResult({ ok: false, service: instDraft.type ?? 'arr', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setInstTesting(false)
    }
  }

  const handleAdmin = wrap(async () => {
    if (adminPass !== adminPass2) throw new Error('Las contraseñas no coinciden')
    await setupAdmin(adminUser.trim(), adminPass)
    // Auto-login after admin creation
    await login(adminUser.trim(), adminPass)
    setAdminCreated(true)
    setStep('emu')
  })

  const handleEmu = wrap(async () => {
    // Persist the key only when there's text AND the user is NOT explicitly
    // skipping. Ticking "continuar sin verificar" means "I'm not really
    // configuring this now", so whatever was typed must be discarded — it
    // must not show up as configured later in Settings. (setup_emu also
    // rejects an empty string, which would block skipping entirely.)
    if (emuKey.trim() && !emuAckSkip) {
      await setupEmu(emuKey)
    }
    setStep('instances')
  })

  function addInstance() {
    setInstError(null)
    if (!instDraft.name?.trim()) { setInstError('El nombre es obligatorio'); return }
    if (!instDraft.url?.trim()) { setInstError('La URL es obligatoria'); return }
    if (!instDraft.api_key?.trim()) { setInstError('La API key es obligatoria'); return }
    setInstances(prev => [...prev, {
      id: Date.now(),
      type: instDraft.type ?? 'radarr',
      name: instDraft.name!.trim(),
      url: instDraft.url!.trim(),
      api_key: instDraft.api_key!.trim(),
      is_4k: instDraft.is_4k ?? false,
      is_anime: instDraft.is_anime ?? false,
    }])
    setInstDraft({ type: 'radarr', is_4k: false, is_anime: false })
  }

  const handleInstances = wrap(async () => {
    await setupInstances(instances.map(i => ({
      type: i.type, name: i.name, url: i.url, api_key: i.api_key,
      is_4k: i.is_4k, is_anime: i.is_anime,
    })))
    setStep('tmdb')
  })

  const handleTmdb = wrap(async () => {
    // Same as eMuwarez: persist only when there's text AND the user is not
    // explicitly skipping. Text + "continuar sin verificar" must be discarded
    // so it never shows as configured in Settings afterwards.
    if (tmdbKey.trim() && !tmdbAckSkip) {
      await setupTmdb(tmdbKey, tmdbLang, tmdbRegion, tmdbLocalizeTitles)
    }
    setStep('nomenclature')
  })

  const handleNomenclature = wrap(async () => {
    await setupNomenclature({
      default_release_tag: nomTag,
      hardlink_base: nomHardlinkBase.trim() || undefined,
      use_hardlinks: !noHardlinks,
      confirmation: noHardlinks ? hardlinksConfirm : undefined,
      provider_priority_order: nomProviderOrder,
    })
    setStep('qbit')
  })

  const handleQbit = wrap(async () => {
    // Optional/skippable: an empty URL just moves on without configuring qBit.
    if (qbitUrl.trim()) {
      await setupQbit(qbitUrl.trim(), qbitPort.trim() || '8080', qbitUser.trim(), qbitPass)
    }
    setStep('imagehosts')
  })

  const handleImghosts = wrap(async () => {
    const keys = Object.fromEntries(Object.entries(imgKeys).filter(([, v]) => v.trim()))
    await setupImghosts(imgEnabled, keys)
    setStep('complete')
  })

  const handleComplete = wrap(async () => {
    await setupComplete()
    if (instances.length > 0) {
      // Best-effort: the Dashboard shows the real state either way (and has
      // its own manual "Sincronizar biblioteca" button), so a failure here
      // shouldn't block finishing setup. Deliberately NOT gated on
      // last_sync_at/summary state — the scheduler (Phase 11D) can run its
      // own sync-library tick before the user even finishes this wizard,
      // which would make any "has it ever synced" check for the Dashboard's
      // own sake constantly self-report success with an empty library.
      try { await syncAll(true) } catch { /* dashboard will show the real state */ }
    }
    onComplete()
  })

  const stepIdx = SETUP_STEPS.indexOf(step)
  const adminPasswordValid = PASSWORD_RULES.every(rule => rule.test(adminPass))
  const emuCanContinue = Boolean(emuTestResult?.ok) || emuAckSkip
  const instancesCanContinue = instances.length > 0 || instAckSkip
  const tmdbCanContinue = Boolean(tmdbTestResult?.ok) || tmdbAckSkip

  return (
    <div className="setup-wizard-wrap">
      <div className="setup-wizard">
        <div className="wizard-logo">
          <ServiceIcon type="emu" size={40} />
          <div className="wizard-logo-title" style={{ marginTop: 8 }}>eMuwarez Uploadrr</div>
          <div className="wizard-logo-sub">Asistente de configuración inicial</div>
        </div>

        <StepsBar current={step} steps={SETUP_STEPS} />

        <div className="wizard-card">
          <div className="wizard-step-title">
            {stepIdx + 1}. {SETUP_STEP_LABELS[step]}
          </div>

          {/* Welcome step */}
          {step === 'welcome' && (
            <>
              <div className="wizard-step-desc" style={{ marginBottom: 4 }}>
                eMuwarez Uploadrr es una aplicación autoalojada que:
              </div>
              <ul style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8, paddingLeft: 20, marginTop: 8 }}>
                <li>Gestiona y sincroniza tus bibliotecas de Radarr y Sonarr.</li>
                <li>Prepara y sube contenido siguiendo la nomenclatura de eMuwarez.</li>
                <li>Se conecta con eMuwarez para listar las peticiones actuales.</li>
                <li>Permite crear o modificar peticiones en eMuwarez.</li>
                <li>Si tienes contenido compatible con una petición existente en eMuwarez, te recomienda subirlo a la plataforma.</li>
                <li>Te recomienda crear una petición si tienes contenido faltante en tu biblioteca.</li>
              </ul>
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={() => setStep('admin')}>
                  Empezar
                </button>
              </div>
            </>
          )}

          {/* Admin step */}
          {step === 'admin' && (
            <>
              <div className="wizard-step-desc">
                Crea la cuenta de administrador local. La contraseña debe tener al menos 12 caracteres,
                una mayúscula, una minúscula, un número y un símbolo.
              </div>
              {adminCreated && <div className="alert alert-success" style={{ marginBottom: 14 }}>Admin creado. Iniciando sesión…</div>}
              <div className="wizard-fields">
                <div className="form-group">
                  <label className="form-label">Usuario</label>
                  <input className="form-input" placeholder="admin" value={adminUser} onChange={e => setAdminUser(e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Contraseña</label>
                  <input className="form-input" type="password" placeholder="Mínimo 12 caracteres" value={adminPass} onChange={e => setAdminPass(e.target.value)} />
                  <PasswordChecklist password={adminPass} />
                </div>
                <div className="form-group">
                  <label className="form-label">Confirmar contraseña</label>
                  <input className="form-input" type="password" placeholder="Repite la contraseña" value={adminPass2} onChange={e => setAdminPass2(e.target.value)} />
                  {adminPass2 && (
                    <span style={{ fontSize: 12.5, color: adminPass === adminPass2 ? '#22c55e' : '#ef4444', marginTop: 6, display: 'inline-block' }}>
                      {adminPass === adminPass2 ? '✓ Las contraseñas coinciden' : '✗ Las contraseñas no coinciden'}
                    </span>
                  )}
                </div>
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleAdmin} disabled={loading || !adminUser || !adminPasswordValid || adminPass !== adminPass2}>
                  {loading ? 'Creando…' : 'Crear admin'}
                </button>
              </div>
            </>
          )}

          {/* EMU step */}
          {step === 'emu' && (
            <>
              <div className="wizard-step-desc">Credenciales de eMuwarez.</div>
              <div className="form-warning" style={{ marginBottom: 14 }}>
                El refresco manual y automático de peticiones eMuwarez tiene un mínimo de 1 hora para
                evitar saturar el servicio.
              </div>
              <div className="wizard-fields">
                <div className="form-group">
                  <label className="form-label">API key eMuwarez</label>
                  <input className="form-input" value={emuKey} onChange={e => { setEmuKey(e.target.value); setEmuAckSkip(false) }} placeholder="Tu API key de eMuwarez" />
                </div>
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14, marginBottom: 4 }}>
                <button className="btn btn-secondary btn-sm" onClick={handleTestEmu} disabled={emuTesting || loading || emuCooldown.active} type="button">
                  {emuTesting ? 'Probando…' : emuCooldown.active ? `Espera ${emuCooldown.remaining}s` : 'Probar conexión'}
                </button>
                {emuTestResult && (
                  <span style={{ fontSize: 12, color: testResultColor(emuTestResult) }}>
                    {testResultLabel(emuTestResult)}
                  </span>
                )}
              </div>
              {!emuCanContinue && (
                <div className="alert alert-error" style={{ marginTop: 10 }}>
                  Todavía no has probado la key (o la prueba ha fallado). Si continúas sin verificarla,
                  las funciones que dependen de eMuwarez no funcionarán hasta que la corrijas más tarde en Configuración.
                  <label className="checkbox-label" style={{ display: 'block', marginTop: 8 }}>
                    <input type="checkbox" checked={emuAckSkip} onChange={e => setEmuAckSkip(e.target.checked)} /> Entiendo, continuar sin verificar
                  </label>
                </div>
              )}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleEmu} disabled={loading || !emuCanContinue}>
                  {loading ? 'Guardando…' : 'Continuar'}
                </button>
              </div>
            </>
          )}

          {/* Instances step */}
          {step === 'instances' && (
            <>
              <div className="wizard-step-desc">Añade tus instancias Radarr y/o Sonarr.</div>
              {instances.length > 0 && (
                <div style={{ marginBottom: 14 }}>
                  {instances.map(inst => (
                    <div key={inst.id} className="instance-card" style={{ marginBottom: 8 }}>
                      <div className="instance-card-info">
                        <ServiceIcon type={inst.type} size={22} />
                        <div>
                          <div className="instance-card-name">{inst.name}</div>
                          <div className="instance-card-url">{inst.url}</div>
                        </div>
                      </div>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => setInstances(prev => prev.filter(i => i.id !== inst.id))}
                      >✕</button>
                    </div>
                  ))}
                </div>
              )}
              <div className="wizard-fields" style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 14 }}>
                <div style={{ fontWeight: 600, fontSize: 12, color: 'var(--text-muted)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Añadir instancia
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
                  {(['radarr', 'sonarr'] as const).map(t => (
                    <div
                      key={t}
                      onClick={() => setInstDraft(p => ({ ...p, type: t }))}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer',
                        border: `1.5px solid ${instDraft.type === t ? 'var(--text-accent)' : 'var(--border-input)'}`,
                        borderRadius: 8, padding: '10px 12px',
                        background: instDraft.type === t ? 'var(--bg-card-hover)' : 'var(--bg-input)',
                      }}
                    >
                      <ServiceIcon type={t} size={24} />
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600 }}>{t === 'radarr' ? 'Radarr' : 'Sonarr'}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t === 'radarr' ? 'Películas' : 'Series'}</div>
                      </div>
                    </div>
                  ))}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div className="form-group">
                    <label className="form-label">Nombre</label>
                    <input className="form-input" placeholder={instDraft.type === 'sonarr' ? 'Sonarr principal' : 'Radarr principal'} value={instDraft.name ?? ''} onChange={e => setInstDraft(p => ({ ...p, name: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">URL</label>
                    <input className="form-input" placeholder={instDraft.type === 'sonarr' ? 'http://192.168.1.100:8989' : 'http://192.168.1.100:7878'} value={instDraft.url ?? ''} onChange={e => setInstDraft(p => ({ ...p, url: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">API key</label>
                    <input className="form-input" type="password" placeholder="API key" value={instDraft.api_key ?? ''} onChange={e => setInstDraft(p => ({ ...p, api_key: e.target.value }))} />
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
                  <label className="checkbox-label">
                    <input type="checkbox" checked={instDraft.is_4k ?? false} onChange={e => setInstDraft(p => ({ ...p, is_4k: e.target.checked }))} /> 4K
                  </label>
                  <label className="checkbox-label">
                    <input type="checkbox" checked={instDraft.is_anime ?? false} onChange={e => setInstDraft(p => ({ ...p, is_anime: e.target.checked }))} /> Anime
                  </label>
                </div>
                {instError && <div className="form-error" style={{ marginTop: 8 }}>{instError}</div>}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
                  <button className="btn btn-secondary btn-sm" onClick={addInstance} type="button">
                    + Añadir instancia
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={handleTestInst} disabled={instTesting} type="button">
                    {instTesting ? 'Probando…' : 'Probar conexión'}
                  </button>
                  {instTestResult && (
                    <span style={{ fontSize: 12, color: testResultColor(instTestResult) }}>
                      {testResultLabel(instTestResult)}
                    </span>
                  )}
                </div>
                {instTestResult?.ok && instTestResult.details?.content_visible === false && (
                  <div className="alert alert-error" style={{ marginTop: 10 }}>
                    ⚠ La conexión funciona, pero eMuwarez Uploadrr <strong>no puede ver el contenido</strong> de
                    esta instancia: sus carpetas raíz no están accesibles desde aquí (probablemente el volumen de
                    medios no está montado igual que en Radarr/Sonarr).
                    {Array.isArray(instTestResult.details?.root_folders) && (
                      <ul style={{ margin: '6px 0 0 18px', fontSize: 12 }}>
                        {(instTestResult.details.root_folders as { path: string; exists: boolean }[]).map((r, i) => (
                          <li key={i} style={{ color: r.exists ? 'var(--color-available)' : 'var(--color-missing)' }}>
                            {r.exists ? '✓' : '✗'} {r.path}
                          </li>
                        ))}
                      </ul>
                    )}
                    <div style={{ marginTop: 6 }}>Sin acceso a los ficheros no se podrá leer el mediainfo ni subir.</div>
                    <label className="checkbox-label" style={{ display: 'block', marginTop: 8 }}>
                      <input type="checkbox" checked={instPathAckSkip} onChange={e => setInstPathAckSkip(e.target.checked)} /> Entiendo, continuar igualmente
                    </label>
                  </div>
                )}
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              {!instancesCanContinue && (
                <div className="alert alert-error" style={{ marginTop: 10 }}>
                  Todavía no has añadido ninguna instancia. Si continúas sin añadir ninguna, la biblioteca
                  no tendrá contenido que cruzar hasta que la corrijas más tarde en Configuración.
                  <label className="checkbox-label" style={{ display: 'block', marginTop: 8 }}>
                    <input type="checkbox" checked={instAckSkip} onChange={e => setInstAckSkip(e.target.checked)} /> Entiendo, continuar sin añadir instancias
                  </label>
                </div>
              )}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleInstances} disabled={loading || !instancesCanContinue}>
                  {loading ? 'Guardando…' : 'Continuar'}
                </button>
              </div>
            </>
          )}

          {/* TMDb step */}
          {step === 'tmdb' && (
            <>
              <div className="wizard-step-desc">Los títulos y pósters vienen de Radarr/Sonarr, no de aquí. La API key de TMDb se usa para dos cosas concretas:</div>
              <div className="alert" style={{ marginBottom: 14, background: 'rgba(59,130,246,0.08)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px', fontSize: 12.5, color: 'var(--text-secondary)' }}>
                <div style={{ marginBottom: 6 }}>
                  <strong>1. Detectar el provider al subir:</strong> cuando el Source es <strong>WEB-DL</strong> y no se detecta ningún provider en el nombre del archivo, la app consulta los <em>watch providers</em> de TMDb (para la región elegida abajo) y propone el de mayor prioridad. Sin key, ese campo se queda en «Sin provider».
                </div>
                <div>
                  <strong>2. La necesita el subidor Uploadrr-EMU:</strong> se le pasa la key para que complete los metadatos de la ficha en eMuwarez durante la subida.
                </div>
              </div>
              <div className="wizard-fields">
                <div className="form-group">
                  <label className="form-label">API key TMDb</label>
                  <input className="form-input" value={tmdbKey} onChange={e => { setTmdbKey(e.target.value); setTmdbAckSkip(false) }} placeholder="API key de TMDb" />
                </div>
                <div className="form-group">
                  <label className="form-label">Idioma</label>
                  <select className="form-input form-select" value={tmdbLang} onChange={e => setTmdbLang(e.target.value)}>
                    {LANGUAGE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Región</label>
                  <select className="form-input form-select" value={tmdbRegion} onChange={e => setTmdbRegion(e.target.value)}>
                    {REGION_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label} ({o.value})</option>)}
                  </select>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                    Región usada para detectar en qué plataforma (provider) está disponible cada título.
                  </div>
                </div>
                <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                  <label className="checkbox-label" style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                    <input type="checkbox" checked={tmdbLocalizeTitles} onChange={e => setTmdbLocalizeTitles(e.target.checked)} style={{ marginTop: 3 }} />
                    <span>
                      Traducir títulos de series con TMDb
                      <span className="form-hint" style={{ display: 'block' }}>
                        Sonarr toma los títulos de TVDB, a menudo en inglés (p. ej. «Los Serrano» → «The Serrano»). Con esto, las series usan el título de TMDb en el idioma elegido arriba, como ya hace Radarr con las películas. Se consulta a TMDb una vez por serie y se cachea.
                      </span>
                    </span>
                  </label>
                </div>
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14, marginBottom: 4 }}>
                <button className="btn btn-secondary btn-sm" onClick={handleTestTmdb} disabled={tmdbTesting || loading} type="button">
                  {tmdbTesting ? 'Probando…' : 'Probar conexión'}
                </button>
                {tmdbTestResult && (
                  <span style={{ fontSize: 12, color: testResultColor(tmdbTestResult) }}>
                    {testResultLabel(tmdbTestResult)}
                  </span>
                )}
              </div>
              {!tmdbCanContinue && (
                <div className="alert alert-error" style={{ marginTop: 10 }}>
                  Todavía no has probado la key (o la prueba ha fallado). Si continúas sin verificarla,
                  la detección de provider no funcionará hasta que la corrijas más tarde en Configuración.
                  <label className="checkbox-label" style={{ display: 'block', marginTop: 8 }}>
                    <input type="checkbox" checked={tmdbAckSkip} onChange={e => setTmdbAckSkip(e.target.checked)} /> Entiendo, continuar sin verificar
                  </label>
                </div>
              )}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleTmdb} disabled={loading || !tmdbCanContinue}>
                  {loading ? 'Guardando…' : 'Continuar'}
                </button>
              </div>
            </>
          )}

          {/* Nomenclature + hardlink strategy step (Phase 11C) */}
          {step === 'nomenclature' && (
            <>
              <div className="wizard-step-desc">
                El directorio de hardlinks se usa para crear archivos listos para subir con la nomenclatura
                de Emuwarez, sin renombrar los archivos originales de tu biblioteca.
              </div>
              <div className="wizard-fields">
                <div className="form-group">
                  <label className="form-label">Etiqueta de subida</label>
                  <input className="form-input" value={nomTag} onChange={e => setNomTag(e.target.value)} placeholder="EMUWAREZ" />
                </div>
                <div className="form-group">
                  <label className="form-label">Directorio de hardlinks</label>
                  <input
                    className="form-input"
                    value={nomHardlinkBase}
                    onChange={e => setNomHardlinkBase(e.target.value)}
                    placeholder="/data/uploads/emu"
                    disabled={noHardlinks}
                  />
                  <span className="form-hint">Debe estar en el mismo filesystem que tu biblioteca, para evitar errores EXDEV.</span>
                </div>
              </div>
              <label className="checkbox-label" style={{ display: 'block', marginTop: 14 }}>
                <input type="checkbox" checked={noHardlinks} onChange={e => { setNoHardlinks(e.target.checked); setHardlinksConfirm('') }} /> No usar hardlinks
              </label>
              {noHardlinks && (
                <div className="alert alert-error" style={{ marginTop: 10 }}>
                  Sin hardlinks, la aplicación puede renombrar el archivo original de tu biblioteca usando la
                  nomenclatura de Emuwarez, en vez de crear una copia preparada aparte. Escribe{' '}
                  <strong>{DISABLE_HARDLINKS_TOKEN}</strong> para confirmar que entiendes esto:
                  <input
                    className="form-input"
                    style={{ marginTop: 8 }}
                    value={hardlinksConfirm}
                    onChange={e => setHardlinksConfirm(e.target.value)}
                    placeholder={DISABLE_HARDLINKS_TOKEN}
                  />
                </div>
              )}
              <div className="form-group" style={{ marginTop: 18 }}>
                <label className="form-label">Prioridad de providers</label>
                <p className="form-hint" style={{ marginBottom: 8 }}>
                  Cuando el mismo contenido está disponible en varias plataformas de streaming (Amazon,
                  Netflix, Disney+...), esta prioridad decide cuál recomendar automáticamente para la subida.
                  Arrastra para reordenar — los de arriba tienen preferencia.
                </p>
                <ProviderPriorityPicker order={nomProviderOrder} onChange={setNomProviderOrder} />
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div className="wizard-actions">
                <span />
                <button
                  className="btn btn-primary"
                  onClick={handleNomenclature}
                  disabled={loading || (noHardlinks && hardlinksConfirm !== DISABLE_HARDLINKS_TOKEN)}
                >
                  {loading ? 'Guardando…' : 'Continuar'}
                </button>
              </div>
            </>
          )}

          {/* qBittorrent step */}
          {step === 'qbit' && (
            <>
              <div className="wizard-step-desc" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ServiceIcon type="qbittorrent" size={18} /> Cliente qBittorrent que usará Uploadrr para añadir el .torrent tras subir. Opcional — puedes configurarlo luego.
              </div>
              <div className="wizard-fields">
                <div className="form-group">
                  <label className="form-label">URL del WebUI</label>
                  <input className="form-input" value={qbitUrl} onChange={e => setQbitUrl(e.target.value)} placeholder="http://127.0.0.1" />
                </div>
                <div className="form-group">
                  <label className="form-label">Puerto</label>
                  <input className="form-input" value={qbitPort} onChange={e => setQbitPort(e.target.value)} placeholder="8080" />
                </div>
                <div className="form-group">
                  <label className="form-label">Usuario</label>
                  <input className="form-input" value={qbitUser} onChange={e => setQbitUser(e.target.value)} placeholder="admin" autoComplete="off" />
                </div>
                <div className="form-group">
                  <label className="form-label">Contraseña</label>
                  <input type="password" className="form-input" value={qbitPass} onChange={e => setQbitPass(e.target.value)} placeholder="Contraseña del WebUI" autoComplete="new-password" />
                </div>
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14, marginBottom: 4 }}>
                <button className="btn btn-secondary btn-sm" onClick={handleTestQbit} disabled={qbitTesting || loading || !qbitUrl.trim()} type="button">
                  {qbitTesting ? 'Probando…' : 'Probar conexión'}
                </button>
                {qbitTestResult && (
                  <span style={{ fontSize: 12, color: testResultColor(qbitTestResult) }}>{testResultLabel(qbitTestResult)}</span>
                )}
              </div>
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleQbit} disabled={loading}>
                  {loading ? 'Guardando…' : qbitUrl.trim() ? 'Continuar' : 'Omitir'}
                </button>
              </div>
            </>
          )}

          {/* Image hosts step */}
          {step === 'imagehosts' && (
            <>
              <div className="wizard-step-desc" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ServiceIcon type="imghost" size={18} /> Dónde suben las capturas que acompañan al torrent. <strong>imgbox</strong> va por defecto (sin key); activa otros si quieres. Puedes cambiarlo luego en Configuración.
              </div>
              <div className="wizard-fields" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {imgAvailable.map(h => {
                  const enabled = imgEnabled.includes(h.id)
                  const isDefault = h.id === 'imgbox'
                  const t = imgTest[h.id]
                  return (
                    <div key={h.id} style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <input type="checkbox" checked={enabled || isDefault} disabled={isDefault}
                          onChange={() => setImgEnabled(p => p.includes(h.id) ? p.filter(x => x !== h.id) : [...p, h.id])} />
                        <ServiceIcon type="imghost" size={14} />
                        <span style={{ fontSize: 13 }}>{h.label}</span>
                        {isDefault && <span className="badge status-available" style={{ fontSize: 10 }}>por defecto</span>}
                        {h.needs_key && <span className="badge nom-na" style={{ fontSize: 10 }}>API key</span>}
                        {(enabled || isDefault) && (
                          <button className="btn btn-secondary btn-sm" style={{ marginLeft: 'auto', fontSize: 11, padding: '2px 8px' }}
                            onClick={() => handleTestImghost(h.id)} disabled={imgTesting === h.id} type="button">
                            {imgTesting === h.id ? 'Probando…' : 'Probar'}
                          </button>
                        )}
                      </div>
                      {h.needs_key && enabled && (
                        <input type="password" className="form-input" style={{ marginTop: 6 }} autoComplete="new-password"
                          value={imgKeys[h.id] ?? ''} onChange={e => setImgKeys(p => ({ ...p, [h.id]: e.target.value }))}
                          placeholder={`API key de ${h.label}`} />
                      )}
                      {t && <div style={{ fontSize: 11, marginTop: 4, color: testResultColor(t) }}>{testResultLabel(t)}</div>}
                    </div>
                  )
                })}
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleImghosts} disabled={loading}>
                  {loading ? 'Guardando…' : 'Continuar'}
                </button>
              </div>
            </>
          )}

          {/* Complete step */}
          {step === 'complete' && (
            <>
              <div className="wizard-step-desc">
                Haz clic en Completar para inicializar la aplicación y entrar al dashboard.
              </div>
              <div className="alert alert-info">
                Cualquier paso que hayas saltado (eMuwarez, instancias, TMDb) se puede configurar más tarde
                desde Configuración. Si has añadido instancias Radarr/Sonarr, la primera sincronización se
                ejecutará desde el dashboard.
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleComplete} disabled={loading}>
                  {loading ? 'Inicializando…' : 'Completar setup'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
