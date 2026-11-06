import { useState } from 'react'
import { borrarLote, cancelarLote, reintentarLote } from '../api/uploads'
import type { LoteAccionResult, LoteBorrarResult, LoteResumen } from '../types/api'
import { useTooltip } from './Tooltip'
import { Modal } from './Modal'

const cuenta = (n: number, una: string, varias: string) => `${n} ${n === 1 ? una : varias}`

// Los contadores del banner, en el orden en que avanza una subida; solo se enseñan los que no son cero.
type Contador = 'en_cola' | 'en_marcha' | 'completadas' | 'fallidas' | 'canceladas'
const CONTADORES: { clave: Contador; una: string; varias: string }[] = [
  { clave: 'en_cola', una: 'en cola', varias: 'en cola' },
  { clave: 'en_marcha', una: 'en marcha', varias: 'en marcha' },
  { clave: 'completadas', una: 'completada', varias: 'completadas' },
  { clave: 'fallidas', una: 'fallida', varias: 'fallidas' },
  { clave: 'canceladas', una: 'cancelada', varias: 'canceladas' },
]

// El orden de la barra: lo hecho primero, luego lo que va y lo que espera, y al final lo que no salió.
const ORDEN_BARRA: Contador[] = ['completadas', 'en_marcha', 'en_cola', 'fallidas', 'canceladas']

// «3 canceladas · 1 ya había empezado»: lo que dice el banner tras «Cancelar pendientes».
function textoCancelacion(r: LoteAccionResult, soloPendientes: boolean): string {
  if (r.canceladas === 0 && r.intactas === 0) return 'No había ninguna que cancelar.'
  const partes = [cuenta(r.canceladas, 'cancelada', 'canceladas')]
  if (r.intactas > 0) {
    partes.push(soloPendientes
      ? `${r.intactas} ${r.intactas === 1 ? 'ya había empezado' : 'ya habían empezado'}`
      : `${r.intactas} ${r.intactas === 1 ? 'no se pudo parar' : 'no se pudieron parar'}`)
  }
  return partes.join(' · ')
}

// «2 reintentadas»; las que se saltaron van aparte, cada una con su motivo.
function textoReintento(r: LoteAccionResult): string {
  if (r.reintentadas === 0) return r.saltadas.length > 0 ? 'Ninguna reintentada' : 'No había ninguna que reintentar.'
  return cuenta(r.reintentadas, 'reintentada', 'reintentadas')
}

// «3 borradas (con 2 reintentos) · 1 sigue en cola o en marcha»: lo que dice el banner tras «Borrar lote».
function textoBorrado(r: LoteBorrarResult): string {
  if (r.borradas === 0 && r.en_curso === 0) return 'No había ninguna terminada que borrar.'
  const reintentos = r.intentos - r.borradas
  const partes = [
    cuenta(r.borradas, 'borrada', 'borradas') + (reintentos > 0 ? ` (con ${cuenta(reintentos, 'reintento', 'reintentos')})` : ''),
  ]
  if (r.en_curso > 0) {
    partes.push(r.en_curso === 1
      ? '1 sigue en cola o en marcha y no se ha borrado'
      : `${r.en_curso} siguen en cola o en marcha y no se han borrado`)
  }
  return partes.join(' · ')
}

type Aviso = { texto: string; saltadas: LoteAccionResult['saltadas'] } | { error: string }

/**
 * Sobre la tabla de Subidas filtrada por un lote: cuántas hay en cada estado, «Cancelar pendientes», «Reintentar
 * fallidas», «Borrar lote» (las terminadas) y «Quitar filtro». Si el freno paró el lote, por qué y cuántas paró. El resumen lo pide UploadsPage en su `load()`, que ya refrescan los avisos del servidor.
 */
export function BannerLote({ loteId, resumen, totalConocido, sinSubidas = false, onQuitar, onHecho }: {
  loteId: string
  // null mientras llega o si el servidor no conoce el lote (404): sin contadores ni acciones.
  resumen: LoteResumen | null
  // Lo que dicen las filas cargadas, hasta que llega el resumen.
  totalConocido: number | null
  // El servidor ya no conoce el lote: se borraron todas sus subidas.
  sinSubidas?: boolean
  onQuitar: () => void
  // Tras cancelar, reintentar o borrar: recargar la lista y el resumen.
  onHecho: () => Promise<void> | void
}) {
  const [confirmar, setConfirmar] = useState(false)
  const [confirmarBorrar, setConfirmarBorrar] = useState(false)
  const [tambienEnMarcha, setTambienEnMarcha] = useState(false)
  const [ocupado, setOcupado] = useState(false)
  const [aviso, setAviso] = useState<Aviso | null>(null)

  const total = resumen?.total ?? totalConocido
  const puedeCancelar = !!resumen?.puede_cancelar && !ocupado
  const puedeReintentar = !!resumen?.puede_reintentar && !ocupado
  const cancelarTip = useTooltip(resumen?.puede_cancelar ? null : 'No queda ninguna en cola ni en marcha')
  const reintentarTip = useTooltip(resumen?.puede_reintentar ? null : 'No hay ninguna fallida ni cancelada')
  // Lo que «Borrar lote» se llevaría: los elementos terminados, salgan bien o mal.
  const terminadas = resumen ? resumen.completadas + resumen.fallidas + resumen.canceladas : 0
  const puedeBorrar = terminadas > 0 && !ocupado
  const borrarTip = useTooltip(terminadas > 0 ? null : 'No hay ninguna terminada que borrar')

  const abrirCancelar = () => { setTambienEnMarcha(false); setConfirmar(true) }

  const hacerCancelar = async () => {
    const soloPendientes = !tambienEnMarcha
    setConfirmar(false); setOcupado(true); setAviso(null)
    try {
      const r = await cancelarLote(loteId, soloPendientes)
      setAviso({ texto: textoCancelacion(r, soloPendientes), saltadas: [] })
      await onHecho()
    } catch (e: unknown) {
      setAviso({ error: e instanceof Error ? e.message : 'No se pudo cancelar el lote.' })
    } finally { setOcupado(false) }
  }

  const hacerReintentar = async () => {
    setOcupado(true); setAviso(null)
    try {
      const r = await reintentarLote(loteId)
      setAviso({ texto: textoReintento(r), saltadas: r.saltadas })
      await onHecho()
    } catch (e: unknown) {
      setAviso({ error: e instanceof Error ? e.message : 'No se pudieron reintentar las fallidas del lote.' })
    } finally { setOcupado(false) }
  }

  const hacerBorrar = async () => {
    setConfirmarBorrar(false); setOcupado(true); setAviso(null)
    try {
      const r = await borrarLote(loteId)
      setAviso({ texto: textoBorrado(r), saltadas: [] })
      await onHecho()
    } catch (e: unknown) {
      setAviso({ error: e instanceof Error ? e.message : 'No se pudo borrar el lote.' })
    } finally { setOcupado(false) }
  }

  const enCola = resumen?.en_cola ?? 0
  const enMarcha = resumen?.en_marcha ?? 0

  return (
    <div className="sub-lote-banner sub-no-encoge">
      <div className="sub-lote-banner-fila">
        <span className="sub-lote-banner-titulo">
          {sinSubidas ? 'Lote sin subidas' : total != null ? `Lote de ${cuenta(total, 'subida', 'subidas')}` : 'Lote'}
        </span>
        {resumen && (
          <ul className="sub-lote-contadores" aria-label="Estado del lote">
            {CONTADORES.filter(c => resumen[c.clave] > 0).map(c => (
              <li key={c.clave} className={`sub-lote-contador sub-lote-contador-${c.clave}`}>
                <span className="sub-lote-punto" aria-hidden="true" />
                {cuenta(resumen[c.clave], c.una, c.varias)}
              </li>
            ))}
          </ul>
        )}
        <div className="sub-lote-banner-acciones">
          <button type="button" className="btn btn-danger btn-sm" disabled={!puedeCancelar} onClick={abrirCancelar}
            {...cancelarTip.triggerProps}>
            Cancelar pendientes
            {cancelarTip.tooltipNode}
          </button>
          <button type="button" className="btn btn-primary btn-sm" disabled={!puedeReintentar} onClick={hacerReintentar}
            {...reintentarTip.triggerProps}>
            Reintentar fallidas
            {reintentarTip.tooltipNode}
          </button>
          <button type="button" className="btn btn-danger btn-sm" disabled={!puedeBorrar}
            onClick={() => setConfirmarBorrar(true)} {...borrarTip.triggerProps}>
            Borrar lote
            {borrarTip.tooltipNode}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onQuitar}>Quitar filtro</button>
        </div>
      </div>

      {resumen && resumen.total > 0 && (
        // Los elementos del lote por estado, en el orden en que avanza una subida; el texto de los contadores ya lo
        // dice, así que la barra es solo un vistazo.
        <div className="sub-lote-barra" aria-hidden="true">
          {ORDEN_BARRA.filter(c => resumen[c] > 0).map(c => (
            // Valor calculado: la parte del lote que está en este estado.
            <span key={c} className={`sub-lote-tramo sub-lote-tramo-${c}`} style={{ flexGrow: resumen[c] }} />
          ))}
        </div>
      )}

      {resumen?.parado && (
        <p className="sub-lote-parado" role="note">
          {resumen.parado}.{' '}
          {resumen.paradas === 1
            ? '1 subida no llegó a empezar; «Reintentar fallidas» la relanza.'
            : `${resumen.paradas} subidas no llegaron a empezar; «Reintentar fallidas» las relanza.`}
        </p>
      )}

      {aviso && ('error' in aviso ? (
        <p className="error-text sub-lote-aviso" role="alert">{aviso.error}</p>
      ) : (
        <div className="sub-lote-aviso" role="status">
          {aviso.texto}
          {aviso.saltadas.length > 0 && (
            <ul className="sub-lote-saltadas">
              {aviso.saltadas.map(s => (
                <li key={s.job_id}>
                  <strong>{s.title || `Subida #${s.job_id}`}</strong>: {s.errors.join('; ') || 'No se pudo reintentar.'}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}

      {confirmar && (
        <Modal titulo="Cancelar las pendientes del lote" onClose={() => setConfirmar(false)} className="sub-modal-520">
          <div className="modal-body">
            <p className="sub-t13">
              {enCola > 0
                ? <>Se cancelarán las <strong>{cuenta(enCola, 'subida', 'subidas')}</strong> del lote que esperan en la cola. Aún no han tocado ningún fichero.</>
                : <>No queda ninguna subida del lote esperando en la cola.</>}
            </p>
            <label className="checkbox-label sub-lote-casilla">
              <input type="checkbox" checked={tambienEnMarcha} onChange={e => setTambienEnMarcha(e.target.checked)} />
              Parar también las que ya se están preparando o subiendo{enMarcha > 0 ? ` (${enMarcha})` : ''}
            </label>
            {tambienEnMarcha && (
              <p className="sub-muted sub-t13">
                Las que están preparando ficheros se marcarán como <strong>canceladas</strong> y se detendrán al
                terminar el paso en curso, no al instante. Podrás <strong>reintentarlas</strong> después: revisa el
                archivo antes, por si quedó algo a medio renombrar.
              </p>
            )}
            <div className="sub-modal-pie">
              <button className="btn btn-secondary" type="button" onClick={() => setConfirmar(false)}>
                Dejarlas seguir
              </button>
              <button className="btn btn-primary" type="button" disabled={enCola === 0 && !tambienEnMarcha} onClick={hacerCancelar}>
                {tambienEnMarcha ? 'Cancelar todas' : 'Cancelar las pendientes'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {confirmarBorrar && (
        <Modal titulo="Borrar el lote" onClose={() => setConfirmarBorrar(false)} className="sub-modal-520">
          <div className="modal-body">
            <p className="sub-t13">
              Se borrarán las <strong>{cuenta(terminadas, 'subida terminada', 'subidas terminadas')}</strong> del lote
              (completadas, fallidas o canceladas), con todo lo registrado de cada una: registro de actividad, capturas
              y demás datos generados. Esta acción no se puede deshacer.
            </p>
            <p className="sub-t13">
              Como al borrar una fila suelta, cada subida se borra <strong>entera, con todos sus intentos</strong>:
              también los que hiciste de ese mismo contenido fuera de este lote (sueltos o en otro lote).
            </p>
            {enCola + enMarcha > 0 && (
              <p className="sub-t13">
                {enCola + enMarcha === 1
                  ? <>La que sigue en cola o en marcha <strong>no se borra</strong>.</>
                  : <>Las <strong>{enCola + enMarcha}</strong> que siguen en cola o en marcha <strong>no se borran</strong>.</>}
              </p>
            )}
            <p className="sub-muted sub-t13">
              Los archivos de vídeo de tu biblioteca no se tocan. Solo se borra el registro en esta aplicación.
            </p>
            <div className="sub-modal-pie">
              <button className="btn btn-secondary" type="button" onClick={() => setConfirmarBorrar(false)}>
                No borrar
              </button>
              <button className="btn btn-danger" type="button" onClick={hacerBorrar}>
                {terminadas === 1 ? 'Borrar 1 subida' : `Borrar ${terminadas} subidas`}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
