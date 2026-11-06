// Paso 2 de «Subir por lotes»: por película o temporada, el nombre del torrent, sus avisos, su comprobación y lo
// que ya hay en eMuwarez, con la casilla «Incluir»; debajo, las comprobaciones comunes (una sola vez) y «Subir N».
import type { UploadCheck, UploadChecksResult } from '../../api/uploads'
import type { LibraryItemResponse } from '../../types/api'
import { CheckRow } from '../asistente/piezas'
import type { AnalisisElemento } from './useLote'

export interface FilaResumenLote {
  item: LibraryItemResponse
  // Las comprobaciones de contenido del elemento; sin llegar todavía, undefined.
  contenido: UploadChecksResult | undefined
  analisis: AnalisisElemento | undefined
  // El nombre del torrent (el de un pack sale de `contenido`); null si no hay, undefined mientras se calcula.
  nombre: string | null | undefined
  // Por qué se saltará seguro (comprobación fallida, nomenclatura bloqueada, nombre repetido); null si no.
  salto: string | null
  // Falta su comprobación o su análisis.
  pendiente: boolean
  incluida: boolean
}

// Qué falló y dónde: la etiqueta dice qué («Contenido no accesible») y el mensaje, el detalle (la ruta, los errores
// del pack). Con solo el mensaje la columna enseñaba una ruta en rojo sin decir qué le pasaba.
export const primerFallo = (c: UploadChecksResult | undefined): string => {
  const fallo = c?.checks.find((x: UploadCheck) => x.status === 'fail')
  if (!fallo) return 'Alguna comprobación falló'
  const { label, message } = fallo
  if (!message || message === label) return label
  return label ? `${label}: ${message}` : message
}

const CLASE_NIVEL: Record<string, string> = {
  duplicado: 'lote-emu-mal', peor: 'lote-emu-mal', mixto: 'lote-emu-aviso', 'sin-comparar': 'lote-emu-aviso', trump: 'lote-emu-bien',
}

export function PasoResumenLote({
  filas, entorno, comprobando, comprobandoIndice, errorComprobando, analizando, paralelo, enviando, rechazo,
  falloEnvio, onIncluir, onRepetir, onVolver, onSubir,
}: {
  filas: readonly FilaResumenLote[]
  entorno: UploadChecksResult | null
  comprobando: boolean
  comprobandoIndice: number
  errorComprobando: string | null
  analizando: boolean
  // «Subidas en paralelo»; null si no se pudo leer.
  paralelo: number | null
  enviando: boolean
  // Los motivos de un 409: falta algo que haría fallar a todas.
  rechazo: string[] | null
  falloEnvio: string | null
  onIncluir: (id: number, incluir: boolean) => void
  onRepetir: () => void
  onVolver: () => void
  onSubir: () => void
}) {
  const total = filas.length
  const incluidas = filas.filter(f => f.incluida).length
  const completas = !!entorno && filas.every(f => f.contenido)
  const envReady = entorno?.ready === true
  const resumen = !comprobando && (completas || !!errorComprobando)
  const fallidas = filas.filter(f => f.contenido?.ready === false || f.analisis?.bloqueo).length
  const puedeSubir = !comprobando && !errorComprobando && completas && envReady && !analizando && incluidas > 0 && !enviando
  const salta = filas.filter(f => f.salto).length
  const porComprobar = filas.filter(f => !f.salto && f.pendiente).length
  return (
    <div className="modal-body">
      {/* Lo que va a pasar con el lote, de un vistazo y sin tener que leer la tabla fila a fila. */}
      <div className="lote-cifras">
        <span className={`lote-cifra${incluidas > 0 ? ' lote-cifra-bien' : ''}`}><strong>{incluidas}</strong> {incluidas === 1 ? 'se subirá' : 'se subirán'}</span>
        {salta > 0 && <span className="lote-cifra lote-cifra-mal"><strong>{salta}</strong> {salta === 1 ? 'se saltará' : 'se saltarán'}</span>}
        {porComprobar > 0 && <span className="lote-cifra"><strong>{porComprobar}</strong> por comprobar</span>}
      </div>
      <div className="lote-tabla-caja">
        <table className="data-table lote-tabla">
          <thead>
            <tr><th>Contenido</th><th>Comprobación</th><th>En eMuwarez</th><th>Incluir</th></tr>
          </thead>
          <tbody>
            {filas.map(f => {
              const a = f.analisis
              // El de una temporada ya lleva la serie: «Serie - Temporada 2».
              const titulo = f.item.title
              return (
                <tr key={f.item.id} data-item={f.item.id}>
                  <td className="lote-celda-titulo">
                    <div className="lote-titulo">{titulo}</div>
                    <div className="lote-nombre">{f.nombre === undefined ? 'Calculando el nombre…' : f.nombre ?? '—'}</div>
                    {a?.avisos.map(aviso => <div key={aviso} className="lote-aviso">⚠ {aviso}</div>)}
                    {f.salto && f.contenido?.ready !== false && <div className="lote-error">✗ {f.salto}</div>}
                  </td>
                  <td>
                    {!f.contenido
                      ? <span className="text-muted">{errorComprobando ? 'Sin comprobar' : 'Comprobando…'}</span>
                      : f.contenido.ready
                        ? <span className="asist-ok">✓ Lista</span>
                        : <span className="asist-error">✗ {f.salto ?? primerFallo(f.contenido)}</span>}
                  </td>
                  <td className={a?.nivel ? CLASE_NIVEL[a.nivel] : undefined}>{a ? a.enEmu : '…'}</td>
                  <td className="lote-celda-incluir">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={f.incluida}
                        disabled={!!f.salto || f.pendiente || enviando}
                        onChange={() => onIncluir(f.item.id, !f.incluida)}
                        aria-label={`Incluir «${titulo}»`}
                      />
                    </label>
                    {f.salto
                      ? <div className="lote-salta">Se saltará</div>
                      : a?.sinIdioma && !f.incluida && <div className="lote-nota">Súbela suelta para elegir el idioma</div>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="detail-card asist-tarjeta asist-mt-12">
        <div className="asist-fila-titulo">
          <div className="asist-etiqueta">Comunes a todo el lote</div>
          {(comprobando || analizando) && <span className="spinner asist-spinner-14" />}
        </div>
        {entorno
          ? entorno.checks.map(c => <CheckRow key={c.id} c={c} />)
          : !errorComprobando && <div className="asist-t12 text-muted">Comprobando…</div>}
        {comprobando && entorno && (
          <div className="asist-t12 text-muted">Comprobando {Math.min(comprobandoIndice + 1, total)} de {total}…</div>
        )}
        {/* La región existe siempre: así el lector anuncia el veredicto cuando llega. */}
        <div role="status">
          {resumen && !analizando && (
            <div className={!errorComprobando && envReady && incluidas > 0 ? 'asist-mt-14 asist-negrita asist-ok' : 'asist-mt-14 asist-negrita asist-error'}>
              {errorComprobando
                ? `✗ No se pudieron completar las comprobaciones: ${errorComprobando}`
                : !envReady
                ? '✗ La subida no se puede realizar'
                : incluidas === 0
                ? '✗ No queda nada marcado para subir'
                : `✓ Se subirán ${incluidas} de ${total}`}
            </div>
          )}
        </div>
        {resumen && !analizando && (!!errorComprobando || !envReady || fallidas > 0) && (
          <button className="btn btn-secondary btn-sm asist-mt-12 asist-t12" onClick={onRepetir} type="button" disabled={enviando}>
            ↻ Volver a comprobar
          </button>
        )}
      </div>

      {paralelo === 0 ? (
        <p className="lote-paralelo lote-paralelo-aviso">
          ⚠ Sin límite: se lanzarán las {incluidas} a la vez contra eMuwarez. Puedes ponerle un tope en Ajustes, «Subidas en paralelo».
        </p>
      ) : (
        <p className="lote-paralelo">
          {paralelo != null
            ? `Se subirán de ${paralelo} en ${paralelo} según “Subidas en paralelo” (ahora: ${paralelo}), en el orden de la lista.`
            : 'Se subirán en el orden de la lista, según “Subidas en paralelo”.'}
        </p>
      )}

      {rechazo && (
        <div className="detail-card asist-tarjeta asist-mt-12" role="alert">
          <p className="asist-bloqueo">✗ No se ha encolado nada:</p>
          <ul className="lote-motivos">{rechazo.map(m => <li key={m}>{m}</li>)}</ul>
        </div>
      )}
      {falloEnvio && <p className="asist-bloqueo" role="alert">✗ No se pudo encolar el lote: {falloEnvio}</p>}

      <div className="asist-pie">
        <button className="btn btn-secondary" onClick={onVolver} type="button" disabled={enviando}>← Volver</button>
        <button className="btn btn-primary" onClick={onSubir} type="button" disabled={!puedeSubir}>
          {enviando ? 'Encolando…' : `Subir ${incluidas}`}
        </button>
      </div>
    </div>
  )
}
