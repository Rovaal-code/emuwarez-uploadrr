/**
 * La lógica de «Hoy» (el Panel): cómo se reparten las recomendaciones, qué va en cada carril y qué dice cada línea.
 * El servidor ya da cada lista en su orden (las peticiones por recompensa); aquí solo se reparte y se redacta.
 */
import type { DashboardRecommendationItem } from '../api/dashboard'
import type { DashboardSummaryResponse, UploadJob } from '../types/api'
import { estadoCastellano } from './castellano'
import { formatBytes, formatItemType, parseServerDate, timeAgo } from './format'

const REC_GRUPO_PETICION = 1
const REC_GRUPO_UNICO = 2
const REC_GRUPO_FALTANTE = 3

/** Una subida fallida deja de avisar pasado este tiempo (o antes, si se reintenta o se borra). */
export const FALLIDA_VIGENTE_MS = 3 * 24 * 3600 * 1000
/** Cuántas subidas fallidas se listan; el resto es «y N más». */
export const FALLIDAS_MAX = 3
const MOTIVO_MAX = 90

export interface RecomendacionesRepartidas {
  /** Grupo 1: las peticiones de eMuwarez con una coincidencia compatible, por recompensa. */
  peticiones: DashboardRecommendationItem[]
  /** Grupo 2: contenido único que se puede subir sin que lo pida nadie. */
  unicos: DashboardRecommendationItem[]
  /** Grupo 3: lo que falta y se podría pedir a eMuwarez. */
  faltantes: DashboardRecommendationItem[]
}

export function repartirRecomendaciones(items: DashboardRecommendationItem[]): RecomendacionesRepartidas {
  const grupo = (g: number) => items.filter(i => i.rec_group === g)
  return { peticiones: grupo(REC_GRUPO_PETICION), unicos: grupo(REC_GRUPO_UNICO), faltantes: grupo(REC_GRUPO_FALTANTE) }
}

/** «Película · 1080p WEB-DL · castellano · 6,0 GB»: lo que se sabe, sin rayas donde no se sabe. */
export function lineaDeEspecificaciones(item: DashboardRecommendationItem): string {
  const castellano = {
    ambos: 'castellano', audio: 'castellano (audio)', subs: 'castellano (subs)', no: '', desconocido: '',
  }[estadoCastellano(item)]
  return [
    formatItemType(item.item_type),
    [item.resolution, item.source].filter(Boolean).join(' '),
    castellano,
    item.size_bytes ? formatBytes(item.size_bytes) : '',
  ].filter(Boolean).join(' · ')
}

/** Las subidas vivas, la que trabaja primero y luego la cola en su orden. */
export function ordenarEnCurso(vivas: UploadJob[]): UploadJob[] {
  const trabajando = (j: UploadJob) => (j.status === 'queued' ? 1 : 0)
  return [...vivas].sort((a, b) =>
    trabajando(a) - trabajando(b) || (a.queue_position ?? 0) - (b.queue_position ?? 0))
}

/** Las subidas que fallaron hace poco y nadie ha reintentado, la más reciente primero. */
export function fallidasRecientes(todas: UploadJob[], excluir: Set<number>, ahora = Date.now()): UploadJob[] {
  const reintentadas = new Set(todas.map(j => j.retry_of_job_id))
  const cuando = (j: UploadJob) => j.finished_at ?? j.updated_at ?? j.created_at ?? ''
  return todas
    .filter(j => j.id != null && j.status === 'failed' && !excluir.has(j.id) && !reintentadas.has(j.id)
      && ahora - parseServerDate(cuando(j)).getTime() < FALLIDA_VIGENTE_MS)
    .sort((a, b) => cuando(b).localeCompare(cuando(a)))
}

export type InstanciaCaida = NonNullable<DashboardSummaryResponse['instancias_caidas']>[number]

export type AvisoHoy =
  | { tipo: 'instancia'; clave: string; titulo: string; detalle: string }
  | { tipo: 'subida'; clave: string; titulo: string; detalle: string; jobId: number }
  | { tipo: 'version'; clave: string; titulo: string; detalle: null }
  | { tipo: 'mas'; clave: string; titulo: string; detalle: null }

// «hace 26 h» en vez de «hace 1 día» hasta los tres días: con una instancia apagada, un día más o menos importa.
function hace(iso: string): string {
  const horas = (Date.now() - parseServerDate(iso).getTime()) / 3_600_000
  return horas >= 24 && horas < 72 ? `hace ${Math.floor(horas)} h` : timeAgo(iso)
}

const primeraLinea = (texto: string) => {
  const linea = texto.split('\n').find(l => l.trim())?.trim() ?? ''
  return linea.length > MOTIVO_MAX ? `${linea.slice(0, MOTIVO_MAX - 1)}…` : linea
}

/** «Necesita atención»: instancias caídas, subidas fallidas (con «y N más» si no caben) y una versión nueva, en ese orden. Solo salud. */
export function avisosDeAtencion(
  { instancias, fallidas, versionNueva }:
  { instancias: InstanciaCaida[]; fallidas: UploadJob[]; versionNueva: string | null },
): AvisoHoy[] {
  const avisos: AvisoHoy[] = instancias.map(i => ({
    tipo: 'instancia', clave: `instancia-${i.id}`,
    titulo: `${i.nombre} no responde`,
    detalle: (i.ultima_sincronizacion ? `Biblioteca de ${hace(i.ultima_sincronizacion)}` : 'Biblioteca sin sincronizar')
      + ' · se sincroniza sola al volver',
  }))
  for (const j of fallidas.slice(0, FALLIDAS_MAX)) {
    avisos.push({
      tipo: 'subida', clave: `subida-${j.id}`, jobId: j.id!,
      titulo: `Subida fallida · ${j.title ?? `#${j.id}`}`,
      detalle: primeraLinea(j.error_message ?? '') || 'Sin motivo guardado',
    })
  }
  if (fallidas.length > FALLIDAS_MAX) {
    const resto = fallidas.length - FALLIDAS_MAX
    avisos.push({ tipo: 'mas', clave: 'mas', titulo: `y ${resto} ${resto === 1 ? 'subida fallida más' : 'subidas fallidas más'}`, detalle: null })
  }
  if (versionNueva) {
    avisos.push({ tipo: 'version', clave: 'version', titulo: `Versión nueva ${versionNueva} publicada`, detalle: null })
  }
  return avisos
}

const hora = (d: Date) => d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })

/** «Última sincronización hace 12 min · próxima a las 11:25». */
export function lineaSincronizacion(ultima: string | null, proxima: string | null, ahora = new Date()): string {
  const partes = [ultima ? `Última sincronización ${timeAgo(ultima)}` : 'Aún no se ha sincronizado']
  if (proxima) {
    const cuando = parseServerDate(proxima)
    const manana = new Date(ahora.getFullYear(), ahora.getMonth(), ahora.getDate() + 1)
    if (cuando <= ahora) partes.push('próxima en breve')
    else if (cuando.toDateString() === ahora.toDateString()) partes.push(`próxima a las ${hora(cuando)}`)
    else if (cuando.toDateString() === manana.toDateString()) partes.push(`próxima mañana a las ${hora(cuando)}`)
    else partes.push(`próxima el ${cuando.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit' })} a las ${hora(cuando)}`)
  }
  return partes.join(' · ')
}
