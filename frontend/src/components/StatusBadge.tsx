import { getLocalStatusInfo, getRequestStatusInfo, getNomenclatureStatusInfo } from '../utils/status'

interface StatusBadgeProps {
  status: string
  type?: 'local' | 'request' | 'nomenclature'
}

export function StatusBadge({ status, type = 'local' }: StatusBadgeProps) {
  const info =
    type === 'request'
      ? getRequestStatusInfo(status)
      : type === 'nomenclature'
      ? getNomenclatureStatusInfo(status)
      : getLocalStatusInfo(status)

  return (
    <span className={`badge ${info.cssClass}`}>
      {info.label}
    </span>
  )
}
