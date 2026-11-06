import { useState } from 'react'
import { testTmdbConnection, type IntegrationTestResult } from '../../../api/integrationTests'
import { ServiceIcon } from '../../../components/ServiceIcon'
import { REGION_OPTIONS } from '../../../constants/regionLanguage'
import { Campo, EstadoSecreto, ResultadoPrueba } from '../Campo'
import { CabeceraTarjeta } from '../CabeceraTarjeta'
import type { ConfigForm } from './useConfigForm'

export function TmdbCard({ form }: { form: ConfigForm }) {
  const { settings, newKey, setNewKey, region, setRegion } = form
  const [testingTmdb, setTestingTmdb] = useState(false)
  const [tmdbTestResult, setTmdbTestResult] = useState<IntegrationTestResult | null>(null)

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

  return (
    <div className="placeholder-card">
      <CabeceraTarjeta
        icono={<ServiceIcon type="tmdb" size={18} />}
        titulo="TMDb"
        lateral={<EstadoSecreto configurado={settings?.tmdb_api_key_configured} enmascarado={settings?.tmdb_api_key_masked} />}
      />
      <Campo
        etiqueta={settings?.tmdb_api_key_configured ? 'Nueva API key' : 'API key'}
        nota={settings?.tmdb_api_key_configured ? 'dejar vacío para mantener la actual' : undefined}
        ayuda="Usada para marcar proveedores disponibles en TMDb y para traducir los títulos de las series al español (eMuwarez exige el título siempre en español)."
      >
        {c => (
          <input
            {...c}
            type="password"
            className="form-input"
            value={newKey}
            onChange={e => setNewKey(e.target.value)}
            placeholder="API key de TMDb"
            autoComplete="new-password"
          />
        )}
      </Campo>
      <div className="aj-acciones">
        <button
          className="btn btn-secondary btn-sm"
          onClick={handleTestTmdb}
          disabled={testingTmdb}
          type="button"
        >
          {testingTmdb ? 'Probando…' : 'Probar conexión'}
        </button>
        <ResultadoPrueba resultado={tmdbTestResult} />
      </div>
      <Campo etiqueta="Región" ayuda="País para filtrar proveedores.">
        {c => (
          <select {...c} className="form-input form-select" value={region} onChange={e => setRegion(e.target.value)}>
            {REGION_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label} ({o.value})</option>)}
          </select>
        )}
      </Campo>
    </div>
  )
}
