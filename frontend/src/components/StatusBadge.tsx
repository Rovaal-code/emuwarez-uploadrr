import { getLocalStatusInfo, getRequestStatusInfo, getNomenclatureStatusInfo, getTaskStatusInfo, getEmuStatusInfo } from '../utils/status'

interface StatusBadgeProps {
  status: string
  type?: 'local' | 'request' | 'nomenclature' | 'task' | 'emu'
}

export function StatusBadge({ status, type = 'local' }: StatusBadgeProps) {
  // Nomenclatura "N/A" (or none) isn't a real status — show the same plain
  // dash used for other empty columns instead of a badge.
  if (type === 'nomenclature' && (!status || status === 'N/A')) {
    return <span style={{ color: 'var(--text-muted)' }}>—</span>
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
      : getLocalStatusInfo(status)

  return (
    <span className={`badge ${info.cssClass}`}>
      {info.label}
    </span>
  )
}
