import { useState, useEffect, useCallback } from 'react'
import {
  getScheduledTasks, updateScheduledTaskSchedule, updateScheduledTaskOptions, runScheduledTaskNow, getScheduledTaskLogs,
  type ScheduledTask, type TaskOption, type TaskRunLogEntry,
} from '../api/scheduledTasks'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { formatDate } from '../utils/format'
import { useRefrescoPorAvisos } from '../hooks/useRefrescoPorAvisos'
import { IconoAviso } from '../components/Iconos'
import { Modal } from '../components/Modal'

const INTERVAL_OPTIONS_MINUTES = [15, 30, 45, 60, 90, 120, 180, 360, 720, 1440]
const HORA_POR_DEFECTO = '04:00'

const STATUS_COLOR: Record<string, string> = {
  completed: 'var(--color-available)',
  failed: 'var(--color-error)',
  skipped: 'var(--color-warning)',
  running: 'var(--text-accent)',
}

function statusColor(status: string | null): string {
  if (!status) return 'var(--color-neutral)'
  return STATUS_COLOR[status] ?? 'var(--color-neutral)'
}

const STATUS_LABEL: Record<string, string> = {
  completed: 'Completado',
  failed: 'Error',
  skipped: 'Omitido',
  running: 'Ejecutando',
  queued: 'En cola',
  pending: 'Pendiente',
}

function statusLabel(status: string | null): string {
  if (!status) return '—'
  return STATUS_LABEL[status] ?? (status.charAt(0).toUpperCase() + status.slice(1))
}

function formatCountdown(targetIso: string | null, now: number): string {
  if (!targetIso) return '—'
  const target = new Date(targetIso).getTime()
  const diffMs = target - now
  if (diffMs <= 0) return 'en breve'
  const totalMin = Math.floor(diffMs / 60000)
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  if (h > 0) return `en ${h}h ${m}m`
  const s = Math.floor((diffMs % 60000) / 1000)
  return m > 0 ? `en ${m}m ${s}s` : `en ${s}s`
}

function LogsModal({ taskKey, taskName, onClose }: { taskKey: string; taskName: string; onClose: () => void }) {
  const [logs, setLogs] = useState<TaskRunLogEntry[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await getScheduledTaskLogs(taskKey, 30)
      setLogs(r.logs)
    } catch { /* ignore */ } finally { setLoading(false) }
  }, [taskKey])

  useEffect(() => { load() }, [load])

  return (
    <Modal titulo={<>Logs: {taskName}</>} onClose={onClose} className="tareas-modal-logs">
      <div className="modal-body tareas-logs-cuerpo">
        {loading ? <p>Cargando…</p> : logs.length === 0 ? (
          <p className="text-muted">Sin ejecuciones registradas todavía.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Estado</th><th>Iniciada</th><th>Finalizada</th><th>Resumen</th></tr>
            </thead>
            <tbody>
              {logs.map(log => (
                <tr key={log.id}>
                  <td>
                    {/* Color calculado según el estado. */}
                    <span className="tareas-log-estado" style={{ color: statusColor(log.status) }}>{statusLabel(log.status)}</span>
                  </td>
                  <td className="tareas-log-fecha">{formatDate(log.started_at)}</td>
                  <td className="tareas-log-fecha">{formatDate(log.finished_at)}</td>
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
function OpcionDeTarea({ taskKey, opcion, onChanged, onMsg }: {
  taskKey: string; opcion: TaskOption; onChanged: () => void; onMsg: (m: string | null) => void
}) {
  const [texto, setTexto] = useState(String(opcion.valor))
  useEffect(() => { setTexto(String(opcion.valor)) }, [opcion.valor])

  async function enviar(n: number) {
    onMsg(null)
    try {
      await updateScheduledTaskOptions(taskKey, { [opcion.clave]: n })
      onChanged()
    } catch (e: unknown) {
      setTexto(String(opcion.valor))
      onMsg(`✗ ${e instanceof Error ? e.message : 'Error al guardar la opción'}`)
    }
  }

  async function guardar() {
    const n = Number(texto)
    if (texto === '' || n === opcion.valor) { setTexto(String(opcion.valor)); return }
    if (!Number.isInteger(n) || n < opcion.minimo || n > opcion.maximo) {
      setTexto(String(opcion.valor))
      onMsg(`✗ ${opcion.etiqueta}: tiene que estar entre ${opcion.minimo} y ${opcion.maximo}`)
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
      </div>
    )
  }

  return (
    <div className="form-group tareas-sin-margen">
      <label className="form-label">{opcion.etiqueta}</label>
      <input
        className="form-input"
        type="number"
        min={opcion.minimo}
        max={opcion.maximo}
        value={texto}
        onChange={e => setTexto(e.target.value)}
        onBlur={guardar}
      />
      <span className="form-hint">De {opcion.minimo} a {opcion.maximo}</span>
    </div>
  )
}

function TaskCard({ task, onChanged }: { task: ScheduledTask; onChanged: () => void }) {
  const [interval, setIntervalValue] = useState(task.interval_minutes)
  const [horaFija, setHoraFija] = useState(task.run_at !== null)
  const [hora, setHora] = useState(task.run_at ?? HORA_POR_DEFECTO)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [logsOpen, setLogsOpen] = useState(false)
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

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
      setMsg(`✗ ${e instanceof Error ? e.message : 'Error al guardar el horario'}`)
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
      setMsg(`${r.status === 'failed' ? '✗' : '✓'} ${r.summary}`)
      onChanged()
    } catch (e: unknown) {
      setMsg(`✗ ${e instanceof Error ? e.message : 'Error al ejecutar la tarea'}`)
    } finally {
      setRunning(false)
    }
  }

  const options = INTERVAL_OPTIONS_MINUTES.filter(m => m >= task.min_interval_minutes)

  return (
    <div className="placeholder-card">
      {logsOpen && <LogsModal taskKey={task.task_key} taskName={task.name} onClose={() => setLogsOpen(false)} />}
      <div className="tareas-cabecera">
        <div>
          <h3 className="tareas-titulo">{task.name}</h3>
          <p className="tareas-descripcion">{task.description}</p>
        </div>
        {/* Color calculado según el estado. */}
        <span className="tareas-estado" style={{ color: statusColor(task.last_status) }}>
          {task.last_status ? statusLabel(task.last_status) : 'sin ejecutar'}
        </span>
      </div>

      <div className="tareas-rejilla-160">
        <div className="form-group tareas-sin-margen">
          <label className="form-label">Cuándo</label>
          <select
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
            <label className="form-label">Hora</label>
            <input
              className="form-input"
              type="time"
              value={hora}
              onChange={e => setHora(e.target.value)}
              onBlur={handleHoraBlur}
            />
            <span className="form-hint">Cada día, hora de {task.timezone}</span>
          </div>
        ) : (
          <div className="form-group tareas-sin-margen">
            <label className="form-label">Intervalo</label>
            <select
              className="form-input form-select"
              value={interval}
              onChange={e => handleIntervalChange(Number(e.target.value))}
              disabled={saving}
            >
              {options.map(m => (
                <option key={m} value={m}>{m < 60 ? `${m} min` : `${m / 60}h`}</option>
              ))}
            </select>
            <span className="form-hint">Mínimo: {task.min_interval_minutes < 60 ? `${task.min_interval_minutes} min` : `${task.min_interval_minutes / 60}h`}</span>
          </div>
        )}

        <div>
          <div className="tareas-dato-etiqueta">Última ejecución</div>
          <div className="tareas-dato-valor">{formatDate(task.last_run_at)}</div>
        </div>

        <div>
          <div className="tareas-dato-etiqueta">Próxima ejecución</div>
          <div className="tareas-dato-valor">{formatCountdown(task.next_run_at, now)}</div>
        </div>
      </div>

      {task.opciones.length > 0 && (
        <div className="tareas-rejilla-200">
          {task.opciones.map(o => (
            <OpcionDeTarea key={o.clave} taskKey={task.task_key} opcion={o} onChanged={onChanged} onMsg={setMsg} />
          ))}
        </div>
      )}

      {task.last_summary && (
        task.last_status === 'failed'
          ? <p className="tareas-resumen tareas-resumen-error"><IconoAviso />{task.last_summary}</p>
          : <p className="tareas-resumen">{task.last_summary}</p>
      )}

      {msg && <p className="tareas-mensaje">{msg}</p>}

      <div className="tareas-acciones">
        {task.manual_allowed ? (
          <button className="btn btn-secondary btn-sm" onClick={handleRunNow} disabled={running}>
            {running ? 'Ejecutando…' : 'Ejecutar ahora'}
          </button>
        ) : (
          <span className="tareas-sin-manual">
            Sin refresco manual (para no saturar el servicio). Próxima automática: {formatCountdown(task.next_run_at, now)}
          </span>
        )}
        <button className="btn btn-secondary btn-sm" onClick={() => setLogsOpen(true)}>Ver logs</button>
      </div>
    </div>
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
          <div className="page-title">Tareas</div>
          <div className="page-subtitle">Tareas automáticas de sincronización</div>
        </div>
      </div>

      {loading ? <LoadingState label="Cargando tareas…" /> : error ? <ErrorState message={error} onRetry={load} /> : (
        <div data-tour="tasks-content" className="tareas-lista">
          {tasks.map(task => (
            <TaskCard key={task.task_key} task={task} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  )
}
