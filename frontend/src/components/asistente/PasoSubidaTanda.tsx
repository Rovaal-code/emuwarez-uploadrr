// Paso 2 con varios elementos (temporadas o capítulos): las comprobaciones de
// cada uno, las comunes a todos, y «Subir todas/todos» con su resultado. Mismo
// aspecto que el de uno solo: tarjeta de comprobaciones y desplegable arriba a
// la derecha para recorrer los elementos.
import { labelStyle } from './constantes'
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
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
              <select
                className="form-input form-select" style={{ width: 'auto' }}
                value={viewId} onChange={e => setBatchViewId(Number(e.target.value))}
              >
                {batchQueue.map(id => {
                  const failed = batchContentChecks.get(id)?.ready === false
                  return <option key={id} value={id}>{failed ? '✗ ' : ''}{batchItemTitle(id)}</option>
                })}
              </select>
            </div>

            <div className="detail-card" style={{ padding: '12px 14px', borderRadius: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <div style={labelStyle}>Comprobaciones previas</div>
                {batchChecksLoading && <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />}
              </div>

              {/* Las del elemento que estés mirando. */}
              {contentChecks
                ? contentChecks.checks.map(c => <CheckRow key={c.id} c={c} />)
                : <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    Comprobando {batchIsEpisodes ? 'capítulo' : 'temporada'} {Math.min(batchChecksIndex + 1, batchQueue.length)} de {batchQueue.length}…
                  </div>}

              {/* Y las compartidas, hechas una sola vez para la tanda. */}
              {batchEnvChecks && (
                <>
                  <div style={{ ...labelStyle, marginTop: 14, marginBottom: 8 }}>
                    Comunes a {batchIsEpisodes ? 'todos los capítulos' : 'todas las temporadas'}
                  </div>
                  {batchEnvChecks.checks.map(c => <CheckRow key={c.id} c={c} />)}
                </>
              )}

              {!batchChecksLoading && (
                <div style={{ marginTop: 14, fontWeight: 600, color: blocked.length === 0 && envReady ? 'var(--color-available)' : 'var(--color-error)' }}>
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
              <div className="detail-card" style={{ padding: '12px 14px', borderRadius: 8, marginTop: 12 }}>
                {blocked.map(id => (
                  <p key={id} style={{ fontSize: 12.5, margin: '4px 0', color: 'var(--color-error-pale)' }}>
                    ✗ {batchItemTitle(id)}: {batchContentChecks.get(id)?.checks.find(c => c.status === 'fail')?.message || 'Alguna comprobación falló'}
                  </p>
                ))}
                <p style={{ fontSize: 12, margin: '10px 0 0', color: 'var(--text-muted)' }}>
                  Se saltarán. El resto se subirá igualmente.
                </p>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
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
        <div style={{ padding: '20px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
          <span className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
          <div style={{ fontSize: 14, fontWeight: 600 }}>
            Subiendo {batchIsEpisodes ? 'capítulo' : 'temporada'} {batchIndex + 1} de {batchQueue.length}
            {`: ${batchItemTitle(batchQueue[batchIndex])}`}
          </div>
        </div>
      )}
      {batchPhase === 'done' && (
        <>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12, textAlign: 'center' }}>
            {batchResults.filter(r => r.status === 'queued').length} de {batchResults.length} {batchIsEpisodes ? 'capítulo(s) encolado(s)' : 'temporada(s) encolada(s)'}
          </div>
          {batchResults.some(r => r.status === 'failed') && (
            <div className="detail-card" style={{ padding: '12px 14px', borderRadius: 8, marginBottom: 14 }}>
              {batchResults.filter(r => r.status === 'failed').map(r => (
                <p key={r.seasonId} style={{ fontSize: 12.5, margin: '4px 0', color: 'var(--color-error-pale)' }}>
                  ✗ {r.title}: {r.reason}
                </p>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <button className="btn btn-primary" onClick={() => { onDone?.(); onNavigate?.('uploads'); onClose() }} type="button">
              Ir a Subidas
            </button>
          </div>
        </>
      )}
    </div>
  )
}
