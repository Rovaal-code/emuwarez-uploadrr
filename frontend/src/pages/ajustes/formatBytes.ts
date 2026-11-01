import { formatNumero } from '../../utils/format'

export function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${formatNumero(n / 1024, 1)} KB`
  return `${formatNumero(n / 1024 / 1024, 2)} MB`
}
