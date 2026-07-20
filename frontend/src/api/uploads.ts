import { api } from './client'
import type {
  UploadPreflightResponse,
  UploadJob,
  UploadJobLogsResponse,
  UploadStartRequest,
  UploadStartResult,
  UploadArtifactsResponse,
  UploadRetryRequest,
  OkResponse,
} from '../types/api'
import type { TrackRemuxOverride } from './nomenclature'
import { latestInChain } from '../utils/uploadStatus'

export async function uploadPreflight(itemId: number, requestId?: number): Promise<UploadPreflightResponse> {
  return api.post<UploadPreflightResponse>(`/library/${itemId}/upload/preflight`, { request_id: requestId ?? null })
}

export interface UploadQueueResult {
  status: string
  job: UploadJob | null
  errors: string[]
}

// Queues "Subir a eMuwarez": the job appears immediately in Subidas as
// 'queued' with a grace period (see services/upload_queue.py) before the
// server actually renames/remuxes/starts it — nothing runs synchronously here.
// `checks` — the pre-upload checks result the wizard already computed and
// showed the user before they confirmed, persisted on the new job so its
// detail page's "Verificación pre-subida" section can show exactly that,
// without re-running anything server-side.
export async function queueUpload(
  itemId: number,
  remuxOverrides?: Record<number, TrackRemuxOverride>,
  checks?: UploadChecksResult | null,
): Promise<UploadQueueResult> {
  return api.post<UploadQueueResult>(`/library/${itemId}/upload/queue`, {
    remux_overrides: remuxOverrides ?? null,
    checks: checks ?? null,
  })
}

export async function getUploads(params?: {
  status?: string; limit?: number; offset?: number; search?: string; library_item_id?: number
}): Promise<UploadJob[]> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  if (params?.search) qs.set('search', params.search)
  if (params?.library_item_id != null) qs.set('library_item_id', String(params.library_item_id))
  const query = qs.toString()
  return api.get<UploadJob[]>(`/uploads${query ? `?${query}` : ''}`)
}

// "Automático": no wizard involved. The job appears immediately in Subidas
// as 'staging' ("Preparando") while the server computes nomenclature/remux/
// checks previews in the background — see services/upload_queue.py.
// `overrides` — set only when checkAutoUploadSource() found a disparity and
// the user picked the source (and provider, if WEB-DL) by hand.
export async function queueAutoUpload(
  itemId: number,
  overrides?: { source?: string; provider?: string },
): Promise<UploadQueueResult> {
  return api.post<UploadQueueResult>(`/library/${itemId}/upload/auto`, {
    source: overrides?.source ?? null,
    provider: overrides?.provider ?? null,
  })
}

export interface AutoUploadSourceCheck {
  disparity: boolean
  from_name: string | null
  from_radarr: string | null
  from_mediainfo: string | null
}

// Quick pre-flight check run right before an "Automático" upload: does the
// file's own name resolve the source, or is Radarr/Sonarr's reported source
// at odds with what MediaInfo's bitrate tool estimates? Only flags that
// specific disagreement — see services/source_assistant.py::check_auto_upload_source.
export async function checkAutoUploadSource(itemId: number): Promise<AutoUploadSourceCheck> {
  return api.get<AutoUploadSourceCheck>(`/library/${itemId}/upload/auto/source-check`)
}

// Precheck before opening/confirming the wizard: is there already a job for
// this item (any status, including Completado)? Used to show "ya existe una
// subida — al continuar se encadenará a su historial" instead of creating an
// unrelated duplicate row.
export async function getExistingJobForItem(itemId: number): Promise<UploadJob | null> {
  const jobs = await getUploads({ library_item_id: itemId, limit: 50 })
  return latestInChain(jobs)
}

export async function getUploadJob(jobId: number): Promise<UploadJob> {
  return api.get<UploadJob>(`/uploads/${jobId}`)
}

export async function getUploadJobLogs(
  jobId: number,
  limit = 500,
  offset = 0,
): Promise<UploadJobLogsResponse> {
  return api.get<UploadJobLogsResponse>(`/uploads/${jobId}/logs?limit=${limit}&offset=${offset}`)
}

export async function getUploadJobArtifacts(jobId: number): Promise<UploadArtifactsResponse> {
  return api.get<UploadArtifactsResponse>(`/uploads/${jobId}/artifacts`)
}

export async function startUploadJob(
  jobId: number,
  body: UploadStartRequest,
): Promise<UploadStartResult> {
  return api.post<UploadStartResult>(`/uploads/${jobId}/start`, body)
}

export async function retryUploadJob(
  jobId: number,
  body: UploadRetryRequest,
): Promise<UploadStartResult> {
  return api.post<UploadStartResult>(`/uploads/${jobId}/retry`, body)
}

// Retries straight into the same queued/60s-countdown flow queueUpload()
// uses — no confirmation token, since it only ever creates a brand new job
// row (the original failed/cancelled job is never touched).
export async function retryUploadJobQueued(jobId: number): Promise<UploadQueueResult> {
  return api.post<UploadQueueResult>(`/uploads/${jobId}/retry-queued`, {})
}

export async function cancelUploadJob(jobId: number): Promise<unknown> {
  return api.post<unknown>(`/uploads/${jobId}/cancel`, {})
}

// Only ever called after the styled confirmation card — the token itself
// isn't user-typed, it's the same constant the backend requires
// (services/upload_execution.py::DELETE_CONFIRMATION_TOKEN).
const DELETE_CONFIRMATION_TOKEN = 'BORRAR_SUBIDA'

export async function deleteUploadJob(jobId: number): Promise<OkResponse> {
  return api.post<OkResponse>(`/uploads/${jobId}/delete`, { confirmation: DELETE_CONFIRMATION_TOKEN })
}

export interface UploadCheck {
  id: string
  label: string
  status: 'ok' | 'fail' | 'skip'
  message: string
}
export interface UploadChecksResult {
  checks: UploadCheck[]
  ready: boolean
}

export async function runUploadChecks(itemId: number): Promise<UploadChecksResult> {
  return api.post<UploadChecksResult>(`/library/${itemId}/upload/checks`, {})
}

export interface UploadChecksProgress {
  checks: UploadCheck[]
  done: boolean
  ready: boolean
}

// Poll this WHILE runUploadChecks() is in flight to see each check land as it
// actually completes (the full run is ~30s of real network calls).
export async function getUploadChecksProgress(itemId: number): Promise<UploadChecksProgress> {
  return api.get<UploadChecksProgress>(`/library/${itemId}/upload/checks/progress`)
}
