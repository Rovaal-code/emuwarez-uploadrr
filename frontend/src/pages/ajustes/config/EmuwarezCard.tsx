import { useState } from 'react'
import { testEmuwarezConnection, type IntegrationTestResult } from '../../../api/integrationTests'
import { useCooldown } from '../../../hooks/useCooldown'
import { ServiceIcon } from '../../../components/ServiceIcon'
import { InfoIcon } from '../../../components/InfoIcon'
import { CheckStatusIcon } from '../../../components/DetailCard'
import { testResultLabel, testResultColor, emuTestCooldownSeconds } from '../../../utils/integrationResult'
import type { ConfigForm } from './useConfigForm'

export function EmuwarezCard({ form }: { form: ConfigForm }) {
  const { settings, newEmuKey, setNewEmuKey, emuUsername, setEmuUsername, tags, setTags, nuevoTag, setNuevoTag, borrador } = form
  const [testingEmu, setTestingEmu] = useState(false)
  const [emuTestResult, setEmuTestResult] = useState<IntegrationTestResult | null>(null)
  const emuCooldown = useCooldown()

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

  function anadirTag() {
    const t = nuevoTag.trim()
    if (t && !tags.includes(t)) setTags([...tags, t])
    setNuevoTag('')
  }

  return (
    <div className="placeholder-card">
      <h3 className="aj-card-titulo aj-mb-14">
        <ServiceIcon type="emu" size={18} /> eMuwarez
      </h3>
      <div className="form-group aj-mb-12">
        <label className="form-label">Estado de la API key</label>
        <div className="aj-fs-13">
          {settings?.emu_api_key_configured
            ? <><span className="aj-ok"><CheckStatusIcon status="ok" /> Configurada</span>{settings.emu_api_key_masked && <code className="aj-code-mascara">{settings.emu_api_key_masked}</code>}</>
            : <span className="aj-err">✗ No configurada</span>}
        </div>
      </div>
      <div className="form-group aj-mb-12">
        <label className="form-label">Nueva API key <span className="form-hint">(dejar vacío para mantener la actual)</span></label>
        <input
          type="password"
          className="form-input"
          value={newEmuKey}
          onChange={e => setNewEmuKey(e.target.value)}
          placeholder="API key de eMuwarez"
          autoComplete="new-password"
        />
        <span className="form-hint">Usada para leer el catálogo y las peticiones de eMuwarez.</span>
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
          <span className="aj-res-12" style={{ color: testResultColor(emuTestResult) }}>
            {testResultLabel(emuTestResult)}
          </span>
        )}
      </div>
      <div className="form-group aj-mt-14">
        <label className="form-label aj-flex-c-6">
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
      <div className="form-group aj-mt-14">
        <label className="form-label aj-flex-c-6" htmlFor="nuevo-grupo-de-subida">
          Grupos de subida
          <InfoIcon text="El tag que va tras el último «-» en el nombre del torrent (tu grupo/usuario). El primero es el que sale por defecto al subir; los demás se eligen en el asistente." />
        </label>
        <div className="aj-col-6 aj-mb-8">
          {tags.map((t, i) => (
            <div key={t} className="aj-flex-c-8">
              <span className="aj-ellipsis-13">{t}</span>
              {i === 0
                ? <span className="badge status-available">por defecto</span>
                : <button type="button" className="btn-icon" title="Usar por defecto" aria-label={`Usar ${t} por defecto`}
                    onClick={() => setTags([t, ...tags.filter(x => x !== t)])}>☆</button>}
              {tags.length > 1 && (
                <button type="button" className="btn-icon" aria-label={`Quitar ${t}`}
                  onClick={() => { setTags(tags.filter(x => x !== t)); if (borrador === t) setNuevoTag('') }}>✕</button>
              )}
            </div>
          ))}
        </div>
        <div className="aj-flex-8">
          <input id="nuevo-grupo-de-subida" className="form-input" value={nuevoTag} onChange={e => setNuevoTag(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); anadirTag() } }}
            placeholder="Añadir otro grupo" />
          <button type="button" className="btn btn-secondary" onClick={anadirTag} disabled={!nuevoTag.trim()}>Añadir</button>
        </div>
      </div>
    </div>
  )
}
