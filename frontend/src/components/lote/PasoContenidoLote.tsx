// Paso 1 de «Subir por lotes»: qué entra. Cada serie marcada sale como sus temporadas (packs). Lo que no se puede
// subir (no está en disco, sin castellano, una temporada que no se puede subir como pack) sale desmarcado y sin
// casilla que marcar, con su motivo. Desde el Panel cada fila dice qué petición cubre y, si cubre varias (dos
// peticiones sobre el mismo elemento), deja elegir cuál se enlaza: el servidor solo enlaza una por subida.
import type { LibraryItemResponse } from '../../types/api'
import { formatNumero } from '../../utils/format'
import { listDisplayTitle } from '../../utils/libraryItem'
import { MAX_ELEMENTOS_LOTE, razonNoSubible } from '../../utils/lote'

const calidad = (item: LibraryItemResponse) => [item.resolution, item.source].filter(Boolean).join(' ')

const TIPO: Record<string, string> = { movie: 'Película', season: 'Temporada', episode: 'Capítulo' }

const NINGUNA: readonly number[] = []

export function PasoContenidoLote({
  elementos, marcadas, onAlternar, onContinuar, expandiendo = null, avisos = [], peticiones, peticionDe,
  onElegirPeticion,
}: {
  elementos: readonly LibraryItemResponse[]
  marcadas: ReadonlySet<number>
  onAlternar: (id: number) => void
  onContinuar: () => void
  // Mientras se cargan las temporadas de las series marcadas: cuántas series van de cuántas.
  expandiendo?: { hechas: number; series: number } | null
  // Una serie sin temporadas o que no se pudo cargar, o una petición cuya temporada o capítulo no está.
  avisos?: readonly string[]
  // Desde el Panel: las peticiones que cubre cada elemento, la que se enlaza y cómo elegir otra.
  peticiones?: ReadonlyMap<number, readonly number[]>
  peticionDe?: (id: number) => number | undefined
  onElegirPeticion?: (id: number, peticion: number) => void
}) {
  const n = elementos.filter(e => marcadas.has(e.id) && !razonNoSubible(e)).length
  const lleno = n >= MAX_ELEMENTOS_LOTE
  if (expandiendo) {
    return (
      <div className="modal-body">
        <p className="lote-cargando" role="status">
          <span className="spinner asist-spinner-14" /> Cargando las temporadas de las series marcadas
          ({formatNumero(Math.min(expandiendo.hechas + 1, expandiendo.series))} de {formatNumero(expandiendo.series)})…
        </p>
      </div>
    )
  }
  return (
    <div className="modal-body">
      <p className="lote-intro text-muted">
        Se subirán en este orden, con el nombre que genere la nomenclatura para cada una; una serie, como el pack de
        cada temporada. Para cambiar un nombre, elegir pistas o subir capítulos sueltos, súbela suelta.
      </p>
      {avisos.length > 0 && (
        <ul className="lote-motivos lote-avisos-expansion">{avisos.map(a => <li key={a}>{a}</li>)}</ul>
      )}
      <ul className="lote-lista">
        {elementos.map(item => {
          const razon = razonNoSubible(item)
          const marcada = !razon && marcadas.has(item.id)
          const suyas = peticiones?.get(item.id) ?? NINGUNA
          const enlazada = peticionDe?.(item.id) ?? suyas[0]
          return (
            <li key={item.id} className={razon ? 'lote-fila lote-fila-apagada' : 'lote-fila'}>
              <label className="checkbox-label lote-fila-casilla">
                <input
                  type="checkbox"
                  checked={marcada}
                  disabled={!!razon || (!marcada && lleno)}
                  onChange={() => onAlternar(item.id)}
                />
                <span className="lote-fila-titulo">{listDisplayTitle(item)}</span>
              </label>
              <span className="lote-fila-tipo">{TIPO[item.item_type] ?? item.item_type}</span>
              <span className="lote-fila-calidad">{calidad(item)}</span>
              {suyas.length === 1 && <span className="lote-fila-peticion">Petición #{suyas[0]}</span>}
              {suyas.length > 1 && (
                <select
                  className="form-input form-select lote-fila-peticion-elegir"
                  aria-label={`Petición que se enlaza con «${listDisplayTitle(item)}»`}
                  value={enlazada}
                  onChange={e => onElegirPeticion?.(item.id, Number(e.target.value))}
                >
                  {suyas.map(p => <option key={p} value={p}>Petición #{p}</option>)}
                </select>
              )}
              {razon && <span className="lote-motivo"><span aria-hidden="true">⚠ </span>{razon}</span>}
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
