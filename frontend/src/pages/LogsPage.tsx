import { memo, useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { getLogs, type LogEntry } from '../api/logs'
import { EmptyState } from '../components/EmptyState'
import { useSeccionVisible } from '../context/SeccionVisible'
import { IconoDocumento } from '../components/Iconos'
import {
  clavesDeLineas, reutilizarLineas, textoDeLinea, trocearPorBusqueda, diaDeLinea, horaDeLinea,
} from '../utils/logs'

const LEVELS = ['', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
const NIVEL_CLASE: Record<string, string> = {
  DEBUG: 'debug', INFO: 'info', WARNING: 'warning', ERROR: 'error', CRITICAL: 'critical',
}
// Cuánto dura el «Copiado» antes de volver a «Copiar».
const AVISO_COPIADO_MS = 1800

// Una línea del registro. Memoizada: con mil líneas, repintarlas todas cada 3 segundos para dejarlas igual era lo que
// más costaba de esta pantalla. Con la línea abierta el mensaje se parte en varias líneas; cerrada, se recorta.
// Solo una línea (`enfocable`) está en el orden del tabulador: con mil líneas y su botón de copiar eran dos mil paradas
// antes de salir de la lista. Dentro, las flechas mueven el foco y la tecla C copia la línea.
const Linea = memo(function Linea({ linea, id, abierta, enfocable, busqueda, onAlternar, onCopiar, onEnfocar }: {
  linea: LogEntry
  id: string
  abierta: boolean
  enfocable: boolean
  busqueda: string
  onAlternar: (id: string) => void
  onCopiar: (linea: LogEntry) => void
  onEnfocar: (id: string) => void
}) {
  const nivel = NIVEL_CLASE[linea.level] ?? 'otro'
  return (
    <div className={`lg-linea lg-linea--${nivel}${abierta ? ' lg-linea--abierta' : ''}`}>
      <button
        type="button"
        className="lg-linea__cuerpo"
        data-linea={id}
        tabIndex={enfocable ? 0 : -1}
        aria-expanded={abierta}
        aria-keyshortcuts="C"
        onClick={() => onAlternar(id)}
        onFocus={() => onEnfocar(id)}
        title={abierta ? 'Recoger la línea' : 'Ver la línea entera'}
      >
        <span className="lg-hora" title={linea.time}>{horaDeLinea(linea)}</span>
        <span className="lg-nivel">{linea.level}</span>
        <span className="lg-origen" title={linea.logger}>{linea.logger}</span>
        <span className="lg-mensaje">
          {trocearPorBusqueda(linea.message, busqueda).map((t, i) =>
            t.coincide ? <mark key={i} className="lg-coincidencia">{t.texto}</mark> : t.texto)}
        </span>
      </button>
      <button type="button" className="lg-copiar" tabIndex={-1} onClick={() => onCopiar(linea)} aria-label={`Copiar la línea de las ${horaDeLinea(linea)}`} title="Copiar la línea">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
          <rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h9" />
        </svg>
      </button>
    </div>
  )
})

export function LogsPage() {
  const [items, setItems] = useState<LogEntry[]>([])
  const listaRef = useRef<HTMLDivElement>(null)
  // Si el foco estaba en una línea de la lista justo antes de aplicar un refresco (lo mira `load`).
  const focoEnLista = useRef(false)
  const [level, setLevel] = useState('')
  const [search, setSearch] = useState('')
  // Lo buscado que ya se pidió al servidor: es lo que se resalta, para no repintar las líneas con cada tecla.
  const [buscado, setBuscado] = useState('')
  const [auto, setAuto] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [abiertas, setAbiertas] = useState<ReadonlySet<string>>(new Set())
  const [todasAbiertas, setTodasAbiertas] = useState(false)
  const [copiado, setCopiado] = useState<string | null>(null)
  // La línea que entra en el orden del tabulador (la última enfocada; al principio, la primera).
  const [activa, setActiva] = useState<string | null>(null)
  const searchRef = useRef(search)
  searchRef.current = search
  // Hay una carga sin acabar: el refresco automático no lanza otra encima (con búsqueda son 1000 líneas con LIKE).
  const enCurso = useRef(false)
  const avisoCopiado = useRef<number | null>(null)

  // Solo cuenta la última petición: cambiar el nivel con una en vuelo no deja las líneas del nivel anterior.
  const ultimaCarga = useRef(0)
  const load = useCallback(async () => {
    const esta = ++ultimaCarga.current
    enCurso.current = true
    try {
      const r = await getLogs({ limit: 1000, level: level || undefined, search: searchRef.current.trim() || undefined })
      if (esta !== ultimaCarga.current) return
      // Si no ha entrado nada, se deja la lista como está: no se repintan mil filas para nada. Si ha entrado algo, las
      // que ya estaban conservan su objeto y solo se pintan las nuevas.
      focoEnLista.current = !!listaRef.current?.contains(document.activeElement)
      setItems(previas => reutilizarLineas(previas, r.items))
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

  // Buscar al dejar de teclear, sin esperar al siguiente refresco ni a pulsar Intro.
  const primeraBusqueda = useRef(true)
  useEffect(() => {
    if (primeraBusqueda.current) { primeraBusqueda.current = false; return }
    const t = window.setTimeout(() => { setBuscado(search); void load() }, 350)
    return () => window.clearTimeout(t)
  }, [search, load])

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

  useEffect(() => () => { if (avisoCopiado.current) window.clearTimeout(avisoCopiado.current) }, [])

  const claves = useMemo(() => clavesDeLineas(items), [items])

  const alternar = useCallback((id: string) => {
    setAbiertas(prev => {
      const sig = new Set(prev)
      if (sig.has(id)) sig.delete(id)
      else sig.add(id)
      return sig
    })
  }, [])

  const copiarTexto = useCallback(async (texto: string, que: string) => {
    try {
      await navigator.clipboard.writeText(texto)
      setCopiado(que)
    } catch {
      // El portapapeles solo existe en https o en localhost.
      setCopiado('error')
    }
    if (avisoCopiado.current) window.clearTimeout(avisoCopiado.current)
    avisoCopiado.current = window.setTimeout(() => setCopiado(null), AVISO_COPIADO_MS)
  }, [])

  // Estable entre repintados para no invalidar el memo de las líneas.
  const copiarLinea = useCallback((l: LogEntry) => { void copiarTexto(textoDeLinea(l), 'linea') }, [copiarTexto])

  const enfocable = activa !== null && claves.includes(activa) ? activa : claves[0]

  // Si un refresco se lleva la línea que tenía el foco (deja de estar entre las más recientes), el foco cae al body:
  // vuelve a la lista, a la línea que ahora entra con Tab. Solo si el foco estaba en la lista al refrescar.
  useEffect(() => {
    if (activa === null || claves.includes(activa) || !focoEnLista.current) return
    focoEnLista.current = false
    if (document.activeElement && document.activeElement !== document.body) return
    listaRef.current?.querySelector<HTMLButtonElement>('.lg-linea__cuerpo[tabindex="0"]')?.focus()
  }, [activa, claves])

  // Flechas, Inicio y Fin entre las líneas; C copia la enfocada.
  function alTeclearLista(e: React.KeyboardEvent<HTMLDivElement>) {
    const actual = (e.target as HTMLElement).closest<HTMLButtonElement>('.lg-linea__cuerpo')
    if (!actual || e.altKey || e.ctrlKey || e.metaKey) return
    if (e.key === 'c' || e.key === 'C') {
      const i = claves.indexOf(actual.dataset.linea ?? '')
      if (i >= 0) { e.preventDefault(); copiarLinea(items[i]) }
      return
    }
    const lineas = [...e.currentTarget.querySelectorAll<HTMLButtonElement>('.lg-linea__cuerpo')]
    const i = lineas.indexOf(actual)
    const destino = e.key === 'ArrowDown' ? i + 1 : e.key === 'ArrowUp' ? i - 1
      : e.key === 'Home' ? 0 : e.key === 'End' ? lineas.length - 1 : null
    if (destino === null || destino < 0 || destino >= lineas.length) return
    e.preventDefault()
    lineas[destino].focus()
  }

  const hayFiltros = level !== '' || search.trim() !== ''
  function quitarFiltros() { setLevel(''); setSearch(''); setBuscado('') }

  // Las líneas con una cabecera cuando cambia el día (la lista va de lo más nuevo a lo más viejo).
  const filas = useMemo(() => {
    const out: ({ tipo: 'dia'; dia: string } | { tipo: 'linea'; linea: LogEntry; id: string })[] = []
    let dia: string | null = null
    items.forEach((linea, i) => {
      const d = diaDeLinea(linea)
      if (d && d !== dia) { out.push({ tipo: 'dia', dia: d }); dia = d }
      out.push({ tipo: 'linea', linea, id: claves[i] })
    })
    return out
  }, [items, claves])

  return (
    <div data-tour="logs-content" className="lg-pagina">
      <div className="page-header lg-cabecera">
        <div>
          <h1 className="page-title">Logs</h1>
          <div className="page-subtitle">Todo lo que hace la aplicación (peticiones HTTP, sincronizaciones, subidas, errores…)</div>
        </div>
      </div>

      <div className="lg-barra" role="search">
        <div className="lg-buscar">
          <input
            type="search"
            className="form-input"
            placeholder="Buscar en los logs…"
            aria-label="Buscar en los logs"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { setBuscado(search); void load() } }}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <select className="form-input form-select lg-nivel-filtro" aria-label="Nivel mínimo" value={level} onChange={e => setLevel(e.target.value)}>
          {LEVELS.map(l => <option key={l} value={l}>{l ? `Nivel: ${l}+` : 'Nivel: Todos'}</option>)}
        </select>
        <button className="btn btn-secondary btn-sm" onClick={() => load()}>Refrescar</button>
        <label className="checkbox-label lg-auto">
          <input type="checkbox" checked={auto} onChange={e => setAuto(e.target.checked)} /> Auto (3s)
        </label>
        <label className="checkbox-label lg-auto">
          <input type="checkbox" checked={todasAbiertas} onChange={e => { setTodasAbiertas(e.target.checked); setAbiertas(new Set()) }} /> Líneas enteras
        </label>
        <div className="lg-barra__fin">
          <span className="lg-contador" role="status">
            {copiado === 'linea' ? 'Línea copiada' : items.length === 1 ? '1 línea' : `${items.length} líneas`}
          </span>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => copiarTexto(items.map(textoDeLinea).join('\n'), 'todas')}
            disabled={items.length === 0}
          >
            {copiado === 'todas' ? 'Copiado' : 'Copiar todo'}
          </button>
        </div>
      </div>
      {copiado === 'error' && (
        <p className="lg-aviso-copia" role="alert">No se pudo copiar: selecciona el texto y cópialo a mano.</p>
      )}

      <div className="activity-section lg-caja">
        {loading ? (
          <div className="lg-aviso">Cargando…</div>
        ) : error && items.length === 0 ? (
          <div className="lg-aviso lg-aviso--error" role="alert">
            {error}{' '}
            <button className="btn btn-secondary btn-sm" onClick={() => { setLoading(true); void load() }}>Reintentar</button>
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<IconoDocumento />}
            title={hayFiltros ? 'Ninguna línea coincide' : 'Sin logs'}
            body={hayFiltros ? 'Prueba con otra búsqueda o con un nivel más bajo.' : 'Todavía no hay entradas en el registro.'}
            action={hayFiltros ? <button className="btn btn-secondary btn-sm" onClick={quitarFiltros}>Quitar filtros</button> : undefined}
          />
        ) : (
          <div ref={listaRef} className="lg-lista" role="region" aria-label="Líneas del registro (flechas para moverse, C copia la línea)" onKeyDown={alTeclearLista}>
            {error && <div className="lg-aviso lg-aviso--error" role="alert">{error}: se enseña la última lectura.</div>}
            {filas.map(f => f.tipo === 'dia'
              ? <div key={`dia-${f.dia}`} className="lg-dia">{f.dia}</div>
              : <Linea
                  key={f.id}
                  id={f.id}
                  linea={f.linea}
                  abierta={todasAbiertas || abiertas.has(f.id)}
                  enfocable={f.id === enfocable}
                  busqueda={buscado}
                  onAlternar={alternar}
                  onCopiar={copiarLinea}
                  onEnfocar={setActiva}
                />)}
          </div>
        )}
      </div>
    </div>
  )
}
