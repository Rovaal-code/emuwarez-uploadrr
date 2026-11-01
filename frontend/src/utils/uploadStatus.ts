import { useEffect, useState } from 'react'
import type { UploadJob } from '../types/api'
import { parseServerDate } from './format'

// Shared between UploadsPage's table and UploadJobDetailPage — a single
// source of truth for Estado's label/color mapping and phase/countdown math,
// so the list and the detail page never drift.

export const UPLOAD_TYPE_LABEL: Record<string, string> = {
  movie: 'Película', series: 'Serie', season: 'Temporada', episode: 'Episodio',
}

// Same semantic palette as the Progreso badge: azul=en cola/en curso
// (preparando o subiendo — ambos se muestran igual, "Subiendo", ya no hay un
// estado "Preparando" aparte), verde=completado, rojo=fallido, gris=cancelado.
export const STATUS_CLASS: Record<string, string> = {
  ready: 'badge req-compatible',
  preflight: 'badge status-queued',
  blocked: 'badge status-error',
  draft: 'badge status-unknown',
  staging: 'badge status-queued',
  queued: 'badge status-queued',
  preparing: 'badge status-queued',
  running: 'badge status-queued',
  completed: 'badge status-available',
  failed: 'badge status-error',
  cancelled: 'badge status-unknown',
}

export const STATUS_LABEL: Record<string, string> = {
  ready: 'Listo',
  preflight: 'Verificación',
  config_staging: 'Configurando',
  blocked: 'Bloqueado',
  draft: 'Borrador',
  // Subida "Automático": el servidor está generando nomenclatura/remux/
  // comprobaciones antes de que el job pueda pasar a "En cola" de verdad.
  staging: 'Preparando',
  queued: 'En cola',
  // "Preparando" ya no es un estado propio de cara al usuario para el flujo
  // manual — en cuanto deja de estar en cola (empieza a comprobar
  // integridad/renombrar/remuxear) se muestra como "Subiendo", mismo texto
  // que el estado 'running' real — el detalle de qué está haciendo vive en
  // Progreso. (No confundir con el 'staging' de arriba, que sí es un estado
  // propio, previo a la cola.)
  preparing: 'Subiendo',
  running: 'Subiendo',
  completed: 'Completado',
  failed: 'Fallido',
  cancelled: 'Cancelado',
}

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] || (status ? status.charAt(0).toUpperCase() + status.slice(1) : '—')
}

// A job in any of these statuses is still "alive" — a new upload for the
// same item must not create an unrelated second job while one of these is
// in flight (mirrors ACTIVE_JOB_STATUSES in services/upload_queue.py).
export const ACTIVE_JOB_STATUSES = new Set(['queued', 'staging', 'preparing', 'running'])

// The tip of a retry chain: the job nobody else's retry_of_job_id points at.
// Given ALL jobs for one library item (any order), returns the one that
// represents "the current state of this item's upload" — used both by the
// wizard's "ya existe una subida" precheck and could back a future chain
// viewer outside UploadsPage's own ancestorsOf()/hasNewerRetry pair.
export function latestInChain(jobs: UploadJob[]): UploadJob | null {
  if (jobs.length === 0) return null
  const referenced = new Set(jobs.map(j => j.retry_of_job_id).filter((id): id is number => id != null))
  return jobs.find(j => j.id != null && !referenced.has(j.id)) ?? jobs[jobs.length - 1]
}

// Human labels for the computed progress_phase (the coarse string, not the %).
const PHASE_LABEL: Record<string, string> = {
  staging: 'Generando nomenclatura',
  queued: 'En cola',
  // Las siete fases que publica el backend (services/uploadrr_progress.py,
  // PHASES). Sin una de ellas aquí, phaseLabel() devolvería su clave interna
  // cruda ("hash_torrent") — y eso pasa justo cuando no hay progreso legible,
  // o sea con un trabajo atascado, que es el peor momento para enseñar jerga.
  // Lo vigila tests/test_copias_frontend.py.
  verificacion_presubida: 'Inicio de Uploadrr',
  nomenclature: 'Aplicando nomenclatura',
  remux: 'Reordenando/renombrando pistas',
  screenshots: 'Generando y subiendo capturas',
  hash_torrent: 'Calculando el hash del torrent',
  uploading_emu: 'Subiendo a eMuwarez',
  qbittorrent_add: 'Subiendo a qBittorrent',
  config_staging: 'Preparando configuración',
  // Repliegue genérico cuando no hay ninguna fase "running" detectable (p.ej.
  // Uploadrr-EMU atascado reintentando en silencio) — deliberadamente NO usa
  // el mismo texto que la fase real "Subida a eMuwarez" (uploading_emu), o
  // parece que el job saltó de fase cuando en realidad no se detectó ninguna.
  running: 'En progreso',
  finalizing: 'Finalizando',
  succeeded: 'Completado',
  failed: 'Fallido',
  timeout: 'Tiempo agotado',
  cancelled: 'Cancelado',
}

export function phaseLabel(phase?: string | null): string {
  if (!phase) return '—'
  return PHASE_LABEL[phase] || phase
}

// Action (gerund) form of each real pipeline sub-phase tracked in
// job.progress.phases (services/uploadrr_progress.py's PHASES) — used by the
// Progreso field, which shows "what's happening right now" rather than the
// Fases table's noun-form label ("Comprobación de integridad" there,
// "Comprobando integridad" here). Kept short — Progreso's value has to fit
// a narrow column/panel, so none of these run longer than the previous
// longest phase label ("Reordenando/renombrando pistas", 31 chars).
const PROGRESS_ACTION_LABEL: Record<string, string> = {
  verificacion_presubida: 'Iniciando Uploadrr',
  nomenclature: 'Aplicando nomenclatura',
  remux: 'Reordenando/renombrando pistas',
  screenshots: 'Generando/subiendo capturas',
  hash_torrent: 'Calculando hash del torrent',
  uploading_emu: 'Subiendo a eMuwarez',
  qbittorrent_add: 'Subiendo a qBittorrent',
}

// <60s → "Ns"; <60min → "Mm Ss"; else → "Hh Mm" — Progreso/Duración show
// live elapsed time that can run well past a minute (or an hour, for a
// large season pack), so raw seconds stop being readable past ~90s.
export function formatSecondsHM(totalSeconds: number): string {
  const secs = Math.max(0, Math.round(totalSeconds))
  if (secs < 60) return `${secs}s`
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = secs % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m ${s}s`
}

export interface CurrentPhaseInfo {
  label: string
  // "3/14" — this phase's 1-based position among all of them.
  counterText: string
}

// Finds whichever phase is currently "running" in job.progress.phases (the
// same array behind the Fases table) and returns its action-form label and
// its position — instead of progress_phase's much coarser
// "running"/"config_staging"/"finalizing" bucket, which has no per-phase
// detail at all. Elapsed time next to it is still the job's OVERALL total
// (progressCounter/formatElapsed) — that's the number that's actually
// meaningful to the user, not how long just this one sub-step has run.
// Returns null when there's no live phase array yet (right at job start)
// or nothing is currently running in it, so callers can fall back to
// phaseLabel().
export function currentPhaseInfo(job: UploadJob): CurrentPhaseInfo | null {
  const phases = job.progress?.phases
  if (!phases || phases.length === 0) return null
  const idx = phases.findIndex(p => p.status === 'running')
  if (idx === -1) return null
  const phase = phases[idx]
  return {
    label: PROGRESS_ACTION_LABEL[phase.key] || phase.label,
    counterText: `${idx + 1}/${phases.length}`,
  }
}

// Live "Xs" counter next to the current phase — ticks while the job is
// actually doing something (preparing/running only — Progreso shows nothing
// for queued (queuedWaitText covers that) or terminal states (Estado
// already says Completado/Fallido/Cancelado, no need to repeat it here)).
export function progressCounter(job: UploadJob): string | null {
  if (job.started_at) {
    const secs = Math.max(0, Math.round((Date.now() - parseServerDate(job.started_at).getTime()) / 1000))
    return formatSecondsHM(secs)
  }
  return null
}

export function formatElapsed(job: UploadJob): string {
  if (job.duration_seconds != null) return formatSecondsHM(job.duration_seconds)
  if (job.status === 'running' && job.started_at) {
    const secs = Math.max(0, Math.round((Date.now() - parseServerDate(job.started_at).getTime()) / 1000))
    return formatSecondsHM(secs)
  }
  return '—'
}

// Texto de una subida «En cola». Solo lo está mientras espera plaza en
// "Subidas en paralelo" (sin espera fija: si hay plaza empieza al momento), y
// el servidor da su puesto (upload_queue.get_queue_positions) en el mismo
// orden en que entran. Cuando la cola avanza, el servidor avisa (subida-estado)
// y la pantalla recarga: aquí no hay reloj.
export function queuedWaitText(job: UploadJob): string {
  const { queue_position: pos, queue_total: total } = job
  if (pos == null) return 'Esperando turno'
  return total != null && total > 1 ? `Puesto ${pos} de ${total}` : 'Siguiente en entrar'
}

// Forces a re-render every `intervalMs` while `active` — keeps live elapsed
// times ticking without depending on the next server poll.
export function useTicker(active: boolean, intervalMs = 1000) {
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!active) return
    const t = setInterval(() => setTick(n => n + 1), intervalMs)
    return () => clearInterval(t)
  }, [active, intervalMs])
}
