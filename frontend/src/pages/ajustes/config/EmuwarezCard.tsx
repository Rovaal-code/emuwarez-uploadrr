import { useState } from 'react'
import { testEmuwarezConnection, type IntegrationTestResult } from '../../../api/integrationTests'
import { useCooldown } from '../../../hooks/useCooldown'
import { ServiceIcon } from '../../../components/ServiceIcon'
import { InfoIcon } from '../../../components/InfoIcon'
import { emuTestCooldownSeconds } from '../../../utils/integrationResult'
import { Campo, EstadoSecreto, ResultadoPrueba } from '../Campo'
import { CabeceraTarjeta } from '../CabeceraTarjeta'
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
      <CabeceraTarjeta
        icono={<ServiceIcon type="emu" size={18} />}
        titulo="eMuwarez"
        lateral={<EstadoSecreto configurado={settings?.emu_api_key_configured} enmascarado={settings?.emu_api_key_masked} />}
      />
      <Campo
        etiqueta={settings?.emu_api_key_configured ? 'Nueva API key' : 'API key'}
        nota={settings?.emu_api_key_configured ? 'dejar vacío para mantener la actual' : undefined}
        ayuda="Usada para leer el catálogo y las peticiones de eMuwarez."
      >
        {c => (
          <input
            {...c}
            type="password"
            className="form-input"
            value={newEmuKey}
            onChange={e => setNewEmuKey(e.target.value)}
            placeholder="API key de eMuwarez"
            autoComplete="new-password"
          />
        )}
      </Campo>
      <div className="aj-acciones">
        <button
          className="btn btn-secondary btn-sm"
          onClick={handleTestEmu}
          disabled={testingEmu || emuCooldown.active}
          type="button"
        >
          {testingEmu ? 'Probando…' : emuCooldown.active ? `Espera ${emuCooldown.remaining}s` : 'Probar conexión'}
        </button>
        <ResultadoPrueba resultado={emuTestResult} />
      </div>
      <Campo
        etiqueta="Mi usuario de eMuwarez"
        info={<InfoIcon text="Tu nombre de usuario en eMuwarez. Se usa para reconocer cuáles de todas las peticiones descargadas las has creado tú, y así poder mostrártelas en 'Mis peticiones'." />}
      >
        {c => (
          <input
            {...c}
            className="form-input"
            value={emuUsername}
            onChange={e => setEmuUsername(e.target.value)}
            placeholder="Tu nombre de usuario en eMuwarez"
          />
        )}
      </Campo>
      <Campo
        etiqueta="Grupos de subida"
        info={<InfoIcon text="El tag que va tras el último «-» en el nombre del torrent (tu grupo/usuario). El primero es el que sale por defecto al subir; los demás se eligen en el asistente." />}
      >
        {c => (
          <>
            <ul className="aj-grupos" aria-label="Grupos guardados">
              {tags.map((t, i) => (
                <li key={t} className="aj-grupos__fila">
                  <span className="aj-grupos__nombre">{t}</span>
                  {i === 0
                    ? <span className="badge status-available">por defecto</span>
                    : <button type="button" className="btn-icon" title="Usar por defecto" aria-label={`Usar ${t} por defecto`}
                        onClick={() => setTags([t, ...tags.filter(x => x !== t)])}>☆</button>}
                  {tags.length > 1 && (
                    <button type="button" className="btn-icon" aria-label={`Quitar ${t}`}
                      onClick={() => { setTags(tags.filter(x => x !== t)); if (borrador === t) setNuevoTag('') }}>✕</button>
                  )}
                </li>
              ))}
            </ul>
            <div className="aj-fila-campo">
              <input {...c} className="form-input" value={nuevoTag} onChange={e => setNuevoTag(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); anadirTag() } }}
                placeholder="Añadir otro grupo" />
              <button type="button" className="btn btn-secondary btn-sm" onClick={anadirTag} disabled={!nuevoTag.trim()}>Añadir</button>
            </div>
          </>
        )}
      </Campo>
    </div>
  )
}
