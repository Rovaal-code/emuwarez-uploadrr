// Paso 1 de «Subir por lotes»: qué películas entran. Las que no se pueden subir (no están en disco, sin castellano)
// salen desmarcadas y sin casilla que marcar, con su motivo.
import type { LibraryItemResponse } from '../../types/api'
import { formatNumero } from '../../utils/format'
import { MAX_ELEMENTOS_LOTE, razonNoSubible } from '../../utils/lote'

const calidad = (item: LibraryItemResponse) => [item.resolution, item.source].filter(Boolean).join(' ')

export function PasoContenidoLote({ elementos, marcadas, onAlternar, onContinuar }: {
  elementos: readonly LibraryItemResponse[]
  marcadas: ReadonlySet<number>
  onAlternar: (id: number) => void
  onContinuar: () => void
}) {
  const n = elementos.filter(e => marcadas.has(e.id) && !razonNoSubible(e)).length
  const lleno = n >= MAX_ELEMENTOS_LOTE
  return (
    <div className="modal-body">
      <p className="lote-intro text-muted">
        Se subirán en este orden, con el nombre que genere la nomenclatura para cada una. Para cambiar un nombre o
        elegir pistas, súbela suelta.
      </p>
      <ul className="lote-lista">
        {elementos.map(item => {
          const razon = razonNoSubible(item)
          const marcada = !razon && marcadas.has(item.id)
          return (
            <li key={item.id} className={razon ? 'lote-fila lote-fila-apagada' : 'lote-fila'}>
              <label className="checkbox-label lote-fila-casilla">
                <input
                  type="checkbox"
                  checked={marcada}
                  disabled={!!razon || (!marcada && lleno)}
                  onChange={() => onAlternar(item.id)}
                />
                <span className="lote-fila-titulo">{item.title}{item.year ? ` (${item.year})` : ''}</span>
              </label>
              {calidad(item) && <span className="lote-fila-calidad">{calidad(item)}</span>}
              {razon && <span className="lote-motivo">{razon}</span>}
            </li>
          )
        })}
      </ul>
      <p className="lote-total" role="status">
        {formatNumero(n)} de {formatNumero(elementos.length)} {elementos.length === 1 ? 'marcada' : 'marcadas'} · máximo {MAX_ELEMENTOS_LOTE} por lote
      </p>
      <div className="asist-pie asist-pie-fin">
        <button className="btn btn-primary" type="button" onClick={onContinuar} disabled={n === 0}>
          Continuar ({n})
        </button>
      </div>
    </div>
  )
}
