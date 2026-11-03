import type { UploadJob } from '../../types/api'
import { lineaDeTiempo } from '../../utils/lineaDeTiempo'
import { formatSecondsHM } from '../../utils/uploadStatus'

// Cuánto tardó cada fase de una subida terminada. La barra es proporcional al total y el tiempo va siempre en
// texto, así que no depende del color. Una fase sin marcas de tiempo enseña solo su estado.
export function DondeSeFueElTiempo({ job }: { job: UploadJob }) {
  const { tramos, totalSegundos } = lineaDeTiempo(job)
  if (tramos.length === 0 && totalSegundos == null) return null
  const mayor = tramos.reduce<number | null>((m, t) => (t.segundos != null && t.segundos > 0 && (m == null || t.segundos > m) ? t.segundos : m), null)
  return (
    <section className="dsub-panel dsub-tiempo" aria-labelledby="dsub-tiempo-titulo">
      <h2 id="dsub-tiempo-titulo" className="dsub-panel-titulo">
        Dónde se fue el tiempo
        {totalSegundos != null && <span className="dsub-tiempo-total">Total <strong>{formatSecondsHM(totalSegundos)}</strong></span>}
      </h2>
      <div className="detail-card dsub-caja">
        <ol className="dsub-tramos">
          {tramos.map(t => (
            <li key={t.clave} className={t.segundos != null && t.segundos === mayor ? 'dsub-tramo dsub-tramo-mayor' : 'dsub-tramo'}>
              <span className="dsub-tramo-nombre">{t.nombre}</span>
              <span className="dsub-tramo-pista" aria-hidden="true">
                {t.fraccion > 0 && <span className="dsub-tramo-barra" style={{ width: `${Math.max(t.fraccion * 100, 0.6)}%` }} />}
              </span>
              <span className="dsub-tramo-valor">{t.segundos != null ? formatSecondsHM(t.segundos) : t.estado}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
