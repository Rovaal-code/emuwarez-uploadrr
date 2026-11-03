import type { DashboardSummaryResponse } from '../types/api'
import { StatCard } from './StatCard'
import { ServiceLabel } from './ServiceIcon'
import { IconoPelicula, IconoSerie } from './Iconos'
import { formatNumero } from '../utils/format'

// Iconos grandes de las tarjetas, uno por cifra (el `icon` de StatCard solo se pinta dentro del HUD).
function svgIcon(d: React.ReactNode) {
  // strokeLinecap="round" es lo que hace que el "M12 17h.01" de ICON_MISSING (la forma estándar de dibujar
  // el punto de la exclamación) salga como un punto y no desaparezca: con el "butt" por defecto un
  // trazo de longitud casi cero no pinta nada.
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
}
export const ICON_LIBRARY = svgIcon(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>)
export const ICON_AVAILABLE = svgIcon(<><path d="M21 15V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9" /><path d="M2 15h20l-2 5H4l-2-5z" /></>)
const ICON_MISSING = svgIcon(<><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></>)
export const ICON_UNIQUE = svgIcon(<><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" /><circle cx="12" cy="12" r="3.2" /></>)
export const ICON_UPLOADS = svgIcon(<path d="M12 19V5M5 12l7-7 7 7" />)
export const ICON_REQUESTS = svgIcon(<><rect x="9" y="3" width="6" height="4" rx="1" /><path d="M9 12h6M9 16h4" /></>)
const ICON_COMPATIBLE = svgIcon(<><circle cx="12" cy="12" r="9" /><path d="M8.5 12.3l2.3 2.3 4.7-4.7" /></>)
const ICON_PARTIAL = svgIcon(<><circle cx="12" cy="12" r="9" /><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" stroke="none" /></>)
const ICON_RECLAIMED = svgIcon(<><path d="M5 21V4" /><path d="M5 4h13l-3.2 4.2L18 12.5H5" /></>)
const ICON_MINE = svgIcon(<><path d="M22 2 11 13" /><path d="M22 2 15 22l-4-9-9-4 20-7z" /></>)

// Explicaciones que comparten estas tarjetas y la franja del Panel.
export const EXPLICACION = {
  available: 'Contenido cuyo archivo está presente en disco, listo para comparar o subir.',
  unique: 'Contenido disponible que aún no está en eMuwarez: las películas, las temporadas completas de series o documentales y sus capítulos. Son tus oportunidades de subida.',
  requests: 'Total de peticiones activas descargadas de eMuwarez.',
  uploads: 'Número de subidas a eMuwarez que has completado con Uploadrr.',
}

// Las diez tarjetas que antes llenaban el pie del Panel. El color de la cifra solo marca un estado
// (disponible, faltante, compatible, parcial); el resto va en el color del texto.
export function TarjetasDelPanel({ resumen: s }: { resumen: DashboardSummaryResponse }) {
  return (
    <>
      <div className="stat-cards-row">
        <StatCard
          icon={ICON_LIBRARY}
          label="Biblioteca sincronizada"
          value={s.library_total}
          info="Total de películas y episodios importados desde tus instancias de Radarr y Sonarr."
        >
          <div className="panel-sub-lista panel-sub-scroll">
            <div className="stat-card-sub-row">
              <ServiceLabel type="radarr" label={`Radarr: ${formatNumero(s.radarr_items)}`} size={13} />
            </div>
            <div className="stat-card-sub-row">
              <ServiceLabel type="sonarr" label={`Sonarr: ${formatNumero(s.sonarr_items)}`} size={13} />
            </div>
          </div>
        </StatCard>

        <StatCard
          icon={ICON_AVAILABLE}
          label="Disponibles"
          value={s.available}
          accentColor="var(--color-available)"
          info={EXPLICACION.available}
        />

        <StatCard
          icon={ICON_MISSING}
          label="Faltantes"
          value={s.missing}
          accentColor="var(--color-missing)"
          info="Contenido que Radarr/Sonarr conocen pero cuyo archivo aún no está en disco (falta, en cola o con error)."
        />

        <StatCard
          icon={ICON_UNIQUE}
          label="Contenido único"
          value={s.unique_content ?? 0}
          info={EXPLICACION.unique}
        >
          <div className="panel-sub-lista">
            <div className="stat-card-sub-row"><IconoPelicula /> {formatNumero(s.unique_movies ?? 0)} películas</div>
            <div className="stat-card-sub-row"><IconoSerie /> {formatNumero(s.unique_seasons ?? 0)} temporadas, {formatNumero(s.unique_episodes ?? 0)} capítulos</div>
          </div>
        </StatCard>

        <StatCard
          icon={ICON_UPLOADS}
          label="Tus subidas"
          value={s.uploads_completed ?? 0}
          info={EXPLICACION.uploads}
        />
      </div>

      <div className="stat-cards-row">
        <StatCard
          icon={ICON_REQUESTS}
          label="Peticiones eMuwarez"
          value={s.requests_total ?? 0}
          info={EXPLICACION.requests}
        />
        <StatCard
          icon={ICON_COMPATIBLE}
          label="Peticiones compatibles"
          value={s.requests_compatible ?? 0}
          accentColor="var(--color-available)"
          info="Peticiones cuya mejor coincidencia en tu biblioteca cumple resolución y source: quizás puedas cubrirlas."
        />
        <StatCard
          icon={ICON_PARTIAL}
          label="Peticiones parciales"
          value={s.requests_partial ?? 0}
          accentColor="var(--color-warning)"
          info="Peticiones cuya mejor coincidencia cumple solo parte de lo pedido (resolución o source, pero no ambos)."
        />
        <StatCard
          icon={ICON_RECLAIMED}
          label="Peticiones reclamadas"
          value={s.requests_reclaimed ?? 0}
          info="Peticiones ya Reclamadas en eMuwarez, tuyas y de otros: es el total. En Peticiones, cada una dice si la reclamaste tú, la reclamó otro usuario o eMuwarez no indica quién."
        />
        <StatCard
          icon={ICON_MINE}
          label="Mis peticiones"
          value={s.requests_mine ?? 0}
          info="Peticiones creadas por tu propio usuario de eMuwarez (según el nombre configurado en Ajustes)."
        />
      </div>
    </>
  )
}
