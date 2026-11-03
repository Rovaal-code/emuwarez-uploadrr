import type { DashboardRecommendationItem } from '../../api/dashboard'
import { lineaDeEspecificaciones, type RecomendacionesRepartidas } from '../../utils/hoy'
import { recompensaDeRecomendacion } from '../../utils/recomendaciones'
import { DetailTitleText, PlainValue } from '../DetailCard'
import { EmptyState } from '../EmptyState'
import { IconoEstrella, IconoPuntos } from '../Iconos'
import { HoverTitle } from '../Tooltip'
import { Carril } from './Carril'
import { Cartel } from './Cartel'

const esSerie = (item: DashboardRecommendationItem) => ['series', 'season', 'episode'].includes(item.item_type)

function Fila({ item, extra, verPeticion, accion, onVerFicha }: {
  item: DashboardRecommendationItem
  extra?: string
  verPeticion?: () => void
  accion: React.ReactNode
  onVerFicha: (item: DashboardRecommendationItem) => void
}) {
  const recompensa = recompensaDeRecomendacion(item)
  const spec = [lineaDeEspecificaciones(item), extra].filter(Boolean).join(' · ')
  return (
    <li className="panel-item">
      <Cartel url={item.poster_url} serie={esSerie(item)} pequeno />
      <div className="panel-item-texto">
        <HoverTitle className="hover-link panel-item-titulo" onClick={() => onVerFicha(item)} tip="Ver ficha del contenido">
          <DetailTitleText title={item.content_name} />
        </HoverTitle>
        <div className="panel-item-spec">
          {spec}
          {verPeticion && <> · <HoverTitle as="span" className="hover-link" onClick={verPeticion} tip="Abrir la petición en Peticiones">Ver petición</HoverTitle></>}
        </div>
      </div>
      <div className="panel-item-accion">
        {recompensa !== null && <PlainValue icon={<IconoPuntos />}>{recompensa}</PlainValue>}
        {accion}
      </div>
    </li>
  )
}

// «Listo para subir»: las peticiones de eMuwarez que tu biblioteca ya cubre, la que más paga primero. Debajo, plegado,
// lo que no es una petición: contenido único que podrías subir y faltantes que podrías pedir.
export function CarrilListo({ recomendaciones, onSubir, onVerPeticion, onVerFicha, onSubirUnico, onPedir }: {
  recomendaciones: RecomendacionesRepartidas
  onSubir: (item: DashboardRecommendationItem) => void
  onVerPeticion: (item: DashboardRecommendationItem) => void
  onVerFicha: (item: DashboardRecommendationItem) => void
  onSubirUnico: (item: DashboardRecommendationItem) => void
  onPedir: (item: DashboardRecommendationItem) => void
}) {
  const { peticiones, unicos, faltantes } = recomendaciones
  const otros = unicos.length + faltantes.length
  const nota = peticiones.length
    ? `${peticiones.length} ${peticiones.length === 1 ? 'petición' : 'peticiones'} · por recompensa`
    : undefined

  return (
    <Carril titulo="Listo para subir" nota={nota} tour="dashboard-ready">
      {peticiones.length === 0 ? (
        <EmptyState
          icon={<IconoEstrella />}
          title="Ninguna petición lista"
          body="Cuando una petición de eMuwarez coincida con algo de tu biblioteca, aparecerá aquí con lo que paga."
        />
      ) : (
        <ul className="panel-lista">
          {peticiones.map(item => (
            <Fila key={item.rec_request_id ?? item.id} item={item} onVerFicha={onVerFicha}
              verPeticion={item.rec_request_id != null ? () => onVerPeticion(item) : undefined}
              accion={<button type="button" className="btn btn-primary btn-sm" onClick={() => onSubir(item)}>Subir</button>} />
          ))}
        </ul>
      )}

      {otros > 0 && (
        <details className="panel-mas">
          <summary>Otras ideas (sin petición)</summary>
          {unicos.length > 0 && (
            <>
              <div className="upload-panel-group">Contenido único que puedes subir</div>
              <ul className="panel-lista">
                {unicos.map(item => (
                  <Fila key={item.id} item={item} onVerFicha={onVerFicha}
                    accion={<button type="button" className="btn btn-secondary btn-sm" onClick={() => onSubirUnico(item)}>Subir</button>} />
                ))}
              </ul>
            </>
          )}
          {faltantes.length > 0 && (
            <>
              <div className="upload-panel-group">Faltantes que podrías pedir a eMuwarez</div>
              <ul className="panel-lista">
                {faltantes.map(item => (
                  <Fila key={`${item.id}-${item.season_number ?? ''}`} item={item} extra={item.missing_count ? `faltan ${item.missing_count}` : undefined}
                    onVerFicha={onVerFicha}
                    accion={<button type="button" className="btn btn-secondary btn-sm" onClick={() => onPedir(item)}>Pedir</button>} />
                ))}
              </ul>
            </>
          )}
        </details>
      )}
    </Carril>
  )
}
