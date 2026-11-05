import type { DashboardRecommendationItem } from '../../api/dashboard'
import { claveDelPanel } from '../../utils/lote'
import { lineaDeEspecificaciones, textoDeAporte, type RecomendacionesRepartidas } from '../../utils/hoy'
import { recompensaDeRecomendacion } from '../../utils/recomendaciones'
import { DetailTitleText, LanguageValueIcon, PlainValue, ReleaseGroupValueIcon, SubtitleValueIcon } from '../DetailCard'
import { EmptyState } from '../EmptyState'
import { IconoEstrella, IconoPuntos } from '../Iconos'
import { BarraLote } from '../lote/BarraLote'
import { CasillaLote } from '../lote/CasillaLote'
import { HoverTitle, Tooltip } from '../Tooltip'
import { Carril } from './Carril'
import { Cartel } from './Cartel'

const esSerie = (item: DashboardRecommendationItem) => ['series', 'season', 'episode'].includes(item.item_type)

// «Subir seleccionadas»: lo marcado vive en el Panel (que lo limpia al salir y al encolar el lote); aquí, la casilla
// de cada fila, el botón «Seleccionar» y la barra al pie del carril.
export interface SeleccionCarril {
  activa: boolean
  onAlternarModo: () => void
  // Por la clave de la fila (`claveDelPanel`).
  tiene: (clave: string) => boolean
  alternar: (item: DashboardRecommendationItem) => void
  lleno: boolean
  total: number
  onSubir: () => void
  onLimpiar: () => void
}

function Fila({ item, extra, verPeticion, accion, onVerFicha, seleccion }: {
  item: DashboardRecommendationItem
  extra?: string
  verPeticion?: () => void
  accion: React.ReactNode
  onVerFicha: (item: DashboardRecommendationItem) => void
  // Con la selección encendida, la fila lleva su casilla (no en faltantes, que solo se piden).
  seleccion?: SeleccionCarril
}) {
  const recompensa = recompensaDeRecomendacion(item)
  const spec = [lineaDeEspecificaciones(item), extra].filter(Boolean).join(' · ')
  const grupo = item.release_group?.trim()
  const audio = item.audio_languages ?? []
  const subs = item.subtitle_languages ?? []
  return (
    <li className="panel-item">
      {seleccion?.activa && (
        <CasillaLote
          item={item} titulo={item.content_name} seleccionado={seleccion.tiene(claveDelPanel(item))}
          bloqueada={seleccion.lleno} onAlternar={seleccion.alternar}
        />
      )}
      <Cartel url={item.poster_url} serie={esSerie(item)} />
      <div className="panel-item-texto">
        <HoverTitle className="hover-link panel-item-titulo" onClick={() => onVerFicha(item)} tip="Ver ficha del contenido">
          <DetailTitleText title={item.content_name} />
        </HoverTitle>
        <div className="panel-item-spec">{spec}</div>
        {(item.rec_aportes ?? []).length > 0 && (
          <div className="panel-item-aportes">
            <span className="solo-lector">Tu copia aporta: </span>
            {(item.rec_aportes ?? []).map((a, i) => <span key={i} className="panel-aporte">{textoDeAporte(a)}</span>)}
          </div>
        )}
        {(grupo || audio.length > 0 || subs.length > 0 || verPeticion) && (
          <div className="panel-item-meta">
            {grupo && (
              <span className="panel-rg" title={grupo}>
                <span className="vicon"><ReleaseGroupValueIcon /></span>
                <span className="solo-lector">Grupo de release: </span><span className="panel-rg-texto">{grupo}</span>
              </span>
            )}
            {audio.length > 0 && (
              <span className="panel-idiomas" title={`Audio: ${audio.join(', ')}`}>
                <PlainValue icon={<LanguageValueIcon />}><span className="solo-lector">Audio: </span>{audio.join(', ')}</PlainValue>
              </span>
            )}
            {subs.length > 0 && (
              <span className="panel-idiomas" title={`Subtítulos: ${subs.join(', ')}`}>
                <PlainValue icon={<SubtitleValueIcon />}><span className="solo-lector">Subtítulos: </span>{subs.join(', ')}</PlainValue>
              </span>
            )}
            {verPeticion && <HoverTitle as="span" className="hover-link panel-item-ver" onClick={verPeticion} tip="Abrir la petición en Peticiones">Ver petición</HoverTitle>}
          </div>
        )}
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
export function CarrilListo({ recomendaciones, onSubir, onVerPeticion, onVerFicha, onSubirUnico, onPedir, seleccion }: {
  recomendaciones: RecomendacionesRepartidas
  onSubir: (item: DashboardRecommendationItem) => void
  onVerPeticion: (item: DashboardRecommendationItem) => void
  onVerFicha: (item: DashboardRecommendationItem) => void
  onSubirUnico: (item: DashboardRecommendationItem) => void
  onPedir: (item: DashboardRecommendationItem) => void
  seleccion?: SeleccionCarril
}) {
  const { peticiones, unicos, faltantes, mejoras } = recomendaciones
  const otros = unicos.length + faltantes.length + mejoras.length
  const nota = peticiones.length
    ? `${peticiones.length} ${peticiones.length === 1 ? 'petición' : 'peticiones'} · por recompensa`
    : undefined
  const seleccionables = peticiones.length + unicos.length + mejoras.length

  return (
    <Carril
      titulo="Listo para subir" nota={nota} tour="dashboard-ready"
      accion={seleccion && (seleccionables > 0 || seleccion.activa) && (
        <Tooltip content="Marca varias para subirlas de una vez">
          <button
            type="button"
            className={`btn btn-secondary btn-sm${seleccion.activa ? ' lote-boton-activo' : ''}`}
            onClick={seleccion.onAlternarModo}
            aria-pressed={seleccion.activa}
          >
            Seleccionar
          </button>
        </Tooltip>
      )}
      pie={seleccion?.activa && (
        <BarraLote
          className="lote-barra-carril" total={seleccion.total}
          vacia="Marca las peticiones o ideas que quieras subir juntas"
          textoSubir={`Subir seleccionadas (${seleccion.total})`}
          onSubir={seleccion.onSubir} onLimpiar={seleccion.onLimpiar}
        />
      )}
    >
      {peticiones.length === 0 ? (
        <EmptyState
          icon={<IconoEstrella />}
          title="Ninguna petición lista"
          body="Cuando una petición de eMuwarez coincida con algo de tu biblioteca, aparecerá aquí con lo que paga."
        />
      ) : (
        <ul className="panel-lista">
          {peticiones.map(item => (
            <Fila key={item.rec_request_id ?? item.id} item={item} onVerFicha={onVerFicha} seleccion={seleccion}
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
                  <Fila key={item.id} item={item} onVerFicha={onVerFicha} seleccion={seleccion}
                    accion={<button type="button" className="btn btn-secondary btn-sm" onClick={() => onSubirUnico(item)}>Subir</button>} />
                ))}
              </ul>
            </>
          )}
          {mejoras.length > 0 && (
            <>
              <div className="upload-panel-group">Mejoras posibles: ya está en eMuwarez, pero tu copia aporta</div>
              <ul className="panel-lista">
                {mejoras.map(item => (
                  <Fila key={item.id} item={item} onVerFicha={onVerFicha} seleccion={seleccion}
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
