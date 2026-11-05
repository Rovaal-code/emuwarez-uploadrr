import { formatNumero } from '../../utils/format'
import { MAX_ELEMENTOS_LOTE } from '../../utils/lote'

/**
 * El pie de la selección para «Subir por lotes»: cuántas hay marcadas (y cuántas de ellas no se ven con el filtro
 * de ahora), «Subir por lotes» y «Limpiar». Va en el flujo de la página, no fija: una barra fija taparía el pie
 * de la barra lateral, y el body tiene zoom (utils/uiScale). El Panel la pone al pie de «Listo para subir» con su
 * propio texto («Subir seleccionadas (N)»).
 */
export function BarraLote({
  total, ocultas = 0, onSubir, onLimpiar, vacia = 'Marca las películas, series o temporadas que quieras subir juntas',
  textoSubir = 'Subir por lotes', className,
}: {
  total: number
  ocultas?: number
  onSubir: () => void
  onLimpiar: () => void
  // Lo que dice sin nada marcado.
  vacia?: string
  textoSubir?: string
  className?: string
}) {
  return (
    <div className={className ? `lote-barra ${className}` : 'lote-barra'} role="region" aria-label="Selección para subir por lotes">
      <span className="lote-barra-cuenta" role="status">
        {total === 0
          ? vacia
          : `${formatNumero(total)} ${total === 1 ? 'seleccionada' : 'seleccionadas'}`}
        {ocultas > 0 && <span className="text-muted"> ({formatNumero(ocultas)} {ocultas === 1 ? 'oculta' : 'ocultas'} por el filtro)</span>}
        {total >= MAX_ELEMENTOS_LOTE && <span className="lote-aviso"> · tope de {MAX_ELEMENTOS_LOTE} por lote</span>}
      </span>
      <div className="lote-barra-botones">
        <button type="button" className="btn btn-primary btn-sm" onClick={onSubir} disabled={total === 0}>
          {textoSubir}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onLimpiar} disabled={total === 0}>
          Limpiar
        </button>
      </div>
    </div>
  )
}
