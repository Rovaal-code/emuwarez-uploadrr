import type { DashboardSummaryResponse } from '../../types/api'
import { StatCard } from '../StatCard'
import { formatNumero } from '../../utils/format'
import { ICON_LIBRARY, ICON_AVAILABLE, ICON_UNIQUE, ICON_REQUESTS, ICON_UPLOADS, EXPLICACION } from '../TarjetasDelPanel'

// La franja de cinco cifras del Panel: las tarjetas de siempre, en una fila. El resto de cifras están arriba de Estadísticas.
export function Franja({ resumen: s }: { resumen: DashboardSummaryResponse }) {
  return (
    <div className="panel-franja" role="group" aria-label="Cifras de la biblioteca y de las peticiones" data-tour="dashboard-stats">
      <StatCard
        icon={ICON_LIBRARY}
        label="En biblioteca"
        value={s.library_total}
        info={<>Películas y episodios importados desde tus instancias de Radarr y Sonarr.<br />Radarr: {formatNumero(s.radarr_items)} · Sonarr: {formatNumero(s.sonarr_items)}</>}
      />
      <StatCard icon={ICON_AVAILABLE} label="En disco" value={s.available} accentColor="var(--color-available)" info={EXPLICACION.available} />
      <StatCard icon={ICON_UNIQUE} label="Únicos sin subir" value={s.unique_content ?? 0} info={EXPLICACION.unique} />
      <StatCard icon={ICON_REQUESTS} label="Peticiones abiertas" value={s.requests_total ?? 0} info={EXPLICACION.requests} />
      <StatCard icon={ICON_UPLOADS} label="Tus subidas" value={s.uploads_completed ?? 0} info={EXPLICACION.uploads} />
    </div>
  )
}
