// Paso 2 con varios elementos (temporadas o capítulos): las comprobaciones de
// cada uno, las comunes a todos, y «Subir todas/todos» con su resultado. Mismo
// aspecto que el de uno solo: tarjeta de comprobaciones y desplegable arriba a
// la derecha para recorrer los elementos.
import { CheckRow } from './piezas'
import type { Asistente } from './useAsistente'

export function PasoSubidaTanda({ a }: { a: Asistente }) {
  const {
    batchQueue, batchIsEpisodes, batchItemTitle, batchPhase, batchIndex, batchResults,
    batchViewId, setBatchViewId, batchEnvChecks, batchContentChecks, batchChecksLoading, batchChecksIndex,
    recalculandoIdioma, setStep, uploadAllEpisodes, uploadAllSeasons, onDone, onNavigate, onClose,
  } = a
  return (
    <div className="modal-body">
      {batchPhase === 'idle' && (() => {
        const viewId = batchViewId ?? batchQueue[0]
        const contentChecks = batchContentChecks.get(viewId)
        const blocked = batchQueue.filter(id => batchContentChecks.get(id)?.ready === false)
        const envReady = batchEnvChecks?.ready !== false
        return (
          <>
            <div className="asist-selector-fila">
              <select
                className="form-input form-select asist-select-auto"
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
                : <div className="asist-t12 text-muted">
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

              {!batchChecksLoading && (
                <div className={blocked.length === 0 && envReady ? 'asist-mt-14 asist-negrita asist-ok' : 'asist-mt-14 asist-negrita asist-error'}>
                  {!envReady
                    ? '✗ La subida no se puede realizar'
                    : blocked.length === 0
                    ? `✓ Todo listo: ${batchQueue.length} ${batchIsEpisodes ? 'capítulos' : 'temporadas'}`
                    : `✗ ${blocked.length} de ${batchQueue.length} no se ${blocked.length === 1 ? 'puede' : 'pueden'} subir`}
                </div>
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

            <div className="asist-pie">
              <button className="btn btn-secondary" onClick={() => setStep(1)} type="button">Volver</button>
              <button
                className="btn btn-primary"
                onClick={batchIsEpisodes ? uploadAllEpisodes : uploadAllSeasons}
                disabled={batchChecksLoading || recalculandoIdioma || !envReady || blocked.length === batchQueue.length}
                type="button"
              >
                {batchIsEpisodes ? 'Subir todos' : 'Subir todas'}
              </button>
            </div>
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
          <div className="asist-fila-centro">
            <button className="btn btn-primary" onClick={() => { onDone?.(); onNavigate?.('uploads'); onClose() }} type="button">
              Ir a Subidas
            </button>
          </div>
        </>
      )}
    </div>
  )
}
