import { useState } from 'react'
import { testQbitConnection, type IntegrationTestResult } from '../../../api/integrationTests'
import { ServiceIcon } from '../../../components/ServiceIcon'
import { useTooltip } from '../../../components/Tooltip'
import { Campo, ResultadoPrueba } from '../Campo'
import { CabeceraTarjeta } from '../CabeceraTarjeta'
import type { ConfigForm } from './useConfigForm'

export function QbitCard({ form }: { form: ConfigForm }) {
  const { settings, qbitUrl, setQbitUrl, qbitPublicUrl, setQbitPublicUrl, qbitTag, setQbitTag, qbitUser, setQbitUser, qbitPass, setQbitPass, quitarQbitPass, setQuitarQbitPass, qbitQui, setQbitQui, quitarQui, setQuitarQui, errores, marcarTocado } = form
  const [testingQbit, setTestingQbit] = useState(false)
  const [qbitTestResult, setQbitTestResult] = useState<IntegrationTestResult | null>(null)
  const [showQbitUser, setShowQbitUser] = useState(false)
  const qbitUserEyeTip = useTooltip(showQbitUser ? 'Ocultar usuario' : 'Mostrar usuario')

  async function handleTestQbit() {
    setTestingQbit(true)
    setQbitTestResult(null)
    try {
      const r = await testQbitConnection({
        url: qbitUrl.trim() || undefined,
        username: qbitUser.trim() || undefined,
        password: qbitPass.trim() || undefined,
        qui_proxy_url: quitarQui ? '' : (qbitQui.trim() || undefined),
      })
      setQbitTestResult(r)
    } catch {
      setQbitTestResult({ ok: false, service: 'qbittorrent', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setTestingQbit(false)
    }
  }

  return (
    <div className="placeholder-card">
      <CabeceraTarjeta
        icono={<ServiceIcon type="qbittorrent" size={18} />}
        titulo="qBittorrent"
      />
      <Campo etiqueta="URL del WebUI" error={errores.qbitUrl}>
        {c => <input {...c} className="form-input" value={qbitUrl} onChange={e => setQbitUrl(e.target.value)} onBlur={() => marcarTocado('qbitUrl')} placeholder="http://127.0.0.1" inputMode="url" autoComplete="off" spellCheck={false} />}
      </Campo>
      <Campo
        etiqueta="URL pública del WebUI"
        nota="opcional"
        ayuda="Cómo abres qBittorrent en tu navegador, si no es la URL de arriba (puede ser el nombre de un contenedor). Activa «Abrir en qBittorrent» en las subidas completadas."
        error={errores.qbitPublicUrl}
      >
        {c => <input {...c} className="form-input" value={qbitPublicUrl} onChange={e => setQbitPublicUrl(e.target.value)} onBlur={() => marcarTocado('qbitPublicUrl')} placeholder="https://qbittorrent.midominio.es" inputMode="url" autoComplete="off" spellCheck={false} />}
      </Campo>
      <Campo etiqueta="Tag">
        {c => <input {...c} className="form-input" value={qbitTag} onChange={e => setQbitTag(e.target.value)} placeholder="Subidas" autoComplete="off" />}
      </Campo>
      <Campo etiqueta="Usuario">
        {c => (
          <div className="aj-con-ojo">
            <input
              {...c}
              className="form-input aj-pr-38"
              type={showQbitUser ? 'text' : 'password'}
              value={qbitUser}
              onChange={e => setQbitUser(e.target.value)}
              placeholder="admin"
              autoComplete="off"
            />
            <button
              type="button"
              onClick={() => setShowQbitUser(s => !s)}
              aria-label={showQbitUser ? 'Ocultar usuario' : 'Mostrar usuario'}
              aria-pressed={showQbitUser}
              className="aj-ojo"
              {...qbitUserEyeTip.triggerProps}
            >
              {qbitUserEyeTip.tooltipNode}
              {showQbitUser ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                  <line x1="1" y1="1" x2="23" y2="23" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
            </button>
          </div>
        )}
      </Campo>
      <Campo etiqueta="Contraseña" nota="dejar vacío para mantener la actual">
        {c => (
          <>
            <input {...c} type="password" className="form-input" value={qbitPass} onChange={e => { setQbitPass(e.target.value); setQuitarQbitPass(false) }} placeholder={quitarQbitPass ? 'Se quitará al guardar' : settings?.qbit_password_configured ? '••••••••' : 'Contraseña del WebUI'} autoComplete="new-password" />
            {settings?.qbit_password_configured && !qbitPass && (
              <button type="button" className="btn btn-secondary btn-sm aj-self-start" onClick={() => setQuitarQbitPass(q => !q)}>
                {quitarQbitPass ? 'No quitarla' : 'Quitar la contraseña'}
              </button>
            )}
          </>
        )}
      </Campo>
      <Campo
        etiqueta={<>Proxy de <a href="https://getqui.com/docs/features/reverse-proxy" target="_blank" rel="noreferrer">qui</a></>}
        nota="opcional; con él no hacen falta usuario ni contraseña"
        error={errores.qbitQui}
      >
        {c => (
          <>
            <input
              {...c}
              type="password"
              className="form-input"
              value={qbitQui}
              onChange={e => { setQbitQui(e.target.value); setQuitarQui(false) }}
              onBlur={() => marcarTocado('qbitQui')}
              placeholder={quitarQui ? 'Se quitará al guardar' : settings?.qbit_qui_configured ? '••••••••' : 'http://qui:7476/proxy/<clave>'}
              autoComplete="off"
            />
            {settings?.qbit_qui_configured && !qbitQui && (
              <button type="button" className="btn btn-secondary btn-sm aj-self-start" onClick={() => setQuitarQui(q => !q)}>
                {quitarQui ? 'No quitarlo' : 'Quitar el proxy de qui'}
              </button>
            )}
          </>
        )}
      </Campo>
      <div className="aj-acciones">
        <button className="btn btn-secondary btn-sm" onClick={handleTestQbit} disabled={testingQbit} type="button">
          {testingQbit ? 'Probando…' : 'Probar conexión'}
        </button>
        <ResultadoPrueba resultado={qbitTestResult} />
      </div>
    </div>
  )
}
