// Paso 1 de una película o un capítulo (uno o varios): los campos de la
// nomenclatura con la vista previa del nombre, y MediaInfo y pistas del archivo.
import { esTanda } from '../../utils/seleccionSubida'
import { listDisplayTitle } from '../../utils/libraryItem'
import { normalizarModo, renombra, tocaElFichero } from '../../utils/modoPistas'
import { FitTextPair } from '../FitText'
import { IconoAviso } from '../Iconos'
import { Modal } from '../Modal'
import { SourceComparisonModal } from '../SourceComparisonModal'
import { FIELD_INFO, INTERNAL_TITLE_LABEL, labelStyle } from './constantes'
import { MediaInfoTable } from './MediaInfoTable'
import { AvisoSubidaExistente, BotonComparacionSource, CampoTag, FieldLabel, GeneratingHint, TableLoadingSpinner } from './piezas'
import { AvisoModoPistas, RemuxTable } from './RemuxTable'
import type { Asistente } from './useAsistente'

export function PasoArchivo({ a }: { a: Asistente }) {
  const {
    seleccion, targetId, episodeQueue, episodes, needsSelection, existingJob, existingJobBlocking,
    episodePrepping, episodePrepIndex, loading, error, loadFields,
    fields, setField, titleOptions, titleWarning, sources, providers, opcionesTag, detectingProvider,
    sourceRequiresProvider, sourceWarning, avisoSource, audioWarning, preview,
    sourceComparison, showSourceCompare, setShowSourceCompare, showEngineDetail, setShowEngineDetail,
    showMiCard, setShowMiCard, miReport, miLoading, miError, runMediaInfo,
    showRemuxCard, setShowRemuxCard, remuxPreview, remuxLoading, remuxError, remuxEdits, runTrackRemux,
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
        {showSourceCompare && sourceComparison && (
          <SourceComparisonModal
            comparison={sourceComparison}
            initialShowDetail={showEngineDetail}
            onClose={() => setShowSourceCompare(false)}
          />
        )}
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
      <div className="detail-card asist-tarjeta asist-mt-16">
        {preview?.torrent_name && preview?.internal_mkv_title ? (
          <FitTextPair
            min={9}
            items={[
              { label: 'Nombre final del torrent (eMuwarez)', text: preview.torrent_name, labelStyle },
              { label: INTERNAL_TITLE_LABEL, text: preview.internal_mkv_title, labelStyle },
            ]}
          />
        ) : (
          <>
            <div className="asist-etiqueta">Nombre final del torrent (eMuwarez)</div>
            <GeneratingHint />
            <div className="asist-etiqueta asist-mt-10">{INTERNAL_TITLE_LABEL}</div>
            <GeneratingHint />
          </>
        )}
      </div>
    </>
  )


  return (
    <div className="modal-body">
      {episodeQueue.length > 1 && (
        <div className="asist-selector-fila">
          <select
            className="form-input form-select asist-select-auto"
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
          <button className="btn btn-secondary btn-sm" type="button" onClick={loadFields}>↻ Reintentar</button>
        </div>
      )}
      {!loading && !error && !episodePrepping && (
        <>
          <p className="text-muted asist-t12 asist-mb-12">
            Los campos técnicos (audio por pista, códec, HDR/DV) se leen con MediaInfo del archivo
            real; el título/año vienen de Radarr/Sonarr y el Source/Provider del nombre del archivo.
            Puedes ajustar cualquier campo, o ver el detalle de MediaInfo abajo.
          </p>
          {fieldBox}

          <div className="asist-bloque-mediainfo">
            <div className="asist-fila-entre">
              <div>
                <div className="asist-bloque-titulo">MediaInfo y pistas del archivo</div>
                <div className="text-muted asist-t11 asist-mt-2">
                  Ver Pistas: muestra la reordenación y el nombre de las pistas de vídeo/audio/subtítulos del contenido{esTanda(seleccion) ? '' : ' (editable)'}.
                  <br />
                  Ver MediaInfo: muestra el detalle técnico real del archivo.
                </div>
              </div>
              <div className="asist-botones">
                <button className="btn btn-primary" onClick={() => { runMediaInfo(); setShowMiCard(true) }} disabled={targetId == null}>
                  Ver MediaInfo
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    setShowRemuxCard(true)
                    if (!remuxPreview && !remuxLoading) runTrackRemux()
                  }}
                  disabled={targetId == null}
                >
                  Ver Pistas
                </button>
              </div>
            </div>
          </div>

          {showMiCard && (
            <Modal titulo="MediaInfo del archivo" onClose={() => setShowMiCard(false)} className="modal-wide asist-modal-ancho">
              <div className="modal-body">
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
                    // Closes this card before opening the comparison one — both are
                    // modal-overlays at the same z-index, so having two open at once
                    // would bury the newly-opened one behind this still-open card.
                    onSourceToolClick={sourceComparison ? () => { setShowMiCard(false); setShowEngineDetail(true); setShowSourceCompare(true) } : undefined}
                  />
                )}
              </div>
            </Modal>
          )}

          {showRemuxCard && (
            <Modal
              titulo={<>
                Ordenación y Nombre de las Pistas
                <AvisoModoPistas plan={remuxPreview} />
              </>}
              onClose={() => setShowRemuxCard(false)}
              className="modal-wide"
              tituloStyle={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}
            >
              <div className="modal-body">
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
                    {esTanda(seleccion) && (
                      <p className="text-muted asist-t12 asist-mt-0">
                        Al subir varios capítulos a la vez se aplican los nombres automáticos. Para cambiarlos, sube el capítulo suelto.
                      </p>
                    )}
                    <RemuxTable
                      plan={remuxPreview}
                      editable={!esTanda(seleccion) && tocaElFichero(normalizarModo(remuxPreview.track_mode))}
                      nameEditable={!esTanda(seleccion) && renombra(normalizarModo(remuxPreview.track_mode))}
                      edits={remuxEdits}
                      onEdit={setRemuxEdit}
                      onIdioma={esTanda(seleccion) ? undefined : elegirIdioma}
                    />
                  </>
                )}
              </div>
            </Modal>
          )}

          <div className="asist-pie">
            {needsSelection
              ? <button className="btn btn-secondary" onClick={() => setStep(0)}>Volver a la selección</button>
              : <span />}
            <button className="btn btn-primary" onClick={goToUpload} disabled={preparing || recalculandoIdioma || !preview || existingJobBlocking}>
              {preparing ? 'Preparando…' : 'Continuar'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
