import { useState, useEffect } from 'react'
import {
  setupAdmin, setupTmdb, setupEmu, setupInstances,
  setupQbit, setupImghosts, setupComplete,
} from '../api/setup'
import { login } from '../api/auth'
import { startLibrarySync } from '../api/library'
import { fetchSettings, updateSettings } from '../api/settings'
import { testTmdbConnection, testEmuwarezConnection, testArrConnection, testQbitConnection, testImghostConnection, type IntegrationTestResult } from '../api/integrationTests'
import { ServiceIcon } from '../components/ServiceIcon'
import { ProviderPriorityPicker } from '../components/ProviderPriorityPicker'
import { REGION_OPTIONS, LANGUAGE_OPTIONS } from '../constants/regionLanguage'
import { SETUP_STEPS, SETUP_STEP_LABELS } from '../types/domain'
import type { SetupStep } from '../types/domain'
import type { SetupStatusResponse } from '../types/api'
import { testResultLabel, testResultColor, emuTestCooldownSeconds } from '../utils/integrationResult'
import { useCooldown } from '../hooks/useCooldown'
import { HoverTitle } from '../components/Tooltip'

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

// Same icon as its Configuración counterpart, for the steps that also exist
// as their own card there (Cuenta, TMDb, qBittorrent, Proveedores de vídeo,
// Proveedores de imágenes) — the other steps (bienvenida, eMuwarez,
// instancias, completado) don't have a matching Settings card, so no icon.
function StepTitleIcon({ step }: { step: string }) {
  if (step === 'admin') {
    // Same person shape (and blue) as the Configuración > Cuenta card's own
    // icon (SettingsPage.tsx) — this step IS that same card (creating/
    // naming the admin account), so it should read as the same thing, not
    // as the general Configuración gear.
    return (
      <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="1.75" aria-hidden>
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
    )
  }
  if (step === 'emu') return <ServiceIcon type="emu" size={20} />
  if (step === 'instances') {
    return (
      <span style={{ display: 'inline-flex', gap: 6 }}>
        <ServiceIcon type="radarr" size={20} />
        <ServiceIcon type="sonarr" size={20} />
      </span>
    )
  }
  if (step === 'tmdb') return <ServiceIcon type="tmdb" size={20} />
  if (step === 'qbit') return <ServiceIcon type="qbittorrent" size={20} />
  if (step === 'imagehosts') return <ServiceIcon type="imghost" size={20} />
  if (step === 'providers') {
    return (
      <svg width={20} height={20} viewBox="0 0 24 24" fill="none" aria-hidden>
        <rect x="2.5" y="5" width="19" height="14" rx="2.5" stroke="#8b5cf6" strokeWidth="1.6" />
        <path d="M10 9.2v5.6l4.5-2.8z" fill="#8b5cf6" />
      </svg>
    )
  }
  return null
}

// One-line "eMuwarez Uploadrr es una aplicación que:" cards on the welcome
// step — icon + a single line of text each, replacing the old plain bullet
// list so the page reads at a glance instead of as a wall of text.
function FeatureCard({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="wizard-feature-card">
      <div className="wizard-feature-icon">{icon}</div>
      <div className="wizard-feature-text">{text}</div>
    </div>
  )
}

const FEATURE_ICONS = {
  sync: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 2v6h-6" /><path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
      <path d="M3 22v-6h6" /><path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
    </svg>
  ),
  upload: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 19V6M6 12l6-6 6 6" /><path d="M5 21h14" />
    </svg>
  ),
  audio: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 10v4M7 6v12M11 3v18M15 6v12M19 10v4" />
    </svg>
  ),
  parallel: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z" />
    </svg>
  ),
  unique: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2l2.4 7.2H22l-6 4.6 2.3 7.2-6.3-4.6-6.3 4.6 2.3-7.2-6-4.6h7.6z" />
    </svg>
  ),
  requests: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M8 6h13M8 12h13M8 18h13" /><path d="M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  ),
  recommendUpload: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7" /><path d="M16 6l-4-4-4 4" /><path d="M12 2v14" />
    </svg>
  ),
  recommendRequest: (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 5v14M5 12h14" />
    </svg>
  ),
}

function StepsBar({ current, steps }: { current: string; steps: readonly string[] }) {
  const currentIdx = steps.indexOf(current)
  return (
    <div className="wizard-steps-bar">
      {steps.map((s, i) => (
        <HoverTitle
          key={s}
          className={`wizard-step-dot${i < currentIdx ? ' done' : i === currentIdx ? ' active' : ''}`}
          tip={SETUP_STEP_LABELS[s as SetupStep]}
        >
          {null}
        </HoverTitle>
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
  const [tmdbAckSkip, setTmdbAckSkip] = useState(false)

  // EMU step state — no skip option: eMuwarez integration is the core of
  // this app, so a validated key is mandatory to finish setup (see
  // emuCanContinue below).
  const [emuKey, setEmuKey] = useState('')
  const [emuUsername, setEmuUsername] = useState('')

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

  // Providers step: load the same real, persisted order Configuración
  // reads (falls back to the backend's own default when nothing was ever
  // saved) instead of a separately hand-typed copy of that default here,
  // which could silently drift out of sync.
  useEffect(() => {
    fetchSettings().then(s => { if (s.provider_priority_order?.length) setNomProviderOrder(s.provider_priority_order) }).catch(() => { /* keep the built-in default */ })
  }, [])

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

  // Upload tag — set on the eMuwarez step now (see handleEmu).
  const [nomTag, setNomTag] = useState('EMUWAREZ')
  // Providers step state. Same default as the backend's provider_priority_order
  // setting (web/api/settings.py::_DEFAULT_PRIORITY) — offered here too so it's
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
    if (emuKey.trim()) {
      await setupEmu(emuKey)
    }
    // Username/tag are independent of the API key itself — worth keeping
    // even if the key is being skipped for now.
    if (emuUsername.trim() || nomTag.trim()) {
      await updateSettings({
        emu_username: emuUsername.trim() || undefined,
        default_release_tag: nomTag.trim() || undefined,
      })
    }
    setStep('instances')
  })

  async function addInstance() {
    setInstError(null)
    if (!instDraft.name?.trim()) { setInstError('El nombre es obligatorio'); return }
    if (!instDraft.url?.trim()) { setInstError('La URL es obligatoria'); return }
    if (!instDraft.api_key?.trim()) { setInstError('La API key es obligatoria'); return }
    // Always re-test right before adding (not just when "Probar conexión" was
    // clicked separately) — otherwise a well-formed but unreachable/wrong
    // instance got added silently, only failing much later when a sync ran.
    setInstTesting(true)
    setInstTestResult(null)
    let result: IntegrationTestResult
    try {
      result = await testArrConnection({
        kind: instDraft.type ?? 'radarr',
        base_url: instDraft.url!.trim(),
        api_key: instDraft.api_key!.trim(),
      })
    } catch {
      result = { ok: false, service: instDraft.type ?? 'arr', status: 'connection_error', message: 'Error al contactar con el servidor' }
    }
    setInstTestResult(result)
    setInstTesting(false)
    if (!result.ok) {
      setInstError(result.message || 'No se pudo conectar con la instancia.')
      return
    }
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
    setInstTestResult(null)
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
      await setupTmdb(tmdbKey, tmdbLang, tmdbRegion)
    }
    setStep('qbit')
  })

  const handleQbit = wrap(async () => {
    // Optional/skippable: an empty URL just moves on without configuring qBit.
    if (qbitUrl.trim()) {
      await setupQbit(qbitUrl.trim(), qbitPort.trim() || '8080', qbitUser.trim(), qbitPass)
    }
    setStep('providers')
  })

  const handleProviders = wrap(async () => {
    await updateSettings({ provider_priority_order: nomProviderOrder })
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
      // Fire-and-forget: a full sync can take a while (or even a few
      // minutes on a real library), and awaiting it here used to leave this
      // screen looking frozen — only the button's own label quietly changed
      // to "Inicializando…" with no other feedback. This now flows through
      // the same active/done lifecycle as the manual "sincronizar
      // biblioteca" button (services/library.py::_lib_sync_guard), so once
      // AppShell mounts, SyncContext picks it up on its own and shows it
      // live in the top-bar banner — no need to block finishing setup on it.
      startLibrarySync(true).catch(() => { /* the Dashboard's own sync button covers a failed kick-off */ })
    }
    onComplete()
  })

  const stepIdx = SETUP_STEPS.indexOf(step)
  const adminPasswordValid = PASSWORD_RULES.every(rule => rule.test(adminPass))
  // No skip escape hatch here (unlike TMDb/instances/qBit below) — an
  // unverified or invalid eMuwarez key would let setup finish while every
  // eMuwarez-dependent feature (sync, requests, catalog) silently can't work.
  const emuCanContinue = Boolean(emuTestResult?.ok)
  const instancesCanContinue = instances.length > 0 || instAckSkip
  const tmdbCanContinue = Boolean(tmdbTestResult?.ok) || tmdbAckSkip

  return (
    <div className="setup-wizard-wrap hud-app">
      <div className="setup-wizard">
        <div className="wizard-logo">
          <ServiceIcon type="emu" size={40} />
          <div className="wizard-logo-title" style={{ marginTop: 8 }}>eMuwarez Uploadrr</div>
          <div className="wizard-logo-sub">Asistente de configuración inicial</div>
        </div>

        <StepsBar current={step} steps={SETUP_STEPS} />

        <div className="wizard-card">
          <div className="wizard-step-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <StepTitleIcon step={step} />
            {stepIdx + 1}. {SETUP_STEP_LABELS[step]}
          </div>

          {/* Welcome step */}
          {step === 'welcome' && (
            <>
              <div className="wizard-step-desc" style={{ marginBottom: 12 }}>
                eMuwarez Uploadrr es una aplicación que:
              </div>
              <div className="wizard-feature-grid">
                <FeatureCard icon={FEATURE_ICONS.sync} text="Gestiona y sincroniza tus bibliotecas de Radarr y Sonarr" />
                <FeatureCard icon={FEATURE_ICONS.upload} text="Prepara y sube contenido siguiendo la nomenclatura de eMuwarez" />
                <FeatureCard icon={FEATURE_ICONS.audio} text="Reordena y renombra las pistas de video, audio y subtítulos adecuadamente" />
                <FeatureCard icon={FEATURE_ICONS.parallel} text="Cualquier subida se puede ejecutar en paralelo" />
                <FeatureCard icon={FEATURE_ICONS.unique} text="Muestra el contenido único que aún no está en eMuwarez" />
                <FeatureCard icon={FEATURE_ICONS.requests} text="Se conecta con eMuwarez para listar las peticiones actuales" />
                <FeatureCard icon={FEATURE_ICONS.recommendUpload} text="Recomienda subir contenido compatible con una petición existente" />
                <FeatureCard icon={FEATURE_ICONS.recommendRequest} text="Te recomienda crear una petición si tienes contenido faltante nuevo" />
              </div>
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
                  <input className="form-input" value={emuKey} onChange={e => { setEmuKey(e.target.value); setEmuTestResult(null) }} placeholder="Tu API key de eMuwarez" />
                </div>
                <div className="form-group">
                  <label className="form-label">Mi usuario de eMuwarez</label>
                  <input className="form-input" value={emuUsername} onChange={e => setEmuUsername(e.target.value)} placeholder="Tu nombre de usuario en eMuwarez" />
                  <span className="form-hint">Se usa para reconocer cuáles de todas las peticiones descargadas las has creado tú.</span>
                </div>
                <div className="form-group">
                  <label className="form-label">Tag del grupo de subida</label>
                  <input className="form-input" value={nomTag} onChange={e => setNomTag(e.target.value)} placeholder="EMUWAREZ" />
                  <span className="form-hint">El tag que va tras el último «-» en el nombre del torrent (tu grupo/usuario).</span>
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
                  Necesitas una key de eMuwarez válida para continuar: pulsa "Probar conexión" y espera a
                  que confirme que funciona. Esta integración es el núcleo de la app, así que aquí no se
                  puede saltar el paso.
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
                  <button className="btn btn-secondary btn-sm" onClick={addInstance} disabled={instTesting} type="button">
                    {instTesting ? 'Comprobando…' : '+ Añadir instancia'}
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
                  <strong>1. Detectar el proveedor al subir:</strong> cuando el Source es <strong>WEB-DL</strong> y no se detecta ningún proveedor en el nombre del archivo, la app consulta los <em>watch providers</em> de TMDb (para la región elegida abajo) y propone el de mayor prioridad. Sin key, ese campo se queda en «Sin proveedor».
                </div>
                <div style={{ marginBottom: 6 }}>
                  <strong>2. La necesita el subidor Uploadrr-EMU:</strong> se le pasa la key para que complete los metadatos de la ficha en eMuwarez durante la subida.
                </div>
                <div>
                  <strong>3. Traducir títulos de series:</strong> Sonarr toma los títulos de TVDB, a menudo en inglés (p. ej. «Los Serrano» → «The Serrano»). Con la key, las series usan el título de TMDb en el idioma elegido abajo, como ya hace Radarr con las películas. Se consulta a TMDb una vez por serie y se cachea.
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
                    Región usada para detectar en qué plataforma (proveedor) está disponible cada título.
                  </div>
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
                  Todavía no has probado la key (o la prueba ha fallado). Si continúas sin verificarla, no
                  podrás: (a) obtener los nombres en español de las series y (b) detectar los posibles
                  proveedores en subidas WEB-DL sin proveedor o mal catalogados por Radarr/Sonarr. Podrás
                  configurarlo más tarde en Configuración.
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

          {/* qBittorrent step */}
          {step === 'qbit' && (
            <>
              <div className="wizard-step-desc">
                Cliente qBittorrent que usará Uploadrr para añadir el .torrent tras subir.
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
              {!qbitUrl.trim() && (
                <div className="alert alert-error" style={{ marginTop: 10 }}>
                  Sin qBittorrent configurado, los torrents no se añadirán automáticamente a su cola tras
                  subir: tendrás que hacerlo a mano. Podrás configurarlo más tarde en Configuración.
                </div>
              )}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleQbit} disabled={loading}>
                  {loading ? 'Guardando…' : qbitUrl.trim() ? 'Continuar' : 'Omitir'}
                </button>
              </div>
            </>
          )}

          {/* Video providers step */}
          {step === 'providers' && (
            <>
              <div className="wizard-step-desc">
                Cuando el mismo contenido está disponible en varias plataformas de streaming (Amazon,
                Netflix, Disney+...), esta prioridad decide cuál recomendar automáticamente para la subida.
                Arrastra para reordenar: los de arriba tienen preferencia. Cada proveedor tiene su propio
                icono para reconocerlo de un vistazo.
              </div>
              <ProviderPriorityPicker order={nomProviderOrder} onChange={setNomProviderOrder} linkIcons={false} />
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleProviders} disabled={loading}>
                  {loading ? 'Guardando…' : 'Continuar'}
                </button>
              </div>
            </>
          )}

          {/* Image hosts step */}
          {step === 'imagehosts' && (
            <>
              <div className="wizard-step-desc">
                Dónde suben las capturas que acompañan al torrent. <strong>imgbox</strong> va por defecto (sin key); activa otros si quieres. Puedes cambiarlo luego en Configuración.
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
                Cualquier paso que hayas saltado (Instancias, TMDb, qBittorent...) se puede configurar más tarde
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
