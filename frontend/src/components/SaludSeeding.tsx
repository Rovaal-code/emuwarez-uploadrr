import { useEffect } from 'react'
import type { UploadJob } from '../types/api'
import type { SeedingEstado } from '../hooks/useSeeding'
import { formatDateTimeSeconds, formatNumero } from '../utils/format'
import { SIN_DATOS_QBIT, claseSeeding, resumenSeeding, seedingDe, textoSubido } from '../utils/seeding'

// Solo la subida completada tiene ya su torrent sembrando; las demás no llegaron a subir o están en ello.
const tieneTorrent = (job: UploadJob) => job.status === 'completed'

// La columna «Seeding» de la lista de Subidas.
export function SeedingCelda({ job, seeding }: { job: UploadJob; seeding: SeedingEstado }) {
  if (!tieneTorrent(job)) return <span className="sub-muted">—</span>
  if (!seeding.datos) return <span className="sub-muted sub-t11">{seeding.cargando ? 'Cargando…' : SIN_DATOS_QBIT}</span>
  if (!seeding.datos.disponible) return <span className="sub-muted sub-t11">{SIN_DATOS_QBIT}</span>
  const i = seedingDe(seeding.datos, job.id)
  if (!i) return <span className="sub-muted">—</span>
  return <span className={claseSeeding(i.estado)}>{resumenSeeding(i)}</span>
}

// El bloque completo del detalle de una subida. Pide los datos al entrar (la caché del servidor evita machacar
// a qBittorrent) y «Actualizar» se salta esa caché.
export function SeedingBloque({ job, seeding }: { job: UploadJob; seeding: SeedingEstado }) {
  const { datos, cargando, cargar } = seeding
  const aplica = tieneTorrent(job)
  useEffect(() => { if (aplica) cargar() }, [aplica, cargar])
  if (!aplica) return null
  const i = seedingDe(datos, job.id)
  const sinDatos = !datos || !datos.disponible
  return (
    <div className="dsub-panel" data-testid="seeding-bloque">
      <h2 className="dsub-panel-titulo">
        Seeding en qBittorrent
        {cargando && <span className="spinner dsub-spinner-13" />}
      </h2>
      <div className="detail-card dsub-caja seeding-caja">
        {sinDatos ? (
          <div className="seeding-sin-datos">
            <strong>{SIN_DATOS_QBIT}</strong>
            <span className="sub-muted sub-t12">
              {datos?.mensaje ?? (cargando ? 'Consultando…' : 'No se pudo consultar. Esto no afecta a la subida.')}
            </span>
          </div>
        ) : !i ? (
          <div className="seeding-sin-datos">
            <span className={claseSeeding('no_encontrado')}>No se encuentra</span>
            <span className="sub-muted sub-t12">
              No hay un torrent único en qBittorrent que corresponda a esta subida
              (puede haberse borrado, estar en otra ruta o haber varios iguales).
            </span>
          </div>
        ) : (
          <dl className="seeding-datos">
            <div><dt>Estado</dt><dd><span className={claseSeeding(i.estado)}>{i.etiqueta}</span></dd></div>
            <div><dt>Ratio</dt><dd>{formatNumero(i.ratio, 2)}</dd></div>
            <div><dt>Subido</dt><dd>{textoSubido(i)}</dd></div>
            <div><dt>Progreso</dt><dd>{i.progreso != null ? `${formatNumero(i.progreso * 100, 1)} %` : '—'}</dd></div>
            <div><dt>Seeds / peers</dt><dd>{formatNumero(i.seeds)} / {formatNumero(i.peers)}</dd></div>
          </dl>
        )}
        {i?.estado === 'faltan_ficheros' && (
          <p className="seeding-aviso">
            qBittorrent no encuentra todos los ficheros de este torrent: comprueba que la carpeta de subidas
            sigue en su sitio y que qBittorrent la ve en la misma ruta.
          </p>
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
