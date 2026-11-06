import { useState, useEffect, useCallback, useId, useSyncExternalStore } from 'react'
import {
  getScheduledTasks, updateScheduledTaskSchedule, updateScheduledTaskOptions, runScheduledTaskNow, getScheduledTaskLogs,
  type ScheduledTask, type TaskOption, type TaskRunLogEntry,
} from '../api/scheduledTasks'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { formatDate } from '../utils/format'
import { useRefrescoPorAvisos } from '../hooks/useRefrescoPorAvisos'
import { IconoAviso } from '../components/Iconos'
import { Modal } from '../components/Modal'
import {
  tonoDeEstado, etiquetaDeEstado, cuentaAtras, duracion, etiquetaIntervalo, type TonoTarea,
} from '../utils/tareas'

const INTERVAL_OPTIONS_MINUTES = [15, 30, 45, 60, 90, 120, 180, 360, 720, 1440]
const HORA_POR_DEFECTO = '04:00'

// Un solo reloj para todas las cuentas atrás de la pantalla: cada segundo repinta solo ellas, no las tarjetas.
const suscriptores = new Set<() => void>()
let ahoraCompartido = Date.now()
let temporizador: number | undefined

function suscribirReloj(aviso: () => void) {
  suscriptores.add(aviso)
  if (suscriptores.size === 1) {
    ahoraCompartido = Date.now()
    temporizador = window.setInterval(() => {
      ahoraCompartido = Date.now()
      suscriptores.forEach(f => f())
    }, 1000)
  }
  return () => {
    suscriptores.delete(aviso)
    if (suscriptores.size === 0) window.clearInterval(temporizador)
  }
}

function CuentaAtras({ objetivo }: { objetivo: string | null }) {
  const ahora = useSyncExternalStore(suscribirReloj, () => ahoraCompartido)
  return <time dateTime={objetivo ?? undefined}>{cuentaAtras(objetivo, ahora)}</time>
}

// El estado de una ejecución: punto, texto y color por tono; el texto lleva el significado, no solo el color.
function EstadoTarea({ estado, desactivada = false }: { estado: string | null; desactivada?: boolean }) {
  const tono: TonoTarea = desactivada ? 'neutro' : tonoDeEstado(estado)
  return (
    <span className={`tareas-estado tareas-estado--${tono}`}>
      <span className="tareas-estado__punto" aria-hidden />
      {desactivada ? 'Desactivada' : etiquetaDeEstado(estado)}
    </span>
  )
}

function LogsModal({ taskKey, taskName, onClose }: { taskKey: string; taskName: string; onClose: () => void }) {
  const [logs, setLogs] = useState<TaskRunLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await getScheduledTaskLogs(taskKey, 30)
      setLogs(r.logs)
    } catch (e: unknown) {
      setError(e instanceof Error && e.message ? e.message : 'No se pudo leer el historial')
    } finally { setLoading(false) }
  }, [taskKey])

  useEffect(() => { load() }, [load])

  return (
    <Modal titulo={<>Logs: {taskName}</>} onClose={onClose} className="tareas-modal-logs">
      <div className="modal-body tareas-logs-cuerpo">
        {loading && logs.length === 0 ? <p className="tareas-logs-aviso">Cargando…</p> : error ? (
          <p className="tareas-logs-aviso tareas-error-linea" role="alert"><IconoAviso />{error}</p>
        ) : logs.length === 0 ? (
          <p className="tareas-logs-aviso">Sin ejecuciones registradas todavía.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Estado</th><th>Iniciada</th><th>Duración</th><th>Resumen</th></tr>
            </thead>
            <tbody>
              {logs.map(log => (
                <tr key={log.id}>
                  <td><EstadoTarea estado={log.status} /></td>
                  <td className="tareas-log-fecha">{formatDate(log.started_at)}</td>
                  <td className="tareas-log-fecha">{duracion(log.started_at, log.finished_at)}</td>
                  <td className="tareas-log-resumen">
                    {log.status === 'failed' && log.summary
                      ? <span className="tareas-error-linea"><IconoAviso />{log.summary}</span>
                      : (log.summary ?? '—')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="detail-panel__actions tareas-logs-acciones">
        <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>Actualizar</button>
        <button className="btn btn-secondary tareas-a-la-derecha" onClick={onClose}>Cerrar</button>
      </div>
    </Modal>
  )
}

// Un ajuste numérico de la tarea (días que se conserva algo, copias que se guardan…). Se guarda al salir del campo.
function OpcionDeTarea({ taskKey, opcion, onChanged }: {
  taskKey: string; opcion: TaskOption; onChanged: () => void
}) {
  const id = useId()
  const [texto, setTexto] = useState(String(opcion.valor))
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { setTexto(String(opcion.valor)) }, [opcion.valor])

  async function enviar(n: number) {
    setError(null)
    try {
      await updateScheduledTaskOptions(taskKey, { [opcion.clave]: n })
      onChanged()
    } catch (e: unknown) {
      setTexto(String(opcion.valor))
      setError(e instanceof Error && e.message ? e.message : 'Error al guardar la opción')
    }
  }

  async function guardar() {
    const n = Number(texto)
    if (texto === '' || n === opcion.valor) { setTexto(String(opcion.valor)); setError(null); return }
    if (!Number.isInteger(n) || n < opcion.minimo || n > opcion.maximo) {
      setTexto(String(opcion.valor))
      setError(`Tiene que ser un número entero entre ${opcion.minimo} y ${opcion.maximo}.`)
      return
    }
    await enviar(n)
  }

  if (opcion.minimo === 0 && opcion.maximo === 1) {
    return (
      <div className="form-group tareas-sin-margen tareas-ancho-total">
        <label className="checkbox-label tareas-check">
          <input type="checkbox" checked={opcion.valor === 1} onChange={e => enviar(e.target.checked ? 1 : 0)} /> {opcion.etiqueta}
        </label>
        {opcion.nota && <span className="form-hint">{opcion.nota}</span>}
        {error && <span className="form-error" role="alert">{error}</span>}
      </div>
    )
  }

  return (
    <div className="form-group tareas-sin-margen">
      <label className="form-label" htmlFor={id}>{opcion.etiqueta}</label>
      <input
        id={id}
        className="form-input"
        type="number"
        inputMode="numeric"
        autoComplete="off"
        min={opcion.minimo}
        max={opcion.maximo}
        value={texto}
        onChange={e => setTexto(e.target.value)}
        onBlur={guardar}
        onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur() }}
        aria-invalid={error ? true : undefined}
        aria-describedby={`${id}-ayuda`}
      />
      <span id={`${id}-ayuda`} className={error ? 'form-error' : 'form-hint'} role={error ? 'alert' : undefined}>
        {error ?? `De ${opcion.minimo} a ${opcion.maximo}`}
      </span>
      {opcion.nota && <span className="form-hint">{opcion.nota}</span>}
    </div>
  )
}

function TaskCard({ task, onChanged }: { task: ScheduledTask; onChanged: () => void }) {
  const base = useId()
  const [interval, setIntervalValue] = useState(task.interval_minutes)
  const [horaFija, setHoraFija] = useState(task.run_at !== null)
  const [hora, setHora] = useState(task.run_at ?? HORA_POR_DEFECTO)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [logsOpen, setLogsOpen] = useState(false)

  useEffect(() => { setIntervalValue(task.interval_minutes) }, [task.interval_minutes])
  useEffect(() => {
    setHoraFija(task.run_at !== null)
    if (task.run_at !== null) setHora(task.run_at)
  }, [task.run_at])

  async function guardarHorario(horario: { interval_minutes: number } | { run_at: string }) {
    setSaving(true)
    setMsg(null)
    try {
      await updateScheduledTaskSchedule(task.task_key, horario)
      onChanged()
    } catch (e: unknown) {
      // El servidor no aceptó el cambio: lo mostrado vuelve a lo guardado.
      setIntervalValue(task.interval_minutes)
      setHoraFija(task.run_at !== null)
      setHora(task.run_at ?? HORA_POR_DEFECTO)
      setMsg({ ok: false, text: e instanceof Error && e.message ? e.message : 'Error al guardar el horario' })
    } finally {
      setSaving(false)
    }
  }

  function handleIntervalChange(minutes: number) {
    setIntervalValue(minutes)
    guardarHorario({ interval_minutes: minutes })
  }

  function handleModoChange(aHoraFija: boolean) {
    setHoraFija(aHoraFija)
    guardarHorario(aHoraFija ? { run_at: hora } : { interval_minutes: interval })
  }

  // Se guarda al salir del campo, no a cada cambio: dos PUT seguidos podían llegar en orden inverso.
  function handleHoraBlur() {
    if (hora && hora !== task.run_at) guardarHorario({ run_at: hora })
  }

  async function handleRunNow() {
    setRunning(true)
    setMsg(null)
    try {
      const r = await runScheduledTaskNow(task.task_key)
      setMsg({ ok: r.status !== 'failed', text: r.summary })
      onChanged()
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error && e.message ? e.message : 'Error al ejecutar la tarea' })
    } finally {
      setRunning(false)
    }
  }

  const options = INTERVAL_OPTIONS_MINUTES.filter(m => m >= task.min_interval_minutes)
  const tono = task.enabled ? tonoDeEstado(task.last_status) : 'neutro'
  const idTitulo = `${base}-titulo`

  return (
    <article className={`placeholder-card tareas-tarjeta tareas-tarjeta--${tono}`} aria-labelledby={idTitulo}>
      {logsOpen && <LogsModal taskKey={task.task_key} taskName={task.name} onClose={() => setLogsOpen(false)} />}
      <header className="tareas-cabecera">
        <div className="tareas-cabecera__texto">
          <h3 className="tareas-titulo" id={idTitulo}>{task.name}</h3>
          <p className="tareas-descripcion">{task.description}</p>
        </div>
        <EstadoTarea estado={task.last_status} desactivada={!task.enabled} />
      </header>

      <dl className="tareas-datos">
        <div>
          <dt>Última ejecución</dt>
          <dd>{formatDate(task.last_run_at)}</dd>
        </div>
        <div>
          <dt>Próxima ejecución</dt>
          <dd>{task.enabled ? <CuentaAtras objetivo={task.next_run_at} /> : 'Desactivada'}</dd>
        </div>
      </dl>

      {task.last_summary && (
        task.last_status === 'failed'
          ? <p className="tareas-resumen tareas-resumen--error" role="status"><IconoAviso />{task.last_summary}</p>
          : <p className="tareas-resumen">{task.last_summary}</p>
      )}

      <div className="tareas-rejilla-160">
        <div className="form-group tareas-sin-margen">
          <label className="form-label" htmlFor={`${base}-modo`}>Cuándo</label>
          <select
            id={`${base}-modo`}
            className="form-input form-select"
            value={horaFija ? 'hora' : 'intervalo'}
            onChange={e => handleModoChange(e.target.value === 'hora')}
            disabled={saving}
          >
            <option value="intervalo">Cada cierto tiempo</option>
            <option value="hora">A una hora fija</option>
          </select>
        </div>

        {horaFija ? (
          <div className="form-group tareas-sin-margen">
            <label className="form-label" htmlFor={`${base}-hora`}>Hora</label>
            <input
              id={`${base}-hora`}
              className="form-input"
              type="time"
              autoComplete="off"
              value={hora}
              onChange={e => setHora(e.target.value)}
              onBlur={handleHoraBlur}
            />
            <span className="form-hint">Cada día, hora de {task.timezone}</span>
          </div>
        ) : (
          <div className="form-group tareas-sin-margen">
            <label className="form-label" htmlFor={`${base}-intervalo`}>Intervalo</label>
            <select
              id={`${base}-intervalo`}
              className="form-input form-select"
              value={interval}
              onChange={e => handleIntervalChange(Number(e.target.value))}
              disabled={saving}
            >
              {options.map(m => (
                <option key={m} value={m}>{etiquetaIntervalo(m)}</option>
              ))}
            </select>
            <span className="form-hint">Mínimo: {etiquetaIntervalo(task.min_interval_minutes)}</span>
          </div>
        )}
      </div>

      {task.opciones.length > 0 && (
        <div className="tareas-rejilla-200">
          {task.opciones.map(o => (
            <OpcionDeTarea key={o.clave} taskKey={task.task_key} opcion={o} onChanged={onChanged} />
          ))}
        </div>
      )}

      {msg && msg.text !== task.last_summary && (
        <p className={`tareas-mensaje tareas-mensaje--${msg.ok ? 'ok' : 'error'}`} role={msg.ok ? 'status' : 'alert'}>{msg.text}</p>
      )}

      <div className="tareas-acciones">
        {task.manual_allowed ? (
          <button className="btn btn-secondary btn-sm" onClick={handleRunNow} disabled={running}>
            {running ? 'Ejecutando…' : 'Ejecutar ahora'}
          </button>
        ) : (
          <span className="tareas-sin-manual">
            Sin refresco manual (para no saturar el servicio). Próxima automática: <CuentaAtras objetivo={task.next_run_at} />
          </span>
        )}
        <button className="btn btn-secondary btn-sm" onClick={() => setLogsOpen(true)}>Ver logs</button>
      </div>
    </article>
  )
}

// Cuántas tareas hay en cada estado que merezca una línea arriba: lo que falló y lo que corre ahora.
function ResumenTareas({ tasks }: { tasks: ScheduledTask[] }) {
  const activas = tasks.filter(t => t.enabled)
  const falladas = activas.filter(t => t.last_status === 'failed').length
  const enCurso = activas.filter(t => t.last_status === 'running').length
  if (falladas === 0 && enCurso === 0) return null
  return (
    <p className="tareas-resumen-pagina" role="status">
      {enCurso > 0 && <span className="tareas-estado tareas-estado--curso"><span className="tareas-estado__punto" aria-hidden />{enCurso === 1 ? '1 en curso' : `${enCurso} en curso`}</span>}
      {falladas > 0 && <span className="tareas-estado tareas-estado--error"><span className="tareas-estado__punto" aria-hidden />{falladas === 1 ? '1 con error' : `${falladas} con error`}</span>}
    </p>
  )
}

export function TasksPage() {
  const [tasks, setTasks] = useState<ScheduledTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setTasks(await getScheduledTasks())
    } catch {
      setError('Error al cargar las tareas automáticas')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // "Últimas tareas ejecutadas" se actualiza en cuanto termina una, en vez de
  // hasta 30 segundos después. El sondeo se espacia a dos minutos de red de
  // seguridad mientras el canal esté vivo.
  useRefrescoPorAvisos(['tarea-terminada'], load, {
    cadaSinCanal: 30_000,
    cadaConCanal: 120_000,
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Tareas</h1>
          <div className="page-subtitle">Tareas automáticas de sincronización</div>
        </div>
        {!loading && !error && <ResumenTareas tasks={tasks} />}
      </div>

      {loading ? <LoadingState label="Cargando tareas…" /> : error ? <ErrorState message={error} onRetry={load} /> : (
        tasks.length === 0 ? (
          <EmptyState title="Sin tareas programadas" body="Las tareas aparecen aquí cuando el servidor las registra al arrancar." />
        ) : <div data-tour="tasks-content" className="tareas-lista">
          {tasks.map(task => (
            <TaskCard key={task.task_key} task={task} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  )
}
