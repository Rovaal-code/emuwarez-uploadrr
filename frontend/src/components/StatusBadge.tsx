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
  // 'No disponible' (you have an entry for this request's content, but no
  // real file — Faltante/en cola/error) isn't a real compatibility verdict
  // either — same plain dash as every other "nothing to show" field, instead
  // of a red badge. The comparison card below it still shows its own dashes
  // for the values that can't be compared without a file (see RequestsPage).
  if (type === 'request' && status === 'No disponible') {
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
