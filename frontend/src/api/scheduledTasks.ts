import { api } from './client'

export interface TaskOption {
  clave: string
  etiqueta: string
  valor: number
  minimo: number
  maximo: number
}

export interface ScheduledTask {
  task_key: string
  name: string
  description: string
  interval_minutes: number
  min_interval_minutes: number
  // "HH:MM": corre cada día a esa hora (la del servidor, `timezone`). null: cada `interval_minutes`.
  run_at: string | null
  timezone: string
  opciones: TaskOption[]
  manual_allowed: boolean
  enabled: boolean
  last_run_at: string | null
  last_status: string | null
  last_summary: string | null
  next_run_at: string | null
}

export interface RunScheduledTaskResult {
  task_key: string
  status: string
  summary: string
  next_run_at: string | null
}

export interface TaskRunLogEntry {
  id: number
  name: string
  status: string
  started_at: string | null
  finished_at: string | null
  summary: string | null
  details: string | null
}

export interface TaskRunLogsResponse {
  task_key: string
  logs: TaskRunLogEntry[]
}

export function getScheduledTasks(): Promise<ScheduledTask[]> {
  return api.get<ScheduledTask[]>('/tasks/scheduled')
}

export function updateScheduledTaskSchedule(
  taskKey: string,
  horario: { interval_minutes: number } | { run_at: string },
): Promise<ScheduledTask> {
  return api.put<ScheduledTask>(`/tasks/scheduled/${taskKey}`, horario)
}

export function updateScheduledTaskOptions(taskKey: string, valores: Record<string, number>): Promise<ScheduledTask> {
  return api.put<ScheduledTask>(`/tasks/scheduled/${taskKey}/opciones`, { valores })
}

export function runScheduledTaskNow(taskKey: string): Promise<RunScheduledTaskResult> {
  return api.post<RunScheduledTaskResult>(`/tasks/scheduled/${taskKey}/run`, {})
}

export function getScheduledTaskLogs(taskKey: string, limit = 20): Promise<TaskRunLogsResponse> {
  return api.get<TaskRunLogsResponse>(`/tasks/scheduled/${taskKey}/logs?limit=${limit}`)
}
