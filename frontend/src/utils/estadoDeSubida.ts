import type { SeedingResponse } from '../api/seeding'
import type { UploadJob } from '../types/api'
import { claseSeeding, seedingDe } from './seeding'
import { currentPhaseInfo, phaseLabel, progressCounter, queuedWaitText, statusLabel } from './uploadStatus'

// El estado de una subida tal como lo abre el detalle: una frase, su tono (el único color de la cabecera) y,
// si falló o quedó a medias, el motivo.
export type Tono = 'ok' | 'aviso' | 'error' | 'curso' | 'neutro'

export interface EstadoVisible {
  tono: Tono
  simbolo: string
  titulo: string
  // Lo que acompaña al título: la fase en curso, el puesto en la cola…
  resumen?: string
  // Por qué falló, o qué quedó a medias.
  motivo?: string
  // El tiempo transcurrido, aparte para que no se anuncie entero en cada cambio.
  transcurrido?: string
  // El estado en qBittorrent de una subida completada, con la clase de insignia de Seeding.
  seeding?: { texto: string; clase: string }
}

function pasoDe(job: UploadJob, estado: string): string | undefined {
  return job.pasos?.find(p => p.estado === estado)?.nombre
}

export function estadoVisible(job: UploadJob, seeding: SeedingResponse | null): EstadoVisible {
  switch (job.status) {
    case 'completed': {
      const i = seedingDe(seeding, job.id)
      const enQbit = i ? { texto: `${i.etiqueta} en qBittorrent`, clase: claseSeeding(i.estado) } : undefined
      const sinQbit = job.progress?.phases?.some(p => p.key === 'qbittorrent_add' && p.status === 'failed')
      const titulo = job.result_url ? 'Subido a eMuwarez' : 'Subida completada'
      if (sinQbit) {
        return { tono: 'aviso', simbolo: '!', titulo, seeding: enQbit,
          motivo: 'El torrent está en eMuwarez, pero no se pudo añadir a qBittorrent: añádelo a mano para sembrarlo.' }
      }
      return { tono: 'ok', simbolo: '✓', titulo, seeding: enQbit }
    }
    case 'failed': {
      const paso = pasoDe(job, 'fallido')
      return { tono: 'error', simbolo: '✕', titulo: paso ? `Falló en «${paso}»` : 'La subida falló',
        motivo: job.error_message || undefined }
    }
    case 'cancelled': {
      const paso = pasoDe(job, 'cancelado')
      return { tono: 'neutro', simbolo: '■', titulo: paso ? `Cancelada en «${paso}»` : 'Subida cancelada',
        motivo: job.error_message || undefined }
    }
    case 'running':
    case 'preparing': {
      const info = currentPhaseInfo(job)
      const fase = info?.label ?? phaseLabel(job.progress_phase)
      const contador = progressCounter(job)
      return { tono: 'curso', simbolo: '●', titulo: 'Subiendo',
        resumen: `${fase}${info?.counterText ? ` (${info.counterText})` : ''}`, transcurrido: contador || undefined }
    }
    case 'queued':
      return { tono: 'curso', simbolo: '●', titulo: 'En cola', resumen: queuedWaitText(job) }
    case 'staging':
      return { tono: 'curso', simbolo: '●', titulo: 'Preparando', resumen: 'Generando nomenclatura' }
    case 'ready':
      return { tono: 'neutro', simbolo: '○', titulo: 'Lista para subir' }
    default:
      return { tono: 'neutro', simbolo: '○', titulo: statusLabel(job.status) }
  }
}
