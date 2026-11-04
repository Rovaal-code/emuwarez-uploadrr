import { useCallback, useEffect, useRef, useState } from 'react'
import { getTrackerStats, type TrackerStats } from '../api/trackerStats'
import type { UploadJob } from '../types/api'
import { formatDateTimeSeconds, formatNumero } from '../utils/format'

// Solo la subida completada que llegó a eMuwarez tiene ficha (`result_tracker`) de la que pedir sus contadores.
const tieneFicha = (job: UploadJob) => job.status === 'completed' && !!job.result_tracker

// El bloque «En eMuwarez» del detalle de una subida: seeders, leechers y veces completado. Se pide al entrar y con
// «Actualizar», nunca por reloj: la clave de eMuwarez se comparte con Sonarr, Radarr y otras aplicaciones.
export function StatsTrackerBloque({ job }: { job: UploadJob }) {
  const aplica = tieneFicha(job)
  const [datos, setDatos] = useState<TrackerStats | null>(null)
  const [cargando, setCargando] = useState(false)
  const ultima = useRef(0)
  const vivo = useRef(true)

  const cargar = useCallback((forzar = false) => {
    if (job.id == null) return
    const n = ++ultima.current
    setCargando(true)
    getTrackerStats(job.id, forzar)
      .then(d => { if (vivo.current && n === ultima.current) setDatos(d) })
      .catch(() => { if (vivo.current && n === ultima.current) setDatos(null) })
      .finally(() => { if (vivo.current && n === ultima.current) setCargando(false) })
  }, [job.id])

  useEffect(() => {
    vivo.current = true
    if (aplica) cargar()
    return () => { vivo.current = false }
  }, [aplica, cargar])

  if (!aplica) return null
  const sinDatos = !datos || !datos.disponible
  return (
    <div className="dsub-panel" data-testid="stats-tracker">
      <h2 className="dsub-panel-titulo">
        En eMuwarez
        {cargando && <span className="spinner dsub-spinner-13" />}
      </h2>
      <div className="detail-card dsub-caja seeding-caja">
        {sinDatos ? (
          <div className="seeding-sin-datos">
            <strong>Sin datos de eMuwarez</strong>
            <span className="sub-muted sub-t12">
              {datos?.mensaje ?? (cargando ? 'Consultando…' : 'No se pudo consultar. Esto no afecta a la subida.')}
            </span>
          </div>
        ) : (
          <dl className="seeding-datos">
            <div><dt>Seeders</dt><dd>{formatNumero(datos.seeders)}</dd></div>
            <div><dt>Leechers</dt><dd>{formatNumero(datos.leechers)}</dd></div>
            <div><dt>Completado</dt><dd>{formatNumero(datos.completadas)} {datos.completadas === 1 ? 'vez' : 'veces'}</dd></div>
            {datos.freeleech && <div><dt>Freeleech</dt><dd>{datos.freeleech}</dd></div>}
            {datos.doble_subida && <div><dt>Subida</dt><dd>Doble</dd></div>}
          </dl>
        )}
        <div className="seeding-pie">
          <span className="sub-muted sub-t11">
            {datos?.actualizado ? `Leído ${formatDateTimeSeconds(datos.actualizado)}` : ''}
          </span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={cargando} onClick={() => cargar(true)}>
            Actualizar
          </button>
        </div>
      </div>
    </div>
  )
}
