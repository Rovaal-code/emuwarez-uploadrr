import { api } from './client'
import type {
  UploadPreflightResponse,
  UploadJob,
  UploadJobLogsResponse,
  UploadStartRequest,
  UploadStartResult,
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
  // The wizard's already-merged (base plan + remuxOverrides) track table —
  // persisted immediately so the job detail page doesn't show "Pendiente"
  // until the pipeline actually runs the remux step.
  remuxSnapshot?: { ordered_tracks: unknown[] } | null,
  // Season-pack-only: Título/Source/Proveedor/Tag confirmed in the wizard's
  // editable season fields, applied uniformly across every episode.
  // Undefined/omitted for a single movie/episode, whose Título already
  // persists through saveNomenclatureFields instead.
  seasonOverrides?: {
    source?: string | null; provider?: string | null; tag?: string | null; title?: string | null
    // El idioma elegido para cada pista de audio sin idioma, por posición.
    idiomas?: Record<number, string>
  },
  // La petición desde la que se abrió el asistente: la subida la cubre y
  // Subidas la enseña.
  requestItemId?: number | null,
): Promise<UploadQueueResult> {
  return api.post<UploadQueueResult>(`/library/${itemId}/upload/queue`, {
    request_item_id: requestItemId ?? null,
    remux_overrides: remuxOverrides ?? null,
    checks: checks ?? null,
    remux_snapshot: remuxSnapshot ?? null,
    source: seasonOverrides?.source ?? null,
    provider: seasonOverrides?.provider ?? null,
    tag: seasonOverrides?.tag ?? null,
    title: seasonOverrides?.title ?? null,
    idiomas: seasonOverrides?.idiomas ?? null,
  })
}

export interface UploadsQuery {
  // Uno o varios estados separados por coma («running,preparing»).
  status?: string; limit?: number; offset?: number; search?: string; library_item_id?: number
  // Sin las filas de antes de que un trabajo solo naciera al pulsar Subir: se quitan en el servidor,
  // antes de aplicar el límite, para que no ocupen sitio en la página.
  hide_preparatory?: boolean
}

function uploadsQueryString(params?: UploadsQuery): string {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.hide_preparatory) qs.set('hide_preparatory', 'true')
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  if (params?.search) qs.set('search', params.search)
  if (params?.library_item_id != null) qs.set('library_item_id', String(params.library_item_id))
  const query = qs.toString()
  return query ? `?${query}` : ''
}

export async function getUploads(params?: UploadsQuery): Promise<UploadJob[]> {
  return api.get<UploadJob[]>(`/uploads${uploadsQueryString(params)}`)
}

// Cuántas subidas hay con esos filtros, sin el límite de la lista: el «M» de «N de M».
export async function countUploads(params?: Omit<UploadsQuery, 'limit' | 'offset'>): Promise<number> {
  return (await api.get<{ total: number }>(`/uploads/count${uploadsQueryString(params)}`)).total
}

// "Automático": no wizard involved. The job appears immediately in Subidas
// as 'staging' ("Preparando") while the server computes nomenclature/remux/
// checks previews in the background — see services/upload_queue.py.
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

// `afterSequence`: solo las líneas posteriores a esa (la `sequence` de la última que ya se tiene), para seguir una
// subida en vivo sin bajar el registro entero cada vez.
export async function getUploadJobLogs(
  jobId: number,
  limit = 500,
  offset = 0,
  tail = false,
  afterSequence?: number,
): Promise<UploadJobLogsResponse> {
  const after = afterSequence != null ? `&after_sequence=${afterSequence}` : ''
  return api.get<UploadJobLogsResponse>(`/uploads/${jobId}/logs?limit=${limit}&offset=${offset}&tail=${tail}${after}`)
}

export async function startUploadJob(
  jobId: number,
  body: UploadStartRequest,
): Promise<UploadStartResult> {
  return api.post<UploadStartResult>(`/uploads/${jobId}/start`, body)
}

// Reintenta por el mismo camino en cola que queueUpload(), sin token de
// confirmación: solo crea un trabajo nuevo y no toca el original (fallido o cancelado).
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

// `scope` parte la pasada para una selección de varias temporadas o
// capítulos: 'content' son las del elemento (una por elemento) y
// 'environment' las compartidas (una sola vez para toda la tanda). Sin
// scope, las hace todas, que es lo que necesita un solo elemento.
export async function runUploadChecks(
  itemId: number,
  scope?: 'content' | 'environment',
  // Temporada: el Proveedor elegido (utils/origenProveedor.ts::proveedorParaServidor), el mismo que la vista previa y la cola.
  provider?: string,
): Promise<UploadChecksResult> {
  const qs = new URLSearchParams()
  if (scope) qs.set('scope', scope)
  if (provider !== undefined) qs.set('provider', provider)
  const query = qs.toString()
  return api.post<UploadChecksResult>(`/library/${itemId}/upload/checks${query ? `?${query}` : ''}`, {})
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
