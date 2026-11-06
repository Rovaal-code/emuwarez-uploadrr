import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  describirSerie, diaMasCercano, diasDelTrazado, formatDia, trazar, variacion, type Medidas, type PuntoSerie,
} from '../utils/graficos'
import { formatNumero } from '../utils/format'

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
  /** Ocupa toda la fila de la rejilla (el de dos series). */
  ancho?: boolean
}

const ALTO = 220
const ANCHO_INICIAL = 560   // hasta medir el recuadro (y en jsdom, que no mide)
const MARGENES = { izquierda: 62, derecha: 16, arriba: 12, abajo: 28 }
// Con pocos puntos se marca cada uno; con muchos, solo el último (y el del día que se recorre).
const MAX_PUNTOS_MARCADOS = 45
// Una fecha cada ~110 px de eje (cabe «dd/mm» con aire), entre 2 y 8.
const PX_POR_FECHA = 110

const signo = (n: number) => (n > 0 ? '+' : n < 0 ? '−' : '')

/** Lo que cambió la serie en el rango, como «+1,13 (+43,5 %)»; null si no hay con qué comparar. */
function textoVariacion(serie: PuntoSerie[], formato: (n: number) => string): string | null {
  const v = variacion(serie)
  if (!v) return null
  const dif = `${signo(v.diferencia)}${formato(Math.abs(v.diferencia))}`
  return v.porcentaje === null ? dif : `${dif} (${signo(v.porcentaje)}${formatNumero(Math.abs(v.porcentaje), 1)} %)`
}

// El ancho real del recuadro, para dibujar a tamaño real: así el texto de los ejes mide lo mismo en un móvil que
// en un monitor ancho (con un viewBox fijo que se escala, en un móvil las cifras quedaban de 7 px).
function useAncho() {
  const ref = useRef<HTMLDivElement>(null)
  const [ancho, setAncho] = useState(ANCHO_INICIAL)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const medir = () => { const w = Math.round(el.clientWidth); if (w > 0) setAncho(w) }
    medir()
    const ro = new ResizeObserver(medir)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return { ref, ancho }
}

// Gráfico de línea en SVG. El dibujo es para ver; `role="img"` con su resumen es lo que oye un lector de pantalla,
// y todos los datos están además en la tabla de la página. Recorrerlo con el ratón, el dedo o las flechas (con el foco
// en el gráfico) enseña el valor de cada día arriba; la lectura de arriba es la del último día si no se está recorriendo.
export function GraficoLinea({ titulo, series, formato, desdeCero = false, ancho: ocupaFila = false }: GraficoLineaProps) {
  const { ref, ancho } = useAncho()
  const medidas: Medidas = { ancho, alto: ALTO, ...MARGENES }
  const marcasX = Math.max(2, Math.min(8, Math.floor((ancho - MARGENES.izquierda - MARGENES.derecha) / PX_POR_FECHA)))
  const trazado = useMemo(
    () => trazar(series.map(s => s.puntos), medidas, desdeCero, marcasX),
    // `series` se rehace en cada render del padre; se compara por sus datos.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(series.map(s => s.puntos)), ancho, desdeCero, marcasX])
  const hayDatos = trazado.lineas.some(l => l.puntos.length > 0)
  const dias = useMemo(() => diasDelTrazado(trazado), [trazado])
  const { izquierda, derecha, abajo } = MARGENES
  const resumen = series.map(s => describirSerie(s.nombre, s.puntos, formato)).join(' ')

  // El día que se recorre (índice en `dias`); null = ninguno, y se lee el último.
  const [activo, setActivo] = useState<number | null>(null)
  const dia = activo !== null ? dias[activo] : null
  const svgRef = useRef<SVGSVGElement>(null)

  const alPuntero = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    const r = svgRef.current?.getBoundingClientRect()
    if (!r || r.width === 0) return
    // clientX y el rectángulo van en el mismo espacio (puede estar escalado por el zoom de la interfaz).
    const i = diaMasCercano(dias, ((e.clientX - r.left) / r.width) * ancho)
    setActivo(i >= 0 ? i : null)
  }, [dias, ancho])

  const alTeclado = (e: React.KeyboardEvent) => {
    if (dias.length === 0) return
    const ultimo = dias.length - 1
    const actual = activo ?? ultimo
    let siguiente: number | null | undefined
    if (e.key === 'ArrowLeft') siguiente = Math.max(0, actual - 1)
    else if (e.key === 'ArrowRight') siguiente = Math.min(ultimo, actual + 1)
    else if (e.key === 'Home') siguiente = 0
    else if (e.key === 'End') siguiente = ultimo
    else if (e.key === 'Escape') siguiente = null
    else return
    e.preventDefault()
    setActivo(siguiente)
  }

  // Valor de una serie en un día (null si ese día no tiene cifra de esa serie).
  const valorEn = (s: SerieGrafico, d: string | undefined) => (d ? s.puntos.find(p => p.dia === d)?.valor ?? null : null)
  const ultimoDe = (s: SerieGrafico) => [...s.puntos].reverse().find(p => p.valor !== null) ?? null
  const lectura = (s: SerieGrafico) => {
    if (dia) {
      const v = valorEn(s, dia.dia)
      return { texto: v === null ? 'sin dato' : formato(v), delta: null as string | null }
    }
    const u = ultimoDe(s)
    return { texto: u ? formato(u.valor as number) : 'sin datos', delta: textoVariacion(s.puntos, formato) }
  }
  const sub = dia ? formatDia(dia.dia) : (() => {
    const u = series.map(ultimoDe).filter(Boolean).map(p => p!.dia).sort().pop()
    return u ? `Último dato: ${formatDia(u)}` : ''
  })()
  // Lo que anuncia un lector de pantalla al recorrer con las flechas.
  const anuncio = dia ? `${formatDia(dia.dia)}: ${series.map(s => `${s.nombre} ${lectura(s).texto}`).join(', ')}.` : ''

  return (
    <figure className={`est-grafico${ocupaFila ? ' est-grafico-ancho' : ''}`}>
      <figcaption className="est-grafico-cab">
        <span className="est-grafico-titulo">{titulo}</span>
        {hayDatos && <span className="est-grafico-fecha">{sub}</span>}
      </figcaption>
      {hayDatos && (
        <ul className={series.length > 1 ? 'est-leyenda' : 'est-lectura-unica'}>
          {series.map(s => {
            const l = lectura(s)
            return (
              <li key={s.nombre} className={s.clase}>
                {series.length > 1 && <svg width="26" height="8" aria-hidden="true"><line className="est-linea" x1="0" x2="26" y1="4" y2="4" /></svg>}
                <span className={series.length > 1 ? "est-lectura-nombre" : "solo-lector"}>{s.nombre}{series.length === 1 && ": "}</span>
                <strong className="est-lectura-valor">{l.texto}</strong>
                {l.delta && <span className="est-lectura-delta">{l.delta}</span>}
              </li>
            )
          })}
        </ul>
      )}
      {!hayDatos ? (
        <p className="est-sin-datos">Sin datos de esto en este rango.</p>
      ) : (
        <div
          ref={ref} className="est-plot" tabIndex={0} role="group"
          aria-label={`${titulo}. Con las flechas izquierda y derecha se recorre día a día.`}
          onKeyDown={alTeclado} onBlur={() => setActivo(null)}
        >
          <svg
            ref={svgRef} className="est-svg" width={ancho} height={ALTO} viewBox={`0 0 ${ancho} ${ALTO}`}
            role="img" aria-label={`${titulo}. ${resumen}`}
            onPointerMove={alPuntero} onPointerDown={alPuntero} onPointerLeave={() => setActivo(null)}
          >
            <title>{titulo}</title>
            {trazado.ticksY.map(t => (
              <g key={t.valor}>
                <line className="est-rejilla" x1={izquierda} x2={ancho - derecha} y1={t.y} y2={t.y} />
                <text className="est-eje" x={izquierda - 8} y={t.y} textAnchor="end" dominantBaseline="middle">{formato(t.valor)}</text>
              </g>
            ))}
            {trazado.ticksX.map((t, i) => (
              <text key={t.dia} className="est-eje" x={t.x} y={ALTO - abajo + 18}
                textAnchor={i === 0 && trazado.ticksX.length > 1 ? 'start' : i === trazado.ticksX.length - 1 && i > 0 ? 'end' : 'middle'}>
                {formatDia(t.dia, true)}
              </text>
            ))}
            <line className="est-base" x1={izquierda} x2={ancho - derecha} y1={ALTO - abajo} y2={ALTO - abajo} />
            {dia && <line className="est-guia" x1={dia.x} x2={dia.x} y1={MARGENES.arriba} y2={ALTO - abajo} />}
            {trazado.lineas.map((l, i) => (
              <g key={series[i].nombre} className={series[i].clase}>
                <path className="est-linea" d={l.camino} />
                {(l.puntos.length <= MAX_PUNTOS_MARCADOS ? l.puntos : l.puntos.slice(-1)).map(p => (
                  <circle key={p.dia} className="est-punto" cx={p.x} cy={p.y} r={3} />
                ))}
                {dia && l.puntos.filter(p => p.dia === dia.dia).map(p => (
                  <circle key={`a-${p.dia}`} className="est-punto est-punto-activo" cx={p.x} cy={p.y} r={5} />
                ))}
              </g>
            ))}
          </svg>
          <span className="solo-lector" aria-live="polite">{anuncio}</span>
        </div>
      )}
    </figure>
  )
}
