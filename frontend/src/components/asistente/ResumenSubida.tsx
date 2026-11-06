// El paso Resumen: lo que se va a mandar a eMuwarez y lo que el catálogo local ya tiene de lo mismo. Es la última
// ocasión de ver una categoría, una pista o un duplicado equivocados, y sirve igual para una película, un pack
// y una tanda de temporadas o capítulos.
import { useId } from 'react'
import { timeAgo } from '../../utils/format'
import { peticionCubre } from '../../utils/seleccionSubida'
import {
  conclusionDuplicados, textoCategoria, textoCopia, textoFicheros, textoPistas, tipoDeEnlace, type FilaYaHay, type YaHay,
} from '../../utils/resumenSubida'
import { mergeRemuxTracks } from './RemuxTable'
import type { Asistente } from './useAsistente'
import { useResumen } from './useResumen'

const ALCANCE: Record<string, string> = { movie: 'esta película', season: 'esta temporada', episode: 'este capítulo' }

export function ResumenSubida({ a }: { a: Asistente }) {
  const {
    item, seasons, episodes, targetId, targetIsSeason, batchQueue, batchIsEpisodes, batchItemTitle,
    preview, seasonDisplayTitle, seasonPlan, fields, remuxPreview, remuxEdits, modoPistasAjuste,
    checks, batchContentChecks, nombresTanda, requestId, preselect,
  } = a
  const esTanda = batchQueue.length > 1
  const ids = esTanda ? batchQueue : targetId != null ? [targetId] : []
  const fila = (id: number) => [item, ...seasons, ...episodes].find(x => x.id === id)
  const filas = ids.map(fila)
  const objetivo = filas[0]
  const tipo = objetivo?.item_type ?? item.item_type
  const cubiertos = esTanda
    ? filas.filter(f => !f || peticionCubre(preselect, f)).length
    : requestId != null ? 1 : 0

  const { yaHay, sincronizado, peticion } = useResumen({
    ids, requestId, cubiertos,
    // Un fichero o un pack: lo que irá en el nombre; una tanda lleva el de cada elemento.
    tuya: esTanda ? undefined : { resolution: fields.resolution, source: fields.source },
    alcance: esTanda ? null : ALCANCE[tipo] ?? 'este contenido',
  })

  // Pistas: con un fichero suelto, las del plan y lo editado a mano; en un pack o una tanda, el ajuste.
  const pistasDelFichero = !esTanda && !targetIsSeason && remuxPreview
  const aMano = Object.keys(remuxEdits).length
  const cambian = pistasDelFichero
    ? mergeRemuxTracks(remuxPreview, remuxEdits).filter(t => t.changed || remuxEdits[t.id]).length
    : null
  const modo = pistasDelFichero ? remuxPreview.track_mode : modoPistasAjuste
  const enlace = tipoDeEnlace(esTanda ? [...batchContentChecks.values()].flatMap(c => c.checks) : checks?.checks)
  const copia = textoCopia(enlace, modo)

  const nombre = targetIsSeason ? seasonDisplayTitle : preview?.torrent_name
  // El nombre del torrent de cada elemento de una tanda: el de un pack lo dan sus comprobaciones, el de un capítulo
  // su nomenclatura. undefined mientras se calcula; null si no hay (comprobación fallida o nomenclatura bloqueada).
  const nombreDeLaTanda = (id: number): string | null | undefined => {
    if (batchIsEpisodes) return nombresTanda.get(id)
    const c = batchContentChecks.get(id)
    return c ? c.nombre ?? null : undefined
  }
  const idTitulo = useId()
  const idYaHay = useId()
  return (
    <div className="asist-resumen">
      <section className="detail-card asist-panel" aria-labelledby={idTitulo}>
        <h3 className="asist-panel-titulo" id={idTitulo}>Lo que se sube</h3>
        {esTanda ? (
          <ul className="asist-lista-subida">
            {batchQueue.map(id => (
              <li key={id}>
                <span className="asist-lista-titulo">{batchItemTitle(id)}</span>
                <NombreDeLaTanda nombre={nombreDeLaTanda(id)} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="asist-nombre-torrent" translate="no">{nombre || '—'}</p>
        )}
        <dl className="asist-datos">
          <dt>Ficheros</dt>
          <dd>{textoFicheros({
            esPack: targetIsSeason && !esTanda, capitulosEnPack: seasonPlan?.episodes.length,
            elementos: esTanda ? batchQueue.length : 1, capitulos: batchIsEpisodes,
            bytes: filas.reduce((suma, f) => suma + (f?.size_bytes ?? 0), 0) || null,
          })}</dd>
          <dt>Categoría</dt>
          <dd>{textoCategoria(tipo !== 'movie', esTanda ? null : fields.source, esTanda ? null : fields.resolution)}</dd>
          <dt>Petición</dt>
          <dd className={peticion?.aviso ? 'asist-aviso-dato' : undefined}>{peticion?.texto ?? '…'}</dd>
          <dt>Pistas</dt>
          <dd>{textoPistas(modo, cambian, pistasDelFichero ? aMano : 0)}</dd>
          <dt>Copia</dt>
          <dd>
            {copia.texto}
            {copia.nota && <span className="asist-dato-nota">{copia.nota}</span>}
          </dd>
        </dl>
      </section>

      <section className="detail-card asist-panel" aria-labelledby={idYaHay}>
        <h3 className="asist-panel-titulo" id={idYaHay}>En eMuwarez ya hay</h3>
        <YaHayEnEmu yaHay={yaHay} />
        {yaHay.estado === 'listo' && (
          <p className="asist-nota-catalogo">
            Del catálogo local, sincronizado {timeAgo(sincronizado)}. No cuenta como permiso: revisa las reglas de trumps.
          </p>
        )}
      </section>
    </div>
  )
}

// El nombre del torrent de un elemento de la tanda, bajo su título.
export function NombreDeLaTanda({ nombre }: { nombre: string | null | undefined }) {
  if (nombre === undefined) return <span className="asist-lista-nombre asist-lista-espera">Calculando el nombre…</span>
  if (nombre === null) return <span className="asist-lista-nombre asist-aviso-dato">Sin nombre: este elemento no se podrá subir</span>
  return <span className="asist-lista-nombre" translate="no">{nombre}</span>
}

function YaHayEnEmu({ yaHay }: { yaHay: YaHay }) {
  if (yaHay.estado === 'cargando') {
    return <p className="asist-t12 text-muted"><span className="spinner asist-spinner-12" /> Mirando el catálogo local…</p>
  }
  if (yaHay.estado === 'error') return <p className="asist-t13">No se pudo leer el catálogo local.</p>
  if (yaHay.estado === 'sin-catalogo') {
    return <p className="asist-t13">Sin catálogo local: sincroniza con eMuwarez para saber si ya está.</p>
  }
  const { filas, sinNada, total } = yaHay
  const conclusion = conclusionDuplicados(filas)
  return (
    <>
      {filas.length === 0 ? (
        <p className="asist-t13">Nada de esto está en eMuwarez todavía.</p>
      ) : (
        <>
        {conclusion && (
          <p className={`asist-t13${conclusion.clase ? ` asist-veredicto asist-veredicto-${conclusion.clase}` : ''}`}
            role="status" data-testid="conclusion-duplicados">
            {conclusion.texto}
          </p>
        )}
        <div className="asist-tabla-caja asist-tabla-caja-yahay">
          <table className="asist-tabla asist-tabla-yahay">
            <caption className="solo-lector">Torrents de eMuwarez del mismo contenido</caption>
            <thead>
              <tr>
                <th className="asist-th" scope="col">Torrent</th>
                <th className="asist-th" scope="col">Calidad</th>
                <th className="asist-th" scope="col">Lo tuyo</th>
              </tr>
            </thead>
            <tbody>
              {filas.map(f => <FilaDuplicado key={f.clave} f={f} />)}
            </tbody>
          </table>
        </div>
        </>
      )}
      {total > 1 && sinNada > 0 && (
        <p className="asist-t12 text-muted asist-mt-10">{sinNada} de {total} no están en eMuwarez.</p>
      )}
    </>
  )
}

function FilaDuplicado({ f }: { f: FilaYaHay }) {
  return (
    <tr className="asist-fila">
      <td className="asist-celda-yahay asist-romper">{f.nombre}</td>
      <td className="asist-celda-yahay asist-sin-salto">{f.calidad || '—'}</td>
      <td className={`asist-celda-yahay asist-veredicto${f.veredicto ? ` asist-veredicto-${f.veredicto}` : ''}`}>
        {f.veredicto ?? '—'}
      </td>
    </tr>
  )
}
