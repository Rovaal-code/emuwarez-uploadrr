import { getLocalStatusInfo, getRequestStatusInfo, getNomenclatureStatusInfo, getTaskStatusInfo } from '../utils/status'

interface StatusBadgeProps {
  status: string
  type?: 'local' | 'request' | 'nomenclature' | 'task'
}

export function StatusBadge({ status, type = 'local' }: StatusBadgeProps) {
  const info =
    type === 'request'
      ? getRequestStatusInfo(status)
      : type === 'nomenclature'
      ? getNomenclatureStatusInfo(status)
      : type === 'task'
      ? getTaskStatusInfo(status)
      : getLocalStatusInfo(status)

  return (
    <span className={`badge ${info.cssClass}`}>
      {info.label}
    </span>
  )
}
