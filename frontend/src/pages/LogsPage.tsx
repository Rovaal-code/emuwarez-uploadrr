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
  // Hay una carga sin acabar: el refresco automático no lanza otra encima (con búsqueda son 1000 líneas con LIKE).
  const enCurso = useRef(false)

  // Solo cuenta la última petición: cambiar el nivel con una en vuelo no deja las líneas del nivel anterior.
  const ultimaCarga = useRef(0)
  const load = useCallback(async () => {
    const esta = ++ultimaCarga.current
    enCurso.current = true
    try {
      const r = await getLogs({ limit: 1000, level: level || undefined, search: searchRef.current || undefined })
      if (esta !== ultimaCarga.current) return
      setItems(r.items)
      setError(null)
    } catch {
      if (esta === ultimaCarga.current) setError('No se pudieron cargar los logs')
    } finally {
      if (esta === ultimaCarga.current) {
        enCurso.current = false
        setLoading(false)
      }
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
    const t = setInterval(() => { if (!enCurso.current) load() }, 3000)
    return () => clearInterval(t)
  }, [auto, load, logsALaVista])

  return (
    <div data-tour="logs-content" className="logs-pagina">
      <div className="page-header">
        <div>
          <div className="page-title">Logs</div>
          <div className="page-subtitle">Todo lo que hace la aplicación (peticiones HTTP, sincronizaciones, subidas, errores…)</div>
        </div>
      </div>

      <div className="logs-barra">
        <input
          className="form-input logs-buscar"
          placeholder="Buscar en los logs…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && load()}
        />
        <select className="form-input form-select logs-nivel" value={level} onChange={e => setLevel(e.target.value)}>
          {LEVELS.map(l => <option key={l} value={l}>{l ? `Nivel: ${l}+` : 'Nivel: Todos'}</option>)}
        </select>
        <button className="btn btn-secondary btn-sm" onClick={load}>↻ Refrescar</button>
        <label className="checkbox-label logs-auto">
          <input type="checkbox" checked={auto} onChange={e => setAuto(e.target.checked)} /> Auto (3s)
        </label>
        <span className="logs-contador">{items.length} líneas</span>
      </div>

      <div className="activity-section logs-caja">
        {loading ? (
          <div className="logs-aviso">Cargando…</div>
        ) : error ? (
          <div className="logs-aviso logs-aviso-error">{error}</div>
        ) : items.length === 0 ? (
          <EmptyState icon={<IconoDocumento />} title="Sin logs" body="No hay entradas que coincidan con el filtro." />
        ) : (
          <div className="logs-lista">
            {items.map((e, i) => (
              <div key={i} className="logs-linea">
                <span className="logs-tiempo">{e.time}</span>
                {/* El color depende del nivel de cada línea: se queda en línea. */}
                <span className="logs-nivel-linea" style={{ color: LEVEL_COLOR[e.level] ?? 'var(--text-secondary)' }}>{e.level}</span>
                <span className="logs-tiempo">{e.logger}</span>
                <span>{e.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
