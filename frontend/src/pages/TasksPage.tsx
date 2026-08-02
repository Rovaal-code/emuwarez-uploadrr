import { useState, useEffect, useCallback } from 'react'
import {
  getScheduledTasks, updateScheduledTaskInterval, runScheduledTaskNow, getScheduledTaskLogs,
  type ScheduledTask, type TaskRunLogEntry,
} from '../api/scheduledTasks'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { formatDate } from '../utils/format'
import { useRefrescoPorAvisos } from '../hooks/useRefrescoPorAvisos'

const INTERVAL_OPTIONS_MINUTES = [15, 30, 45, 60, 90, 120, 180, 360, 720]

const STATUS_COLOR: Record<string, string> = {
  completed: '#22c55e',
  failed: '#ef4444',
  skipped: '#f59e0b',
  running: '#3b82f6',
}

function statusColor(status: string | null): string {
  if (!status) return '#6b7280'
  return STATUS_COLOR[status] ?? '#6b7280'
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
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 700 }}>
        <div className="modal-header">
          <h2 className="modal-title">Logs — {taskName}</h2>
          <button className="btn-icon" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body" style={{ maxHeight: 480, overflowY: 'auto' }}>
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
                    <td><span style={{ color: statusColor(log.status), fontSize: 12, fontWeight: 600 }}>{statusLabel(log.status)}</span></td>
                    <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{formatDate(log.started_at)}</td>
                    <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{formatDate(log.finished_at)}</td>
                    <td style={{ fontSize: 12 }}>
                      {log.status === 'failed' && log.summary
                        ? <span style={{ color: '#ef4444', display: 'inline-flex', alignItems: 'center', gap: 6 }}><span aria-hidden>⚠</span>{log.summary}</span>
                        : (log.summary ?? '—')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="detail-panel__actions" style={{ padding: '10px 16px' }}>
          <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>Actualizar</button>
          <button className="btn btn-secondary" onClick={onClose} style={{ marginLeft: 'auto' }}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}

function TaskCard({ task, onChanged }: { task: ScheduledTask; onChanged: () => void }) {
  const [interval, setIntervalValue] = useState(task.interval_minutes)
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

  async function handleIntervalChange(minutes: number) {
    setIntervalValue(minutes)
    setSaving(true)
    setMsg(null)
    try {
      await updateScheduledTaskInterval(task.task_key, minutes)
      onChanged()
    } catch (e: unknown) {
      setMsg(`✗ ${e instanceof Error ? e.message : 'Error al guardar el intervalo'}`)
    } finally {
      setSaving(false)
    }
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div>
          <h3 style={{ marginTop: 0, marginBottom: 4 }}>{task.name}</h3>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0, maxWidth: 480 }}>{task.description}</p>
        </div>
        <span style={{
          fontSize: 11, fontWeight: 600, padding: '3px 8px', borderRadius: 6,
          color: statusColor(task.last_status),
          background: 'rgba(255,255,255,0.04)',
          whiteSpace: 'nowrap',
        }}>
          {task.last_status ? statusLabel(task.last_status) : 'sin ejecutar'}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 14, marginTop: 16 }}>
        <div className="form-group" style={{ marginBottom: 0 }}>
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

        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>Última ejecución</div>
          <div style={{ fontSize: 13 }}>{formatDate(task.last_run_at)}</div>
        </div>

        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>Próxima ejecución</div>
          <div style={{ fontSize: 13 }}>{formatCountdown(task.next_run_at, now)}</div>
        </div>
      </div>

      {task.last_summary && (
        task.last_status === 'failed'
          ? <p style={{ fontSize: 12, color: '#ef4444', marginTop: 10, marginBottom: 0, display: 'flex', alignItems: 'center', gap: 6 }}><span aria-hidden>⚠</span>{task.last_summary}</p>
          : <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 10, marginBottom: 0 }}>{task.last_summary}</p>
      )}

      {msg && <p style={{ fontSize: 12, marginTop: 10, marginBottom: 0 }}>{msg}</p>}

      <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
        {task.manual_allowed ? (
          <button className="btn btn-secondary btn-sm" onClick={handleRunNow} disabled={running}>
            {running ? 'Ejecutando…' : 'Ejecutar ahora'}
          </button>
        ) : (
          <span style={{ fontSize: 12, color: 'var(--text-muted)', alignSelf: 'center' }}>
            Sin refresco manual (para no saturar el servicio) — próxima automática {formatCountdown(task.next_run_at, now)}
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
        <div data-tour="tasks-content" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {tasks.map(task => (
            <TaskCard key={task.task_key} task={task} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  )
}
