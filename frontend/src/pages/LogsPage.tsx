import { useState, useEffect, useCallback, useRef } from 'react'
import { getLogs, type LogEntry } from '../api/logs'
import { EmptyState } from '../components/EmptyState'
import { useSeccionVisible } from '../context/SeccionVisible'
import { IconoDocumento } from '../components/Iconos'

const LEVELS = ['', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
const LEVEL_COLOR: Record<string, string> = {
  DEBUG: 'var(--color-neutral)', INFO: 'var(--color-accent-soft)', WARNING: 'var(--color-warning)', ERROR: 'var(--color-error)', CRITICAL: 'var(--hud-danger)',
}

export function LogsPage() {
  const [items, setItems] = useState<LogEntry[]>([])
  const [level, setLevel] = useState('')
  const [search, setSearch] = useState('')
  const [auto, setAuto] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const searchRef = useRef(search)
  searchRef.current = search

  const load = useCallback(async () => {
    try {
      const r = await getLogs({ limit: 1000, level: level || undefined, search: searchRef.current || undefined })
      setItems(r.items)
      setError(null)
    } catch {
      setError('No se pudieron cargar los logs')
    } finally {
      setLoading(false)
    }
  }, [level])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 3s while enabled.
  // El auto-refresco viene encendido, y la sección se queda montada al cambiar
  // de pestaña: sin la condición de que se vea, montarla una vez dejaba una
  // petición cada 3 segundos para siempre, mirara nadie o no.
  const logsALaVista = useSeccionVisible()
  useEffect(() => {
    if (!auto || !logsALaVista) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [auto, load, logsALaVista])

  return (
    <div data-tour="logs-content" style={{ height: '100%' }}>
      <div className="page-header">
        <div>
          <div className="page-title">Logs</div>
          <div className="page-subtitle">Todo lo que hace la aplicación (peticiones HTTP, sincronizaciones, subidas, errores…)</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          className="form-input"
          placeholder="Buscar en los logs…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && load()}
          style={{ minWidth: 240 }}
        />
        <select className="form-input form-select" value={level} onChange={e => setLevel(e.target.value)} style={{ width: 150 }}>
          {LEVELS.map(l => <option key={l} value={l}>{l ? `Nivel: ${l}+` : 'Nivel: Todos'}</option>)}
        </select>
        <button className="btn btn-secondary btn-sm" onClick={load}>↻ Refrescar</button>
        <label className="checkbox-label" style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          <input type="checkbox" checked={auto} onChange={e => setAuto(e.target.checked)} /> Auto (3s)
        </label>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>{items.length} líneas</span>
      </div>

      <div className="activity-section" style={{ padding: 0 }}>
        {loading ? (
          <div style={{ padding: 20, color: 'var(--text-muted)' }}>Cargando…</div>
        ) : error ? (
          <div style={{ padding: 20, color: 'var(--color-missing)' }}>{error}</div>
        ) : items.length === 0 ? (
          <EmptyState icon={<IconoDocumento />} title="Sin logs" body="No hay entradas que coincidan con el filtro." />
        ) : (
          <div style={{ maxHeight: 'calc(var(--vh100) * 0.7)', overflow: 'auto', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            {items.map((e, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, padding: '3px 12px', borderBottom: '1px solid var(--border)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{e.time}</span>
                <span style={{ color: LEVEL_COLOR[e.level] ?? 'var(--text-secondary)', fontWeight: 700, flexShrink: 0, width: 64 }}>{e.level}</span>
                <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{e.logger}</span>
                <span>{e.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
