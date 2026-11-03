import type { DashboardSummaryResponse } from '../../types/api'
import { formatNumero } from '../../utils/format'

// La franja de cinco números del Panel. El resto de cifras del Panel están arriba de Estadísticas.
export function Franja({ resumen: s }: { resumen: DashboardSummaryResponse }) {
  const cifras: [string, number][] = [
    ['en biblioteca', s.library_total],
    ['en disco', s.available],
    ['únicos sin subir', s.unique_content ?? 0],
    ['peticiones abiertas', s.requests_total ?? 0],
    ['tus subidas', s.uploads_completed ?? 0],
  ]
  return (
    <dl className="panel-franja" data-tour="dashboard-stats">
      {cifras.map(([etiqueta, valor]) => (
        <div key={etiqueta} className="panel-franja-cifra">
          <dt>{etiqueta}</dt>
          <dd>{formatNumero(valor)}</dd>
        </div>
      ))}
    </dl>
  )
}
