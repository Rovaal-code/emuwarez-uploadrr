import type { UploadJob } from '../types/api'
import { PlainValue, ValueChip } from './DetailCard'
import { StatusBadge } from './StatusBadge'
import { useTooltip } from './Tooltip'

// La petición que cubrió la subida, con enlace a eMuwarez, tal como era al
// encolarla: la fila de Peticiones se borra cuando deja de estar abierta. Sin
// petición guardada, el estado en vivo de la ficha de biblioteca. Lo comparten
// la tabla de Subidas y la ficha de la subida.
export function PeticionDeSubida({ job }: { job: UploadJob }) {
  const { triggerProps, tooltipNode } = useTooltip(job.request_url ? 'Abrir la petición en eMuwarez' : null)
  if (!job.request_title) return <StatusBadge status={job.request_status || 'Sin petición'} type="request" />
  if (!job.request_url) return <PlainValue>{job.request_title}</PlainValue>
  return (
    <ValueChip linkable>
      <a className="hover-link txt" href={job.request_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} {...triggerProps}>
        {job.request_title}
        {tooltipNode}
      </a>
    </ValueChip>
  )
}
