// Paso 1 de un pack de temporada (una o varias): el plan del pack, sus campos
// con el nombre del torrent, el idioma de las pistas sin idioma, y MediaInfo,
// pistas y nombres de cada capítulo.
import { textoOrigenProveedor } from '../../utils/origenProveedor'
import { etiquetaPistaSinIdioma, SIN_IDIOMAS, type IdiomasPorPosicion } from '../../utils/idiomasPack'
import { FitText, FitTextPair } from '../FitText'
import { IconoAviso } from '../Iconos'
import { Modal } from '../Modal'
import { SourceComparisonModal } from '../SourceComparisonModal'
import { EpisodePicker } from './Capitulos'
import { FIELD_INFO, INTERNAL_TITLE_LABEL, labelStyle } from './constantes'
import { MediaInfoTable } from './MediaInfoTable'
import { AvisoSubidaExistente, BotonComparacionSource, CampoTag, FieldLabel, GeneratingHint, MarcoPaso, TableLoadingSpinner } from './piezas'
import { Pestanas, type Pestana } from './Pestanas'
import { AvisoModoPistas, RemuxTable } from './RemuxTable'
import type { Asistente, PestanaArchivo } from './useAsistente'

export function PasoTemporada({ a }: { a: Asistente }) {
  const {
    targetId, seasonQueue, seasons, needsSelection, existingJob, existingJobBlocking,
    seasonPlan, seasonPlanLoading, seasonPlanError, seasonProgress, loadSeasonPlan, seasonDisplayTitle,
    fields, setField, sources, providers, opcionesTag, sourceRequiresProvider, avisoSource, audioWarning,
    sourceComparison, setSourceComparison, showSourceCompare, setShowSourceCompare, showEngineDetail, setShowEngineDetail,
    idiomasPackEnVuelo, idiomasPorTemporada, elegirIdiomaPack, recalculandoIdioma,
    pestana, elegirPestana, detalles,
    cambiarElemento, setStep, goToUpload, preparing,
  } = a
  const {
    seasonNames, seasonNamesLoading, showSeasonNamesCard, setShowSeasonNamesCard,
    seasonNamesEpisodeId, setSeasonNamesEpisodeId, loadSeasonNames,
    seasonMi, seasonMiLoading, seasonMiError, miEpisodeId, setMiEpisodeId, loadSeasonMi,
    seasonRemux, seasonRemuxLoading, seasonRemuxError, remuxEpisodeId, setRemuxEpisodeId, loadSeasonRemux,
  } = detalles

  // Season target: same field-by-field confirmation grid a movie/episode
  // shows. Título/Año/Resolución/Códec/Audio/Subtítulos stay read-only (read
  // straight from the actual files — every episode already has to agree, or
  // build_season_pack_plan blocks otherwise). Source/Proveedor/Tag are
  // editable exactly like a movie/episode: applied uniformly across every
  // episode (source_override/provider_override/tag_override) instead of
  // being stuck with whatever the filename/Radarr-Sonarr happened to say —
  // the same kind of misdetection the Internal Source Tool exists to catch.
  const seasonTitleOptions = seasonPlan?.title_options ?? []
  // Los avisos del plan, tanto si el pack es válido como si está bloqueado.
  const avisosDelPlan = seasonPlan?.warnings?.map((w, i) => (
    <p key={i} className="text-warning asist-aviso-linea"><IconoAviso /> {w}</p>
  ))
  const idiomasPackActuales: IdiomasPorPosicion =
    idiomasPackEnVuelo ?? (targetId != null ? idiomasPorTemporada.get(targetId) : undefined) ?? SIN_IDIOMAS
  const origenProveedor = textoOrigenProveedor(
    seasonPlan?.provider, seasonPlan?.provider_source_detail, fields.provider)

  const seasonFieldBox = (
    <div className="asist-rejilla-campos">
      <label><FieldLabel label="Título" info={FIELD_INFO.title} />
        {seasonTitleOptions.length > 0 ? (
          <select
            className="form-input form-select"
            value={fields.title || seasonPlan?.series_title || ''}
            onChange={e => setField('title', e.target.value)}
            disabled={seasonTitleOptions.length < 2}
          >
            {seasonTitleOptions.map(o => (
              <option key={o.value} value={o.value}>{o.label}: {o.value}</option>
            ))}
          </select>
        ) : (
          <input className="form-input" value={seasonPlan?.series_title || ''} disabled />
        )}
      </label>
      <label><FieldLabel label="Año" info={FIELD_INFO.year} />
        <input className="form-input" value={seasonPlan?.year ?? ''} disabled />
      </label>
      <label><FieldLabel label="Resolución" info={FIELD_INFO.resolution} />
        <input className="form-input" value={seasonPlan?.resolution || ''} disabled />
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
              representativo
              onClick={() => { setShowEngineDetail(false); setShowSourceCompare(v => !v) }}
            />
          )}
        </div>
      </label>
      {avisoSource && (
        <p className="text-warning asist-col-completa asist-t12 asist-m0"><IconoAviso /> {avisoSource}</p>
      )}
      {sourceRequiresProvider && (
        <label><FieldLabel label="Proveedor" info={FIELD_INFO.provider} />
          <select className="form-input form-select" value={fields.provider || ''} onChange={e => setField('provider', e.target.value || null)}>
            <option value="">— Sin proveedor —</option>
            {providers.map(p => <option key={p.code} value={p.code}>{p.name} ({p.code})</option>)}
          </select>
          {origenProveedor && <span className="form-hint">{origenProveedor}</span>}
        </label>
      )}
      <label><FieldLabel label="Códec de vídeo" info={FIELD_INFO.video_codec} />
        <input className="form-input" value={seasonPlan?.video_codec || ''} disabled />
      </label>
      <label><FieldLabel label="Audio" info={FIELD_INFO.audio} />
        <input className="form-input" value={fields.audio_summary ?? seasonPlan?.audio_summary ?? ''} disabled />
        {seasonPlan?.audio_warning && (
          <span className="asist-aviso-campo"><IconoAviso /> {seasonPlan.audio_warning}</span>
        )}
        {audioWarning && (
          <span className="asist-aviso-campo"><IconoAviso /> {audioWarning}</span>
        )}
      </label>
      {(seasonPlan?.pistas_sin_idioma?.length ?? 0) > 0 && (
        <div className="asist-col-completa asist-pila">
          {(seasonPlan?.pistas_sin_idioma ?? []).map(p => (
            <label key={p.posicion}>
              <FieldLabel label={etiquetaPistaSinIdioma(p.posicion, p.pista, p.capitulos)} info={FIELD_INFO.idioma_pista_pack} />
              <select
                className="form-input form-select"
                value={idiomasPackActuales[p.posicion] ?? ''}
                onChange={e => elegirIdiomaPack(p.posicion, e.target.value)}
              >
                <option value="">— Sin idioma (no entra en el nombre) —</option>
                {(seasonPlan?.idiomas_elegibles ?? []).map(o => <option key={o.code} value={o.code}>{o.label}</option>)}
              </select>
            </label>
          ))}
          {recalculandoIdioma && <span className="form-hint"><span className="spinner asist-spinner-10" /> Recalculando el nombre del pack…</span>}
        </div>
      )}
      <label><FieldLabel label="Subtítulos" info={FIELD_INFO.subs} />
        <input className="form-input" value={seasonPlan?.subtitle_summary || ''} disabled />
      </label>
      <CampoTag value={fields.tag} opciones={opcionesTag} onChange={t => setField('tag', t)} />
    </div>
  )

  // El resumen del pack (la tarjeta del nombre va sobre las pestañas): cuántos capítulos y el nombre de cada uno.
  const resumenPack = seasonPlan?.status === 'valid' && (
    <div className="asist-resumen-temporada">
      <span>✓ {seasonPlan.episodes.length} capítulo(s) listos, coherentes entre sí</span>
      <button
        className="btn btn-secondary btn-sm"
        type="button"
        onClick={() => { setShowSeasonNamesCard(true); setSeasonNamesEpisodeId(null); if (!seasonNames && !seasonNamesLoading) loadSeasonNames() }}
      >
        Ver nombre de todos los capítulos
      </button>
    </div>
  )

  const sinIdioma = seasonPlan?.pistas_sin_idioma?.length ?? 0
  const pestanas: Pestana<PestanaArchivo>[] = [
    { id: 'nomenclatura', etiqueta: 'Nomenclatura' },
    { id: 'pistas', etiqueta: 'Pistas', aviso: sinIdioma > 0 ? `${sinIdioma} sin idioma` : undefined },
    { id: 'mediainfo', etiqueta: 'MediaInfo' },
  ]
  const listo = !seasonPlanLoading && !seasonPlanError && !!seasonPlan

  return (
    <MarcoPaso
      pie={<>
        {needsSelection
          ? <button className="btn btn-secondary" type="button" onClick={() => setStep(0)}>Volver a la selección</button>
          : <span />}
        <button className="btn btn-primary" type="button" onClick={goToUpload} disabled={!listo || preparing || recalculandoIdioma || seasonPlan?.status !== 'valid' || existingJobBlocking}>
          {preparing ? 'Preparando…' : 'Continuar'}
        </button>
      </>}
    >
      {seasonQueue.length > 1 && (
        <div className="asist-selector-fila">
          <select
            className="form-input form-select asist-select-auto"
            aria-label="Temporada"
            value={targetId ?? ''} onChange={e => cambiarElemento(Number(e.target.value))}
            disabled={seasonPlanLoading}
          >
            {seasonQueue.map(id => {
              const s = seasons.find(x => x.id === id)
              return <option key={id} value={id}>{s?.title || `Temporada ${s?.season_number ?? id}`}</option>
            })}
          </select>
        </div>
      )}
      <AvisoSubidaExistente job={existingJob} bloquea={existingJobBlocking} />
      {seasonPlanLoading && (
        <div className="asist-espera">
          <span className="spinner asist-spinner-28" />
          <div className="asist-espera-titulo">
            {seasonProgress.total > 0
              ? `Generando Nomenclatura para eMuwarez… (${seasonProgress.done} de ${seasonProgress.total} capítulos)`
              : 'Generando Nomenclatura para eMuwarez…'}
          </div>
          {seasonProgress.current_title && (
            <div className="asist-t12 text-muted">{seasonProgress.current_title}</div>
          )}
        </div>
      )}
      {seasonPlanError && !seasonPlanLoading && (
        <div className="asist-bloque-error">
          <p className="text-error asist-mt-0 asist-mb-10"><IconoAviso /> {seasonPlanError}</p>
          {avisosDelPlan}
          {(seasonPlan?.provider_conflict?.length ?? 0) > 0 && (
            // El error pide elegir un proveedor: el selector tiene que estar aquí.
            <label className="asist-bloque asist-mb-10"><FieldLabel label="Proveedor" info={FIELD_INFO.provider} />
              <select className="form-input form-select" value="" onChange={e => { if (e.target.value) loadSeasonPlan(e.target.value) }}>
                <option value="">— Elegir proveedor para todo el pack —</option>
                {providers.map(p => <option key={p.code} value={p.code}>{p.name} ({p.code})</option>)}
              </select>
            </label>
          )}
          <button className="btn btn-secondary btn-sm" type="button" onClick={() => loadSeasonPlan()}>↻ Reintentar</button>
        </div>
      )}
      {listo && (
        <>
          {/* El nombre del pack, a la vista en las tres pestañas. */}
          <div className="detail-card asist-tarjeta">
            <div className="asist-etiqueta">Nombre final del torrent (eMuwarez)</div>
            {seasonDisplayTitle ? <div translate="no"><FitText min={9} text={seasonDisplayTitle} /></div> : <GeneratingHint />}
          </div>

          <Pestanas nombre="Detalle de los capítulos" pestanas={pestanas} activa={pestana} onCambiar={elegirPestana}>
            {pestana === 'nomenclatura' && (
              <>
                <p className="text-muted asist-t12 asist-mt-0 asist-mb-12">
                  Se sube como un único pack de temporada: todos los capítulos deben tener el mismo códec de
                  audio y vídeo, los mismos idiomas de audio y subtítulos, la misma resolución y el mismo source.
                  Source, Proveedor y Tag se pueden corregir a mano y se aplican a todos los capítulos por igual.
                </p>
                {seasonFieldBox}
                {avisosDelPlan}
                {resumenPack}
              </>
            )}

            {pestana === 'pistas' && (
              <>
                <div className="asist-fila-titulo-pestana">
                  <AvisoModoPistas plan={seasonRemux?.[0]?.plan} />
                </div>
                {seasonRemuxLoading && !seasonRemux && <TableLoadingSpinner label="Calculando las pistas de cada capítulo…" />}
                {seasonRemuxError && !seasonRemuxLoading && (
                  <>
                    <p className="text-error asist-t12 asist-mt-0 asist-mb-10">✗ {seasonRemuxError}</p>
                    <button className="btn btn-secondary btn-sm" type="button" onClick={loadSeasonRemux}>↻ Reintentar</button>
                  </>
                )}
                {seasonRemux && seasonRemux.length > 0 && (() => {
                  const current = seasonRemux.find(e => e.episode_id === remuxEpisodeId) ?? seasonRemux[0]
                  return (
                    <>
                      <EpisodePicker episodes={seasonRemux} currentId={current.episode_id} onChange={setRemuxEpisodeId} />
                      <RemuxTable plan={current.plan} editable={false} />
                    </>
                  )
                })()}
              </>
            )}

            {pestana === 'mediainfo' && (
              <>
                {seasonMiLoading && !seasonMi && <TableLoadingSpinner label="Leyendo MediaInfo de cada capítulo…" />}
                {seasonMiError && !seasonMiLoading && (
                  <>
                    <p className="text-error asist-t12 asist-mt-0 asist-mb-10">✗ {seasonMiError}</p>
                    <button className="btn btn-secondary btn-sm" type="button" onClick={loadSeasonMi}>↻ Reintentar</button>
                  </>
                )}
                {seasonMi && seasonMi.length > 0 && (() => {
                  const current = seasonMi.find(e => e.episode_id === miEpisodeId) ?? seasonMi[0]
                  return (
                    <>
                      <EpisodePicker episodes={seasonMi} currentId={current.episode_id} onChange={setMiEpisodeId} />
                      <MediaInfoTable
                        report={current.report}
                        onSourceToolClick={current.source_comparison ? () => {
                          setSourceComparison(current.source_comparison!)
                          setShowEngineDetail(true)
                          setShowSourceCompare(true)
                        } : undefined}
                      />
                    </>
                  )
                })()}
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

      {showSeasonNamesCard && (
        <Modal titulo="Nombre de todos los capítulos" onClose={() => setShowSeasonNamesCard(false)} className="modal-wide asist-modal-ancho">
          <div className="modal-body">
            {seasonNamesLoading && !seasonNames && <TableLoadingSpinner label="Generando el nombre de cada capítulo…" />}
            {seasonNames && seasonNames.length > 0 && (() => {
              const current = seasonNames.find(e => e.episode_id === seasonNamesEpisodeId) ?? seasonNames[0]
              return (
                <>
                  {seasonNames.length > 1 && (
                    <div className="asist-selector-fila">
                      <select
                        className="form-input form-select asist-select-auto"
                        aria-label="Capítulo"
                        value={current.episode_id}
                        onChange={e => setSeasonNamesEpisodeId(Number(e.target.value))}
                      >
                        {seasonNames.map(ep => (
                          <option key={ep.episode_id} value={ep.episode_id}>{ep.display_title}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  {current.error ? (
                    <p className="text-error asist-t12 asist-m0">✗ {current.error}</p>
                  ) : (
                    <FitTextPair
                      min={9}
                      items={[
                        { label: 'Nombre del torrent', text: current.torrent_name || '—', labelStyle },
                        { label: INTERNAL_TITLE_LABEL, text: current.internal_mkv_title || '—', labelStyle },
                      ]}
                    />
                  )}
                </>
              )
            })()}
          </div>
        </Modal>
      )}
    </MarcoPaso>
  )
}
