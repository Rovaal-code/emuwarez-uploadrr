import { useState } from 'react'
import { testTmdbConnection, type IntegrationTestResult } from '../../../api/integrationTests'
import { ServiceIcon } from '../../../components/ServiceIcon'
import { CheckStatusIcon } from '../../../components/DetailCard'
import { REGION_OPTIONS } from '../../../constants/regionLanguage'
import { testResultLabel, testResultColor } from '../../../utils/integrationResult'
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
      <h3 className="aj-card-titulo aj-mb-14">
        <ServiceIcon type="tmdb" size={18} /> TMDb
      </h3>
      <div className="form-group aj-mb-12">
        <label className="form-label">Estado de la API key</label>
        <div className="aj-fs-13">
          {settings?.tmdb_api_key_configured
            ? <><span className="aj-ok"><CheckStatusIcon status="ok" /> Configurada</span>{settings.tmdb_api_key_masked && <code className="aj-code-mascara">{settings.tmdb_api_key_masked}</code>}</>
            : <span className="aj-err">✗ No configurada</span>}
        </div>
      </div>
      <div className="form-group aj-mb-12">
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
      <div className="aj-mb-12">
        <button
          className="btn btn-secondary btn-sm"
          onClick={handleTestTmdb}
          disabled={testingTmdb}
          type="button"
        >
          {testingTmdb ? 'Probando…' : 'Probar conexión'}
        </button>
        {tmdbTestResult && (
          <span className="aj-res-12" style={{ color: testResultColor(tmdbTestResult) }}>
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
  )
}
