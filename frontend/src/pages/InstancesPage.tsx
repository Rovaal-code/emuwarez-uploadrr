import { useState, useEffect, useCallback } from 'react'
import { getInstances, addInstance, testInstance, syncInstance } from '../api/instances'
import { refreshArrHealth } from '../api/diagnostics'
import type { InstanceSafeResponse } from '../types/api'
import { ServiceIcon, ServiceLabel } from '../components/ServiceIcon'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { ApiClientError } from '../api/client'
import { formatDate } from '../utils/format'

interface AddForm {
  type: 'radarr' | 'sonarr'
  name: string
  url: string
  api_key: string
  is_4k: boolean
  is_anime: boolean
}

function defaultForm(): AddForm {
  return { type: 'radarr', name: '', url: '', api_key: '', is_4k: false, is_anime: false }
}

export function InstancesPage() {
  const [instances, setInstances] = useState<InstanceSafeResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState<AddForm>(defaultForm())
  const [addError, setAddError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [testResults, setTestResults] = useState<Record<number, string>>({})
  const [testingId, setTestingId] = useState<number | null>(null)
  const [syncingId, setSyncingId] = useState<number | null>(null)
  const [syncResults, setSyncResults] = useState<Record<number, string>>({})
  const [healthMsg, setHealthMsg] = useState<string | null>(null)
  const [healthLoading, setHealthLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setInstances(await getInstances())
    } catch {
      setError('Error al cargar las instancias')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    setAddError(null)
    if (!form.name.trim() || !form.url.trim() || !form.api_key.trim()) {
      setAddError('Nombre, URL y API key son obligatorios')
      return
    }
    setAdding(true)
    try {
      await addInstance({ type: form.type, name: form.name.trim(), url: form.url.trim(), api_key: form.api_key.trim(), is_4k: form.is_4k, is_anime: form.is_anime })
      setForm(defaultForm())
      setShowAdd(false)
      await load()
    } catch (err) {
      setAddError(err instanceof ApiClientError ? err.message : 'Error al añadir instancia')
    } finally {
      setAdding(false)
    }
  }

  async function handleTest(id: number) {
    setTestingId(id)
    setTestResults(p => ({ ...p, [id]: 'Probando…' }))
    try {
      const res = await testInstance(id)
      setTestResults(p => ({
        ...p,
        [id]: res.ok ? `✓ OK — v${res.version ?? '?'}` : `✗ Error: ${res.error ?? 'desconocido'}`,
      }))
    } catch {
      setTestResults(p => ({ ...p, [id]: '✗ Error de conexión' }))
    } finally {
      setTestingId(null)
    }
  }

  async function handleSync(id: number) {
    setSyncingId(id)
    setSyncResults(p => ({ ...p, [id]: 'Sincronizando…' }))
    try {
      const res = await syncInstance(id)
      setSyncResults(p => ({ ...p, [id]: `↻ ${res.imported} elementos · ${res.missing} faltantes` }))
    } catch {
      setSyncResults(p => ({ ...p, [id]: '✗ Error de sincronización' }))
    } finally {
      setSyncingId(null)
    }
  }

  async function handleRefreshHealth() {
    setHealthLoading(true)
    setHealthMsg(null)
    try {
      const r = await refreshArrHealth({ include_queue: true, include_history: false })
      const s = r.health?.summary
      setHealthMsg(s ? `Salud: OK=${s.ok} Aviso=${s.warning} Error=${s.error}` : 'Salud actualizada')
    } catch {
      setHealthMsg('Error al refrescar salud ARR')
    } finally {
      setHealthLoading(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Instancias</div>
          <div className="page-subtitle">Gestiona tus instancias Radarr y Sonarr</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className="btn btn-secondary btn-sm" onClick={handleRefreshHealth} disabled={healthLoading}>
            {healthLoading ? 'Actualizando…' : 'Refrescar salud ARR'}
          </button>
          {healthMsg && <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{healthMsg}</span>}
          <button className="btn btn-primary btn-sm" onClick={() => setShowAdd(!showAdd)}>
            {showAdd ? 'Cancelar' : '+ Añadir instancia'}
          </button>
        </div>
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div style={{ fontWeight: 600, marginBottom: 14 }}>Nueva instancia</div>
          <form onSubmit={handleAdd}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 12 }}>
              <div className="form-group">
                <label className="form-label">Tipo</label>
                <select className="form-input form-select" value={form.type} onChange={e => setForm(p => ({ ...p, type: e.target.value as 'radarr' | 'sonarr' }))}>
                  <option value="radarr">Radarr</option>
                  <option value="sonarr">Sonarr</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Nombre</label>
                <input className="form-input" placeholder="Radarr principal" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label className="form-label">URL</label>
                <input className="form-input" placeholder="http://192.168.1.100:7878" value={form.url} onChange={e => setForm(p => ({ ...p, url: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label className="form-label">API key</label>
                <input className="form-input" type="password" placeholder="API key" value={form.api_key} onChange={e => setForm(p => ({ ...p, api_key: e.target.value }))} required />
              </div>
            </div>
            <div style={{ display: 'flex', gap: 16, marginBottom: 14 }}>
              <label className="checkbox-label"><input type="checkbox" checked={form.is_4k} onChange={e => setForm(p => ({ ...p, is_4k: e.target.checked }))} /> 4K</label>
              <label className="checkbox-label"><input type="checkbox" checked={form.is_anime} onChange={e => setForm(p => ({ ...p, is_anime: e.target.checked }))} /> Anime</label>
            </div>
            {addError && <div className="alert alert-error" style={{ marginBottom: 12 }}>{addError}</div>}
            <button type="submit" className="btn btn-primary btn-sm" disabled={adding}>
              {adding ? 'Añadiendo…' : 'Añadir'}
            </button>
          </form>
        </div>
      )}

      {/* List */}
      {loading ? (
        <LoadingState label="Cargando instancias…" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : instances.length === 0 ? (
        <EmptyState
          icon="🔌"
          title="Sin instancias configuradas"
          body="Añade una instancia Radarr o Sonarr para empezar a sincronizar tu biblioteca."
          action={<button className="btn btn-primary btn-sm" onClick={() => setShowAdd(true)}>+ Añadir instancia</button>}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {instances.map(inst => (
            <div key={inst.id} className="instance-card">
              <div className="instance-card-info">
                <ServiceIcon type={inst.type as 'radarr' | 'sonarr'} size={28} />
                <div className="instance-card-meta">
                  <div className="instance-card-name">
                    <ServiceLabel type={inst.type} label={inst.name} size={14} />
                    {inst.is_4k && <span className="badge status-queued" style={{ fontSize: 10, padding: '1px 6px' }}>4K</span>}
                    {inst.is_anime && <span className="badge status-uploading" style={{ fontSize: 10, padding: '1px 6px' }}>Anime</span>}
                    {!inst.enabled && <span className="badge status-unknown" style={{ fontSize: 10, padding: '1px 6px' }}>Desactivada</span>}
                  </div>
                  <div className="instance-card-url">{inst.url}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                    API key: {inst.api_key_masked} · Añadida: {formatDate(inst.created_at)}
                    {inst.last_test_status && ` · Último test: ${inst.last_test_status}`}
                  </div>
                  {(testResults[inst.id] || syncResults[inst.id]) && (
                    <div style={{ fontSize: 12, marginTop: 4, color: 'var(--text-secondary)' }}>
                      {testResults[inst.id] && <span style={{ marginRight: 12 }}>{testResults[inst.id]}</span>}
                      {syncResults[inst.id] && <span>{syncResults[inst.id]}</span>}
                    </div>
                  )}
                </div>
              </div>
              <div className="instance-card-actions">
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={testingId === inst.id}
                  onClick={() => handleTest(inst.id)}
                >
                  {testingId === inst.id ? 'Probando…' : 'Probar conexión'}
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={syncingId === inst.id}
                  onClick={() => handleSync(inst.id)}
                >
                  {syncingId === inst.id ? 'Sincronizando…' : '↻ Sincronizar'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
