// Paso Resumen con varios elementos (temporadas o capítulos): el resumen de la
// tanda, las comprobaciones de cada uno, las comunes a todos, y «Subir todas/todos»
// con su resultado. Mismo aspecto que el de uno solo, con un desplegable arriba a
// la derecha para recorrer las comprobaciones de los elementos.
import { CheckRow, MarcoPaso } from './piezas'
import { ResumenSubida } from './ResumenSubida'
import type { Asistente } from './useAsistente'

export function PasoSubidaTanda({ a }: { a: Asistente }) {
  const {
    batchQueue, batchIsEpisodes, batchItemTitle, batchPhase, batchIndex, batchResults,
    batchViewId, setBatchViewId, batchEnvChecks, batchContentChecks, batchChecksLoading, batchChecksIndex,
    batchChecksError, repetirComprobacionesTanda,
    recalculandoIdioma, setStep, uploadAllEpisodes, uploadAllSeasons, onDone, onNavigate, onClose,
  } = a
  // El pie, según la fase: antes de subir, Volver y «Subir todos»; al terminar, ir a Subidas; mientras sube, ninguno.
  const viewId = batchViewId ?? batchQueue[0]
  const blocked = batchQueue.filter(id => batchContentChecks.get(id)?.ready === false)
  const completas = !!batchEnvChecks && batchQueue.every(id => batchContentChecks.has(id))
  const envReady = batchEnvChecks?.ready === true
  const resumen = !batchChecksLoading && (completas || !!batchChecksError)
  const todoBien = !batchChecksError && blocked.length === 0 && envReady
  // El veredicto va en el pie, junto al botón que lo obedece; la región existe siempre para que el lector lo anuncie.
  const veredicto = !resumen ? ''
    : batchChecksError ? `✗ No se pudieron completar las comprobaciones: ${batchChecksError}`
    : !envReady ? '✗ La subida no se puede realizar'
    : blocked.length === 0 ? `✓ Todo listo: ${batchQueue.length} ${batchIsEpisodes ? 'capítulos' : 'temporadas'}`
    : `✗ ${blocked.length} de ${batchQueue.length} no se ${blocked.length === 1 ? 'puede' : 'pueden'} subir`
  const pie = batchPhase === 'idle' ? (
    <>
      <button className="btn btn-secondary" onClick={() => setStep(1)} type="button">← Volver</button>
      <div role="status" className={`asist-pie-estado ${resumen ? (todoBien ? 'asist-ok' : 'asist-error') : ''}`}>{veredicto}</div>
      <button
        className="btn btn-primary"
        onClick={batchIsEpisodes ? uploadAllEpisodes : uploadAllSeasons}
        disabled={batchChecksLoading || recalculandoIdioma || !!batchChecksError || !completas || !envReady || blocked.length === batchQueue.length}
        type="button"
      >
        {batchIsEpisodes ? 'Subir todos' : 'Subir todas'}
      </button>
    </>
  ) : batchPhase === 'done' ? (
    <button className="btn btn-primary" onClick={() => { onDone?.(); onNavigate?.('uploads'); onClose() }} type="button">
      Ir a Subidas
    </button>
  ) : undefined
  return (
    <MarcoPaso pie={pie} finPie={batchPhase === 'done'}>
      {batchPhase === 'idle' && (() => {
        const contentChecks = batchContentChecks.get(viewId)
        return (
          <>
            <ResumenSubida a={a} />

            <div className="asist-selector-fila asist-mt-14">
              <span className="asist-etiqueta-selector" id="asist-comprobaciones-de">Comprobaciones de</span>
              <select
                className="form-input form-select asist-select-auto"
                aria-labelledby="asist-comprobaciones-de"
                value={viewId} onChange={e => setBatchViewId(Number(e.target.value))}
              >
                {batchQueue.map(id => {
                  const failed = batchContentChecks.get(id)?.ready === false
                  return <option key={id} value={id}>{failed ? '✗ ' : ''}{batchItemTitle(id)}</option>
                })}
              </select>
            </div>

            <div className="detail-card asist-tarjeta">
              <div className="asist-fila-titulo">
                <div className="asist-etiqueta">Comprobaciones previas</div>
                {batchChecksLoading && <span className="spinner asist-spinner-14" />}
              </div>

              {/* Las del elemento que estés mirando. */}
              {contentChecks
                ? contentChecks.checks.map(c => <CheckRow key={c.id} c={c} />)
                : !batchChecksError && <div className="asist-t12 text-muted">
                    Comprobando {batchIsEpisodes ? 'capítulo' : 'temporada'} {Math.min(batchChecksIndex + 1, batchQueue.length)} de {batchQueue.length}…
                  </div>}

              {/* Y las compartidas, hechas una sola vez para la tanda. */}
              {batchEnvChecks && (
                <>
                  <div className="asist-etiqueta asist-mt-14 asist-mb-8">
                    Comunes a {batchIsEpisodes ? 'todos los capítulos' : 'todas las temporadas'}
                  </div>
                  {batchEnvChecks.checks.map(c => <CheckRow key={c.id} c={c} />)}
                </>
              )}

              {/* Repite solo lo que falló o no llegó; lo elegido y editado se queda. */}
              {resumen && (!!batchChecksError || !envReady || blocked.length > 0) && (
                <button className="btn btn-secondary btn-sm asist-mt-12 asist-t12" onClick={repetirComprobacionesTanda} type="button">
                  ↻ Volver a comprobar
                </button>
              )}
            </div>

            {/* Qué se va a saltar y por qué, antes de pulsar nada. */}
            {!batchChecksLoading && blocked.length > 0 && (
              <div className="detail-card asist-tarjeta asist-mt-12">
                {blocked.map(id => (
                  <p key={id} className="asist-bloqueo">
                    ✗ {batchItemTitle(id)}: {batchContentChecks.get(id)?.checks.find(c => c.status === 'fail')?.message || 'Alguna comprobación falló'}
                  </p>
                ))}
                <p className="asist-nota-saltan">
                  Se saltarán. El resto se subirá igualmente.
                </p>
              </div>
            )}

          </>
        )
      })()}
      {batchPhase === 'processing' && (
        <div className="asist-espera asist-espera-corta">
          <span className="spinner asist-spinner-28" />
          <div className="asist-negrita asist-t14">
            Subiendo {batchIsEpisodes ? 'capítulo' : 'temporada'} {batchIndex + 1} de {batchQueue.length}
            {`: ${batchItemTitle(batchQueue[batchIndex])}`}
          </div>
        </div>
      )}
      {batchPhase === 'done' && (
        <>
          <div className="asist-resultado-titulo">
            {batchResults.filter(r => r.status === 'queued').length} de {batchResults.length} {batchIsEpisodes ? 'capítulo(s) encolado(s)' : 'temporada(s) encolada(s)'}
          </div>
          {batchResults.some(r => r.status === 'failed') && (
            <div className="detail-card asist-tarjeta asist-mb-14">
              {batchResults.filter(r => r.status === 'failed').map(r => (
                <p key={r.seasonId} className="asist-bloqueo">
                  ✗ {r.title}: {r.reason}
                </p>
              ))}
            </div>
          )}
        </>
      )}
    </MarcoPaso>
  )
}
