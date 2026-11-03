import type { RequestItemResponse } from '../types/api'
import { useTooltip } from './Tooltip'
import { DetailTitleText, PlainValue, PointsValueIcon } from './DetailCard'
import { formatNumero } from '../utils/format'
import { requestDisplayTitle } from '../utils/peticiones'

// El carril «Peticiones listas para subir» del Panel: las peticiones que la
// preparación ya da por listas (`ready_to_upload`, el mismo criterio que la
// columna de Peticiones y el aviso `request_new_ready`), la de más recompensa
// primero, para ver de un vistazo cuál conviene subir antes. El orden y el
// tope los pone el servidor (GET /api/requests?readiness=…&sort=points_desc);
// aquí solo se pintan en ese orden.

/** La preparación que cuenta como «lista para subir» (request_readiness.py). */
export const LISTA_PARA_SUBIR = 'ready_to_upload'
/** Cuántas caben en el carril: una fila, sin desplazarse (tres con la interfaz estrecha). */
export const CARRIL_LISTAS_MAX = 5

function FilaLista({ item, onOpen }: { item: RequestItemResponse; onOpen: (id: number) => void }) {
  const titulo = requestDisplayTitle(item)
  // El título se corta con puntos suspensivos: el tooltip lo da entero.
  const { triggerProps, tooltipNode } = useTooltip(`Ver petición: ${titulo}`)
  const recompensa = item.points == null ? 'sin dato' : `${formatNumero(item.points)} puntos`
  return (
    // Una sola línea y sin póster: el carril va encima de Recomendaciones y
    // cada píxel que ocupa se lo quita a ella.
    <button type="button" className="panel-listas-fila" onClick={() => onOpen(item.id)}
      aria-label={`${titulo}. Recompensa: ${recompensa}`} {...triggerProps}>
      <span className="panel-listas-titulo"><DetailTitleText title={titulo} /></span>
      <span className="panel-listas-recompensa">
        <PlainValue icon={<PointsValueIcon />}>{formatNumero(item.points)}</PlainValue>
      </span>
      {tooltipNode}
    </button>
  )
}

/** Sin peticiones listas no se pinta nada: como el resto del Panel, no deja una caja vacía a la vista. */
export function CarrilPeticionesListas({ items, total, onOpen }: {
  items: RequestItemResponse[]
  /** Cuántas listas hay en total, aunque el carril enseñe solo las primeras. */
  total: number
  onOpen: (requestId: number) => void
}) {
  if (items.length === 0) return null
  const visibles = items.slice(0, CARRIL_LISTAS_MAX)
  return (
    <section className="activity-section panel-listas" aria-labelledby="panel-listas-titulo">
      <div className="section-header">
        <div className="section-title" id="panel-listas-titulo">Peticiones listas para subir</div>
        {/* Siempre: con la interfaz estrecha caben tres (panel.css), y así no
            hay que adivinar cuántas se ven para decir si hay más. */}
        <span className="panel-ver-todas">{total === 1 ? '1 lista' : `${formatNumero(total)} listas`}</span>
      </div>
      <ol className="panel-listas-carril">
        {visibles.map(item => <li key={item.id}><FilaLista item={item} onOpen={onOpen} /></li>)}
      </ol>
    </section>
  )
}
