import { getLocalStatusInfo, getRequestStatusInfo, getNomenclatureStatusInfo, getTaskStatusInfo, getEmuStatusInfo, getSpanishStatusInfo } from '../utils/status'

interface StatusBadgeProps {
  status: string
  type?: 'local' | 'request' | 'nomenclature' | 'task' | 'emu' | 'spanish'
}

export function StatusBadge({ status, type = 'local' }: StatusBadgeProps) {
  // Nomenclatura "N/A" (or none) isn't a real status — show the same plain
  // dash used for other empty columns instead of a badge.
  if (type === 'nomenclature' && (!status || status === 'N/A')) {
    return <span className="menores-sin-estado">—</span>
  }
  const info =
    type === 'request'
      ? getRequestStatusInfo(status)
      : type === 'nomenclature'
      ? getNomenclatureStatusInfo(status)
      : type === 'task'
      ? getTaskStatusInfo(status)
      : type === 'emu'
      ? getEmuStatusInfo(status)
      : type === 'spanish'
      ? getSpanishStatusInfo(status)
      : getLocalStatusInfo(status)

  return (
    <span className={`badge ${info.cssClass}`}>
      {info.label}
    </span>
  )
}
