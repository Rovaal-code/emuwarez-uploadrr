import { useEffect, useState } from 'react'
import { getEstadisticasCuenta } from '../api/estadisticas'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { GraficoLinea } from '../components/GraficoLinea'
import { LoadingState } from '../components/LoadingState'
import { useSeccionVisible } from '../context/SeccionVisible'
import type { PuntoCuenta } from '../types/api'
import { formatBytes, formatNumero, SIN_DATO } from '../utils/format'
import { formatDia, type PuntoSerie } from '../utils/graficos'

const RANGOS = [30, 90, 365]

// formatBytes enseña una raya para el cero; en un eje o en la tabla, 0 es una cifra.
const bytes = (n: number) => (n === 0 ? '0 B' : formatBytes(n))
const ratio = (n: number) => formatNumero(n, 2)
const entero = (n: number) => formatNumero(n)

const serie = (puntos: PuntoCuenta[], campo: Exclude<keyof PuntoCuenta, 'dia'>): PuntoSerie[] =>
  puntos.map(p => ({ dia: p.dia, valor: p[campo] }))

const celda = (n: number | null, formato: (n: number) => string) => (n === null ? SIN_DATO : formato(n))

type Resultado = { dias: number; puntos: PuntoCuenta[] | null; error: string | null }

// La evolución de tu cuenta de eMuwarez: una instantánea al día, que el servidor guarda al leer tu perfil.
// Se pide al entrar en la sección y al cambiar de rango; no hay sondeo.
export function EstadisticasPage() {
  const seVe = useSeccionVisible()
  const [dias, setDias] = useState(90)
  const [intento, setIntento] = useState(0)
  const [resultado, setResultado] = useState<Resultado | null>(null)

  useEffect(() => {
    if (!seVe) return
    let vigente = true
    getEstadisticasCuenta(dias).then(
      r => { if (vigente) setResultado({ dias, puntos: r.puntos, error: null }) },
      () => { if (vigente) setResultado({ dias, puntos: null, error: 'No se pudo cargar la evolución de tu cuenta.' }) },
    )
    return () => { vigente = false }
  }, [seVe, dias, intento])

  const puntos = resultado?.puntos ?? []

  return (
    <div className="est-pagina">
      <div className="page-header">
        <div>
          <div className="page-title">Estadísticas</div>
          <div className="page-subtitle">Cómo evoluciona tu cuenta de eMuwarez: una instantánea al día, que se guarda sola al leer tu perfil.</div>
        </div>
        <div className="est-rangos" role="group" aria-label="Rango de días">
          {RANGOS.map(r => (
            <button key={r} type="button" className={`btn btn-sm ${r === dias ? 'btn-primary' : 'btn-secondary'}`}
              aria-pressed={r === dias} onClick={() => setDias(r)}>
              {r} días
            </button>
          ))}
        </div>
      </div>

      {resultado === null || resultado.dias !== dias ? (
        <LoadingState label="Cargando estadísticas…" />
      ) : resultado.error ? (
        <ErrorState message={resultado.error} onRetry={() => { setResultado(null); setIntento(n => n + 1) }} />
      ) : puntos.length === 0 ? (
        <EmptyState
          title="Todavía no hay datos"
          body="Se empieza a guardar hoy: la primera instantánea sale en cuanto se lea tu perfil de eMuwarez (hace falta su API key en Configuración)."
        />
      ) : (
        <>
          {puntos.length === 1 && (
            <p className="est-nota" role="status">Solo hay un día guardado: la línea aparecerá a partir de mañana.</p>
          )}
          <div className="est-rejilla-graficos">
            <GraficoLinea titulo="Ratio" formato={ratio}
              series={[{ nombre: 'Ratio', clase: 'est-serie-ratio', puntos: serie(puntos, 'ratio') }]} />
            <GraficoLinea titulo="Subido y bajado" formato={bytes}
              series={[
                { nombre: 'Subido', clase: 'est-serie-subido', puntos: serie(puntos, 'subido_bytes') },
                { nombre: 'Bajado', clase: 'est-serie-bajado', puntos: serie(puntos, 'bajado_bytes') },
              ]} />
            <GraficoLinea titulo="Bonus" formato={entero}
              series={[{ nombre: 'Bonus', clase: 'est-serie-bonus', puntos: serie(puntos, 'bonus') }]} />
          </div>

          <details className="est-tabla">
            <summary>Ver los datos en una tabla</summary>
            <table className="data-table">
              <caption className="solo-lector">Instantáneas diarias de tu cuenta, de la más reciente a la más antigua</caption>
              <thead>
                <tr>
                  <th scope="col">Día</th><th scope="col">Ratio</th><th scope="col">Subido</th>
                  <th scope="col">Bajado</th><th scope="col">Bonus</th>
                </tr>
              </thead>
              <tbody>
                {[...puntos].reverse().map(p => (
                  <tr key={p.dia}>
                    <th scope="row">{formatDia(p.dia)}</th>
                    <td>{celda(p.ratio, ratio)}</td>
                    <td>{celda(p.subido_bytes, bytes)}</td>
                    <td>{celda(p.bajado_bytes, bytes)}</td>
                    <td>{celda(p.bonus, entero)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </div>
  )
}
