import type { PeticionDeLaFicha } from '../types/api'
import { StatusBadge } from './StatusBadge'
import { PlainValue, PointsValueIcon } from './DetailCard'
import { Favicon } from './Favicon'
import { useTooltip } from './Tooltip'
import { formatNumero, SIN_DATO } from '../utils/format'
import { requestDisplayTitle } from '../utils/peticiones'
import { getRequestStatusInfo } from '../utils/status'

// El valor de la fila «Petición» de la ficha de Biblioteca: el estado guardado
// y, si hay petición, quién la pidió, la recompensa, un enlace a su ficha en
// Peticiones y otro a su página en eMuwarez. Sin petición queda solo la
// insignia, como siempre.
//
// Una temporada o un capítulo sin petición propia enseñan la de su temporada o
// su serie cuando esta los cubre (la de la serie entera, p. ej.), dicho así
// para no confundirla con una propia: su estado guardado sigue siendo «Sin
// petición», que es lo que filtra la lista. En una serie o una temporada se
// listan además las peticiones de sus temporadas o capítulos.

const EMU_DOMINIO = 'emu-warez.com'
/** Cuántas peticiones de debajo se enseñan; el resto se cuenta. */
export const DEBAJO_MAX = 4

/** «Temporada 2» o «S01E04»; null para la serie entera. */
export function alcanceDePeticion(p: Pick<PeticionDeLaFicha, 'req_scope' | 'req_season' | 'req_episode'>): string | null {
  if (p.req_season == null) return null
  if (p.req_scope === 'episode' && p.req_episode != null) {
    return `S${String(p.req_season).padStart(2, '0')}E${String(p.req_episode).padStart(2, '0')}`
  }
  return `Temporada ${p.req_season}`
}

function tituloDe(p: PeticionDeLaFicha): string {
  return requestDisplayTitle({ ...p, title: p.title ?? '', library_year: null })
}

function EnlaceEmu({ p }: { p: PeticionDeLaFicha }) {
  const tip = useTooltip(p.url ? 'Abrir la petición en eMuwarez' : null)
  if (!p.url) return null
  return (
    <a className="hover-link bibdet-pet-emu" href={p.url} target="_blank" rel="noreferrer"
      aria-label={`Abrir la petición en eMuwarez: ${tituloDe(p)}`} {...tip.triggerProps}>
      <Favicon domain={EMU_DOMINIO} size={16} radius={3} fallback={<span aria-hidden="true">↗</span>} />
      {tip.tooltipNode}
    </a>
  )
}

function VerPeticion({ p, onAbrir, children }: {
  p: PeticionDeLaFicha
  onAbrir: (id: number) => void
  children: React.ReactNode
}) {
  const tip = useTooltip(`Ver petición: ${tituloDe(p)}`)
  return (
    <button type="button" className="hover-link bibdet-pet-ver" onClick={() => onAbrir(p.id)} {...tip.triggerProps}>
      {children}{tip.tooltipNode}
    </button>
  )
}

function Autor({ p }: { p: PeticionDeLaFicha }) {
  if (!p.author) return null
  return (
    <span className="bibdet-pet-autor">
      de <span className={p.is_mine ? 'bibdet-pet-mio' : undefined}>{p.author}{p.is_mine ? ' (Yo)' : ''}</span>
    </span>
  )
}

function Datos({ p, onAbrir }: { p: PeticionDeLaFicha; onAbrir?: (id: number) => void }) {
  return (
    // Dos grupos: quién y cuánto, y los dos enlaces, que no se separan. En la
    // tarjeta estrecha cada grupo va en su línea; si cabe, en una sola.
    <span className="bibdet-pet-datos">
      {(p.author || p.points != null) && (
        <span className="bibdet-pet-grupo">
          <Autor p={p} />
          {p.points != null && (
            <span className="bibdet-pet-puntos">
              <span className="solo-lector">Recompensa: </span>
              <PlainValue icon={<PointsValueIcon />}>{formatNumero(p.points)}</PlainValue>
              <span className="solo-lector"> puntos</span>
            </span>
          )}
        </span>
      )}
      {(onAbrir || p.url) && (
        <span className="bibdet-pet-grupo bibdet-pet-enlaces">
          {onAbrir && <VerPeticion p={p} onAbrir={onAbrir}>Ver petición</VerPeticion>}
          <EnlaceEmu p={p} />
        </span>
      )}
    </span>
  )
}

export function CampoPeticion({ itemType, requestStatus, peticion, onAbrirPeticion }: {
  itemType: string
  requestStatus: string
  peticion?: PeticionDeLaFicha | null
  onAbrirPeticion?: (id: number) => void
}) {
  if (!peticion) return <StatusBadge status={requestStatus} type="request" />

  const heredada = peticion.heredada_de
  // Una serie que guarda una petición de una temporada (no había fila para
  // ella): que diga de cuál, porque la insignia de la serie no lo dice.
  const alcance = !heredada && itemType === 'series' ? alcanceDePeticion(peticion) : null

  return (
    <span className="bibdet-pet">
      <span className="bibdet-pet-linea">
        {heredada && <span className="bibdet-pet-nota">Petición de la {heredada}</span>}
        {alcance && <span className="bibdet-pet-nota">{alcance}</span>}
        <StatusBadge status={heredada ? (peticion.estado ?? requestStatus) : requestStatus} type="request" />
      </span>
      <Datos p={peticion} onAbrir={onAbrirPeticion} />
    </span>
  )
}

// Las peticiones de las temporadas o capítulos de una serie o temporada (una
// serie con una petición por temporada): una línea por petición con su
// alcance, que la abre en Peticiones, y su estado. Va en su propia fila de la
// tarjeta, a todo lo ancho: en la columna del valor no cabían sin partirse.
export function PeticionesDebajo({ itemType, debajo, onAbrirPeticion }: {
  itemType: string
  debajo?: PeticionDeLaFicha[] | null
  onAbrirPeticion?: (id: number) => void
}) {
  const otras = debajo ?? []
  if (otras.length === 0) return null
  const visibles = otras.slice(0, DEBAJO_MAX)
  return (
    <div className="bibdet-pet-debajo">
      <span className="detcard-fila-etiqueta">
        {itemType === 'series' ? 'Peticiones de sus temporadas' : 'Peticiones de sus capítulos'}
      </span>
      <ul className="bibdet-pet-lista">
        {visibles.map(p => {
          const alcance = alcanceDePeticion(p) ?? 'Toda la serie'
          return (
            <li key={p.id}>
              {onAbrirPeticion ? <VerPeticion p={p} onAbrir={onAbrirPeticion}>{alcance}</VerPeticion> : <span>{alcance}</span>}
              <span className="bibdet-pet-nota">{p.estado ? getRequestStatusInfo(p.estado).label : SIN_DATO}</span>
            </li>
          )
        })}
      </ul>
      {otras.length > visibles.length && (
        <span className="bibdet-pet-nota">y {formatNumero(otras.length - visibles.length)} más</span>
      )}
    </div>
  )
}
