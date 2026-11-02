import { describirSerie, formatDia, trazar, type Medidas, type PuntoSerie } from '../utils/graficos'

export interface SerieGrafico {
  nombre: string
  clase: string          // el color y el trazo, en estadisticas.css
  puntos: PuntoSerie[]
}

interface GraficoLineaProps {
  titulo: string
  series: SerieGrafico[]
  formato: (n: number) => string
  desdeCero?: boolean
}

const MEDIDAS: Medidas = { ancho: 640, alto: 220, izquierda: 72, derecha: 16, arriba: 12, abajo: 28 }
// Con pocos puntos se marca cada uno; con muchos, solo el último.
const MAX_PUNTOS_MARCADOS = 45

// Gráfico de línea en SVG: el dibujo es para ver, y `role="img"` con su resumen es lo que oye un lector de
// pantalla (todos los datos están en la tabla de la página).
export function GraficoLinea({ titulo, series, formato, desdeCero = false }: GraficoLineaProps) {
  const trazado = trazar(series.map(s => s.puntos), MEDIDAS, desdeCero)
  const hayDatos = trazado.lineas.some(l => l.puntos.length > 0)
  const { ancho, alto, izquierda, derecha, abajo } = MEDIDAS
  const resumen = series.map(s => describirSerie(s.nombre, s.puntos, formato)).join(' ')

  return (
    <figure className="est-grafico">
      <figcaption className="est-grafico-titulo">{titulo}</figcaption>
      {!hayDatos ? (
        <p className="est-sin-datos">Sin datos de esto en este rango.</p>
      ) : (
        <svg className="est-svg" viewBox={`0 0 ${ancho} ${alto}`} role="img" aria-label={`${titulo}. ${resumen}`}>
          <title>{titulo}</title>
          {trazado.ticksY.map(t => (
            <g key={t.valor}>
              <line className="est-rejilla" x1={izquierda} x2={ancho - derecha} y1={t.y} y2={t.y} />
              <text className="est-eje" x={izquierda - 8} y={t.y} textAnchor="end" dominantBaseline="middle">{formato(t.valor)}</text>
            </g>
          ))}
          {trazado.ticksX.map((t, i) => (
            <text key={t.dia} className="est-eje" x={t.x} y={alto - abajo + 18}
              textAnchor={i === 0 && trazado.ticksX.length > 1 ? 'start' : i === trazado.ticksX.length - 1 && i > 0 ? 'end' : 'middle'}>
              {formatDia(t.dia, true)}
            </text>
          ))}
          <line className="est-base" x1={izquierda} x2={ancho - derecha} y1={alto - abajo} y2={alto - abajo} />
          {trazado.lineas.map((l, i) => (
            <g key={series[i].nombre} className={series[i].clase}>
              <path className="est-linea" d={l.camino} />
              {(l.puntos.length <= MAX_PUNTOS_MARCADOS ? l.puntos : l.puntos.slice(-1)).map(p => (
                <circle key={p.dia} className="est-punto" cx={p.x} cy={p.y} r={3} />
              ))}
            </g>
          ))}
        </svg>
      )}
      {series.length > 1 && (
        <ul className="est-leyenda">
          {series.map(s => (
            <li key={s.nombre} className={s.clase}>
              <svg width="28" height="8" aria-hidden="true"><line className="est-linea" x1="0" x2="28" y1="4" y2="4" /></svg>
              {s.nombre}
            </li>
          ))}
        </ul>
      )}
    </figure>
  )
}
