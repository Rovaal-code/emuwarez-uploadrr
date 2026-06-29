import { useState } from 'react'
import { setupAdmin, setupBase, setupUploadrr, setupTmdb, setupEmu, setupInstances, setupComplete } from '../api/setup'
import { login } from '../api/auth'
import { ApiClientError } from '../api/client'
import { ServiceIcon } from '../components/ServiceIcon'
import { SETUP_STEPS, SETUP_STEP_LABELS } from '../types/domain'
import type { SetupStep } from '../types/domain'
import type { SetupStatusResponse } from '../types/api'

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
    ? 'admin'
    : (setupStatus.next_step as SetupStep) ?? 'complete'

  const [step, setStep] = useState<SetupStep>(initialStep)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [adminCreated, setAdminCreated] = useState(false)

  // Admin step state
  const [adminUser, setAdminUser] = useState('')
  const [adminPass, setAdminPass] = useState('')
  const [adminPass2, setAdminPass2] = useState('')

  // Base step state
  const [appName, setAppName] = useState('eMuwarez Uploadrr')
  const [timezone, setTimezone] = useState('Europe/Madrid')

  // Uploadrr step state
  const [uploadrrPath, setUploadrrPath] = useState('./Uploadrr')

  // TMDb step state
  const [tmdbKey, setTmdbKey] = useState('')
  const [tmdbLang, setTmdbLang] = useState('es-ES')
  const [tmdbRegion, setTmdbRegion] = useState('ES')

  // EMU step state
  const [emuKey, setEmuKey] = useState('')
  const [emuEndpoint, setEmuEndpoint] = useState('')

  // Instances step state
  const [instances, setInstances] = useState<InstanceDraft[]>([])
  const [instDraft, setInstDraft] = useState<Partial<InstanceDraft>>({ type: 'radarr', is_4k: false, is_anime: false })
  const [instError, setInstError] = useState<string | null>(null)

  function wrap(fn: () => Promise<void>) {
    return async () => {
      setError(null)
      setLoading(true)
      try {
        await fn()
      } catch (err) {
        setError(err instanceof ApiClientError ? err.message : 'Error inesperado')
      } finally {
        setLoading(false)
      }
    }
  }

  const handleAdmin = wrap(async () => {
    if (adminPass !== adminPass2) throw new Error('Las contraseñas no coinciden')
    await setupAdmin(adminUser.trim(), adminPass)
    // Auto-login after admin creation
    await login(adminUser.trim(), adminPass)
    setAdminCreated(true)
    setStep('base')
  })

  const handleBase = wrap(async () => {
    await setupBase(appName, timezone)
    setStep('uploadrr')
  })

  const handleUploadrr = wrap(async () => {
    await setupUploadrr(uploadrrPath)
    setStep('tmdb')
  })

  const handleTmdb = wrap(async () => {
    await setupTmdb(tmdbKey, tmdbLang, tmdbRegion)
    setStep('emu')
  })

  const handleEmu = wrap(async () => {
    await setupEmu(emuKey, emuEndpoint || null)
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
    setStep('complete')
  })

  const handleComplete = wrap(async () => {
    await setupComplete()
    onComplete()
  })

  const stepIdx = SETUP_STEPS.indexOf(step)

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
                </div>
                <div className="form-group">
                  <label className="form-label">Confirmar contraseña</label>
                  <input className="form-input" type="password" placeholder="Repite la contraseña" value={adminPass2} onChange={e => setAdminPass2(e.target.value)} />
                </div>
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleAdmin} disabled={loading || !adminUser || !adminPass || !adminPass2}>
                  {loading ? 'Creando…' : 'Crear admin'}
                </button>
              </div>
            </>
          )}

          {/* Base step */}
          {step === 'base' && (
            <>
              <div className="wizard-step-desc">Configura el nombre y zona horaria de la aplicación.</div>
              <div className="wizard-fields">
                <div className="form-group">
                  <label className="form-label">Nombre de la aplicación</label>
                  <input className="form-input" value={appName} onChange={e => setAppName(e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Zona horaria</label>
                  <input className="form-input" value={timezone} onChange={e => setTimezone(e.target.value)} placeholder="Europe/Madrid" />
                </div>
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleBase} disabled={loading}>
                  {loading ? 'Guardando…' : 'Continuar'}
                </button>
              </div>
            </>
          )}

          {/* Uploadrr step */}
          {step === 'uploadrr' && (
            <>
              <div className="wizard-step-desc">Indica la ruta del directorio Uploadrr (motor de subida).</div>
              <div className="wizard-fields">
                <div className="form-group">
                  <label className="form-label">Ruta Uploadrr</label>
                  <input className="form-input" value={uploadrrPath} onChange={e => setUploadrrPath(e.target.value)} placeholder="./Uploadrr" />
                  <span className="form-hint">Ruta al directorio que contiene upload.py</span>
                </div>
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleUploadrr} disabled={loading}>
                  {loading ? 'Guardando…' : 'Continuar'}
                </button>
              </div>
            </>
          )}

          {/* TMDb step */}
          {step === 'tmdb' && (
            <>
              <div className="wizard-step-desc">API key de TMDb para enriquecimiento de metadatos (título en español, pósters).</div>
              <div className="wizard-fields">
                <div className="form-group">
                  <label className="form-label">API key TMDb</label>
                  <input className="form-input" value={tmdbKey} onChange={e => setTmdbKey(e.target.value)} placeholder="Tu API key de TMDb" />
                </div>
                <div className="form-group">
                  <label className="form-label">Idioma</label>
                  <input className="form-input" value={tmdbLang} onChange={e => setTmdbLang(e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Región</label>
                  <input className="form-input" value={tmdbRegion} onChange={e => setTmdbRegion(e.target.value)} />
                </div>
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleTmdb} disabled={loading}>
                  {loading ? 'Guardando…' : 'Continuar'}
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
                  <input className="form-input" value={emuKey} onChange={e => setEmuKey(e.target.value)} placeholder="Tu API key de eMuwarez" />
                </div>
                <div className="form-group">
                  <label className="form-label">Endpoint peticiones (opcional)</label>
                  <input className="form-input" value={emuEndpoint} onChange={e => setEmuEndpoint(e.target.value)} placeholder="https://emuwarez.com/api/..." />
                  <span className="form-hint">Puedes configurarlo más adelante cuando captures el endpoint real.</span>
                </div>
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleEmu} disabled={loading}>
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
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div className="form-group">
                    <label className="form-label">Tipo</label>
                    <select className="form-input form-select" value={instDraft.type} onChange={e => setInstDraft(p => ({ ...p, type: e.target.value as 'radarr' | 'sonarr' }))}>
                      <option value="radarr">Radarr</option>
                      <option value="sonarr">Sonarr</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Nombre</label>
                    <input className="form-input" placeholder="Radarr principal" value={instDraft.name ?? ''} onChange={e => setInstDraft(p => ({ ...p, name: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">URL</label>
                    <input className="form-input" placeholder="http://192.168.1.100:7878" value={instDraft.url ?? ''} onChange={e => setInstDraft(p => ({ ...p, url: e.target.value }))} />
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
                <button className="btn btn-secondary btn-sm" style={{ marginTop: 10 }} onClick={addInstance}>
                  + Añadir instancia
                </button>
              </div>
              {error && <div className="alert alert-error" style={{ marginTop: 14 }}>{error}</div>}
              <div className="wizard-actions">
                <span />
                <button className="btn btn-primary" onClick={handleInstances} disabled={loading}>
                  {loading ? 'Guardando…' : 'Continuar'}
                </button>
              </div>
            </>
          )}

          {/* Complete step */}
          {step === 'complete' && (
            <>
              <div className="wizard-step-desc">
                Todo está configurado. Haz clic en Completar para inicializar la aplicación y entrar al dashboard.
              </div>
              <div className="alert alert-info">
                Si has añadido instancias Radarr/Sonarr, la primera sincronización se ejecutará desde el dashboard.
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
