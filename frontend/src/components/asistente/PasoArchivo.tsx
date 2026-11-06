// Paso 1 de una película o un capítulo (uno o varios): los campos de la
// nomenclatura con la vista previa del nombre, y MediaInfo y pistas del archivo.
import { esTanda } from '../../utils/seleccionSubida'
import { listDisplayTitle } from '../../utils/libraryItem'
import { normalizarModo, renombra, tocaElFichero } from '../../utils/modoPistas'
import { FitText } from '../FitText'
import { IconoAviso } from '../Iconos'
import { SourceComparisonModal } from '../SourceComparisonModal'
import { FIELD_INFO, INTERNAL_TITLE_LABEL } from './constantes'
import { MediaInfoTable } from './MediaInfoTable'
import { AvisoSubidaExistente, BotonComparacionSource, CampoTag, FieldLabel, GeneratingHint, MarcoPaso, TableLoadingSpinner } from './piezas'
import { Pestanas, type Pestana } from './Pestanas'
import { AvisoModoPistas, RemuxTable } from './RemuxTable'
import type { Asistente, PestanaArchivo } from './useAsistente'

export function PasoArchivo({ a }: { a: Asistente }) {
  const {
    seleccion, targetId, episodeQueue, episodes, needsSelection, existingJob, existingJobBlocking,
    episodePrepping, episodePrepIndex, loading, error, reintentarNomenclatura,
    fields, setField, titleOptions, titleWarning, sources, providers, opcionesTag, detectingProvider,
    sourceRequiresProvider, sourceWarning, avisoSource, audioWarning, preview,
    sourceComparison, showSourceCompare, setShowSourceCompare, showEngineDetail, setShowEngineDetail,
    pestana, elegirPestana, miReport, miLoading, miError, runMediaInfo,
    remuxPreview, remuxLoading, remuxError, remuxEdits, runTrackRemux,
    setRemuxEdit, elegirIdioma, cambiarElemento, setStep, goToUpload, preparing, recalculandoIdioma,
  } = a

  const fieldBox = (
    <>
      <div className="asist-rejilla-campos">
        <label><FieldLabel label="Título" info={FIELD_INFO.title} />
          {/* Spanish by default (it leads title_options), original as the
              alternative. Falls back to the old read-only input when the
              backend couldn't offer a choice at all, so the field never
              silently turns into an empty select. */}
          {titleOptions.length > 0 ? (
            <select
              className="form-input form-select"
              value={fields.title || ''}
              onChange={e => setField('title', e.target.value)}
              disabled={titleOptions.length < 2}
            >
              {titleOptions.map(o => (
                <option key={o.value} value={o.value}>{o.label}: {o.value}</option>
              ))}
            </select>
          ) : (
            <input className="form-input" value={fields.title || ''} disabled />
          )}
          {titleWarning && (
            <span className="asist-aviso-campo"><IconoAviso /> {titleWarning}</span>
          )}
        </label>
        <label><FieldLabel label="Año" info={FIELD_INFO.year} />
          <input className="form-input" value={fields.year || ''} disabled />
        </label>
        {fields.season_episode != null && (
          <label><FieldLabel label="Temporada / Episodio" info={FIELD_INFO.season_episode} />
            {/* Read-only like every other derived field here (Año, Resolución,
                códecs): it comes straight from Sonarr's season/episode numbers
                for THIS file. Editing it let you name a file S03E07 when it is
                actually S01E02, and the upload renames the real file to
                whatever this says — a typo here mislabels the release and the
                file on disk. Only Source, Proveedor and Tag are meant to be
                editable, and those are genuine judgement calls. */}
            <input className="form-input" value={fields.season_episode || ''} disabled />
          </label>
        )}
        <label><FieldLabel label="Resolución" info={FIELD_INFO.resolution} />
          <input className="form-input" value={fields.resolution || ''} disabled />
        </label>
        <label><FieldLabel label="Source" info={FIELD_INFO.source} />
          <div className="asist-fila-source">
            <select className="form-input form-select asist-crece" value={fields.source || ''} onChange={e => setField('source', e.target.value)}>
              <option value="">— Seleccionar —</option>
              {sources.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}
            </select>
            {sourceComparison && (
              <BotonComparacionSource
                comparison={sourceComparison}
                onClick={() => { setShowEngineDetail(false); setShowSourceCompare(v => !v) }}
              />
            )}
          </div>
          {sourceWarning && (
            <span className="asist-aviso-campo"><IconoAviso /> {sourceWarning}</span>
          )}
          {avisoSource && (
            <span className="asist-aviso-campo"><IconoAviso /> {avisoSource}</span>
          )}
        </label>
        {sourceRequiresProvider && (
          <label><FieldLabel label="Proveedor" info={FIELD_INFO.provider} />
            {detectingProvider ? (
              <div className="form-input asist-detectando">
                <span className="spinner asist-spinner-12" /> Detectando…
              </div>
            ) : (
              <select className="form-input form-select" value={fields.provider || ''} onChange={e => setField('provider', e.target.value || null)}>
                <option value="">— Sin proveedor —</option>
                {providers.map(p => <option key={p.code} value={p.code}>{p.name} ({p.code})</option>)}
              </select>
            )}
          </label>
        )}
        <label><FieldLabel label="Códec de vídeo" info={FIELD_INFO.video_codec} />
          <input className="form-input" value={fields.video_codec || ''} disabled />
        </label>
        <label><FieldLabel label="Audio" info={FIELD_INFO.audio} />
          <input className="form-input" value={fields.audio_summary || ''} disabled />
          {audioWarning && (
            <span className="asist-aviso-campo"><IconoAviso /> {audioWarning}</span>
          )}
        </label>
        <label><FieldLabel label="Subtítulos" info={FIELD_INFO.subs} />
          <input className="form-input" value={fields.subs || ''} disabled />
        </label>
        <CampoTag value={fields.tag} opciones={opcionesTag} onChange={t => setField('tag', t)} />
      </div>
      <div className="asist-mt-16">
        <div className="asist-etiqueta">{INTERNAL_TITLE_LABEL}</div>
        {preview?.internal_mkv_title ? <FitText min={9} text={preview.internal_mkv_title} /> : <GeneratingHint />}
      </div>
    </>
  )


  // Las pistas de audio sin idioma esperan una elección: la pestaña lo dice sin abrirla.
  const sinIdioma = (remuxPreview?.ordered_tracks ?? []).filter(t => t.type === 'audio' && t.sin_idioma && !remuxEdits[t.id]?.language).length
  const pestanas: Pestana<PestanaArchivo>[] = [
    { id: 'nomenclatura', etiqueta: 'Nomenclatura' },
    { id: 'pistas', etiqueta: 'Pistas', aviso: sinIdioma > 0 ? `${sinIdioma} sin idioma` : undefined },
    { id: 'mediainfo', etiqueta: 'MediaInfo' },
  ]
  const listo = !loading && !error && !episodePrepping
  const enTanda = esTanda(seleccion)

  return (
    <MarcoPaso
      pie={<>
        {needsSelection
          ? <button className="btn btn-secondary" type="button" onClick={() => setStep(0)}>Volver a la selección</button>
          : <span />}
        <button className="btn btn-primary" type="button" onClick={goToUpload} disabled={!listo || preparing || recalculandoIdioma || !preview || existingJobBlocking}>
          {preparing ? 'Preparando…' : 'Continuar'}
        </button>
      </>}
    >
      {episodeQueue.length > 1 && (
        <div className="asist-selector-fila">
          <select
            className="form-input form-select asist-select-auto"
            aria-label="Capítulo"
            value={targetId ?? ''} onChange={e => cambiarElemento(Number(e.target.value))}
            disabled={episodePrepping}
          >
            {/* Canonical "Serie (Año) - SxxExx", same format the rest
                of the app uses for an episode. */}
            {episodeQueue.map(id => {
              const ep = episodes.find(x => x.id === id)
              return <option key={id} value={id}>{ep ? listDisplayTitle(ep) : id}</option>
            })}
          </select>
        </div>
      )}
      <AvisoSubidaExistente job={existingJob} bloquea={existingJobBlocking} />
      {episodePrepping && (
        <div className="asist-espera">
          <span className="spinner asist-spinner-28" />
          <div className="asist-espera-titulo">Generando Nomenclatura para eMuwarez…</div>
          <div className="asist-t125 text-muted">
            Capítulo {Math.min(episodePrepIndex + 1, episodeQueue.length)} de {episodeQueue.length}
            {(() => {
              const ep = episodes.find(x => x.id === episodeQueue[episodePrepIndex])
              return ep ? `: ${listDisplayTitle(ep)}` : ''
            })()}
          </div>
        </div>
      )}
      {loading && !episodePrepping && (
        <div className="asist-espera">
          <span className="spinner asist-spinner-28" />
          <div className="asist-espera-titulo">Generando Nomenclatura para eMuwarez…</div>
        </div>
      )}
      {error && !loading && !episodePrepping && (
        <div className="asist-bloque-error">
          <p className="text-error asist-mt-0 asist-mb-10"><IconoAviso /> {error}</p>
          <button className="btn btn-secondary btn-sm" type="button" onClick={reintentarNomenclatura}>↻ Reintentar</button>
        </div>
      )}
      {listo && (
        <>
          {/* El nombre que saldrá, a la vista en las tres pestañas: lo que se cambie en cualquiera lo mueve. */}
          <div className="detail-card asist-tarjeta">
            <div className="asist-etiqueta">Nombre final del torrent (eMuwarez)</div>
            {preview?.torrent_name ? <FitText min={9} text={preview.torrent_name} /> : <GeneratingHint />}
          </div>

          <Pestanas nombre="Detalle del archivo" pestanas={pestanas} activa={pestana} onCambiar={elegirPestana}>
            {pestana === 'nomenclatura' && (
              <>
                <p className="text-muted asist-t12 asist-mt-0 asist-mb-12">
                  El título y el año vienen de Radarr/Sonarr, el Source y el Proveedor del nombre del archivo, y el resto
                  se lee con MediaInfo del archivo real. Puedes ajustar los campos editables.
                </p>
                {fieldBox}
              </>
            )}

            {pestana === 'pistas' && (
              <>
                <div className="asist-fila-titulo-pestana">
                  <AvisoModoPistas plan={remuxPreview} />
                </div>
                {remuxLoading && !remuxPreview && <TableLoadingSpinner label="Cargando pistas del archivo…" />}
                {remuxError && !remuxLoading && (
                  <>
                    <p className="text-error asist-t12 asist-mt-0 asist-mb-10">✗ {remuxError}</p>
                    <button className="btn btn-secondary btn-sm" type="button" onClick={runTrackRemux}>↻ Reintentar</button>
                  </>
                )}
                {/* Editable solo si el modo renombra: sin eso la
                    columna ofrece escribir un nombre que no se va a
                    aplicar. Lo decide Configuración → Otros, no una
                    casilla aquí: la casilla solo salía subiendo una
                    película o un capítulo suelto, nunca en una
                    temporada entera. */}
                {remuxPreview && (
                  <>
                    {/* En una tanda "Subir todos" no lleva las ediciones: se
                        enseñan las pistas pero no se pueden tocar. */}
                    {enTanda && (
                      <p className="text-muted asist-t12 asist-mt-0">
                        Al subir varios capítulos a la vez se aplican los nombres automáticos. Para cambiarlos, sube el capítulo suelto.
                      </p>
                    )}
                    <RemuxTable
                      plan={remuxPreview}
                      editable={!enTanda && tocaElFichero(normalizarModo(remuxPreview.track_mode))}
                      nameEditable={!enTanda && renombra(normalizarModo(remuxPreview.track_mode))}
                      edits={remuxEdits}
                      onEdit={setRemuxEdit}
                      onIdioma={enTanda ? undefined : elegirIdioma}
                    />
                  </>
                )}
              </>
            )}

            {pestana === 'mediainfo' && (
              <>
                {miLoading && !miReport && <TableLoadingSpinner label="Cargando MediaInfo…" />}
                {miError && !miLoading && (
                  <>
                    <p className="text-error asist-t12 asist-mt-0 asist-mb-10">✗ {miError}</p>
                    <button className="btn btn-secondary btn-sm" type="button" onClick={runMediaInfo}>↻ Reintentar</button>
                  </>
                )}
                {miReport && (
                  <MediaInfoTable
                    report={miReport}
                    onSourceToolClick={sourceComparison ? () => { setShowEngineDetail(true); setShowSourceCompare(true) } : undefined}
                  />
                )}
              </>
            )}
          </Pestanas>
        </>
      )}
      {/* Fuera de las pestañas: se abre igual desde el botón de Source (Nomenclatura) que desde MediaInfo. */}
      {showSourceCompare && sourceComparison && (
        <SourceComparisonModal
          comparison={sourceComparison}
          initialShowDetail={showEngineDetail}
          onClose={() => setShowSourceCompare(false)}
        />
      )}
    </MarcoPaso>
  )
}
