import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { planVentana } from '../utils/ventana'

// Lo que se pinta de más por arriba y por abajo de lo visible: unas diez filas
// a cada lado, para que desplazarse deprisa no enseñe huecos en blanco.
const MARGEN_PX = 600
const PASO_PX = 100

interface Props<T> {
  items: readonly T[]
  clave: (item: T) => number
  // Lo que se supone que mide una fila hasta que se pinta y se mide de verdad.
  alturaEstimada: number
  columnas: number
  // El que hace scroll, y la cabecera fija de la tabla (su alto no es lista).
  contenedor: RefObject<HTMLElement>
  cabecera: RefObject<HTMLElement>
  // Claves que se pintan siempre, se vean o no (ver utils/ventana).
  fijas?: ReadonlySet<number>
  pintar: (item: T, indice: number) => ReactNode
}

/**
 * El cuerpo de una tabla larga pintando solo lo que se ve (utils/ventana).
 *
 * Cada elemento va en su propio <tbody>: una fila de Biblioteca puede ser
 * varias <tr> (una serie desplegada con sus temporadas), y así se mide entera
 * de una vez. Lo que no se pinta se sustituye por un <tbody> hueco de su alto,
 * para que la barra de scroll siga contando la lista completa.
 *
 * Las alturas se leen con offsetHeight, que está en el mismo espacio sin
 * escalar que el CSS y el scrollTop (ver utils/uiScale: el zoom del body).
 */
export function FilasVirtuales<T>({ items, clave, alturaEstimada, columnas, contenedor, cabecera, fijas, pintar }: Props<T>) {
  const [vista, setVista] = useState({ desde: 0, alto: 0, ancho: 0 })
  const medidas = useRef(new Map<number, number>())
  const estimada = useRef(alturaEstimada)
  const [version, setVersion] = useState(0)

  // Un solo observador para todas las filas pintadas: cuando una cambia de
  // alto (se despliega, carga sus capítulos) se apunta y se recalcula.
  const observador = useMemo(() => typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(entradas => {
    let cambia = false
    for (const e of entradas) {
      const el = e.target as HTMLElement
      const k = Number(el.dataset.clave)
      const alto = el.offsetHeight
      if (!alto || medidas.current.get(k) === alto) continue
      // La estimación sale de la primera fila sin desplegar que se mide: un
      // número fijo en el código se desviaría con el tamaño de la interfaz.
      if (estimada.current === alturaEstimada && el.dataset.fija !== '1') estimada.current = alto
      medidas.current.set(k, alto)
      cambia = true
    }
    if (cambia) setVersion(v => v + 1)
  }), [alturaEstimada])
  useEffect(() => () => observador?.disconnect(), [observador])

  // useEffect y no useLayoutEffect: el contenedor es un antepasado, y React
  // engancha su ref DESPUÉS de los efectos de layout de los hijos.
  useEffect(() => {
    const el = contenedor.current
    if (!el) return
    // El desplazamiento va a saltos de PASO_PX: con el margen de MARGEN_PX
    // sobra para que no se vea el borde, y así no se recalcula en cada píxel.
    // Sin requestAnimationFrame: el navegador ya manda `scroll` como mucho una
    // vez por fotograma, y rAF se para en una pestaña en segundo plano, que
    // dejaba la ventana sin actualizar al volver a ella.
    const leer = () => {
      const cab = cabecera.current?.offsetHeight ?? 0
      setVista(v => {
        const desde = Math.floor(Math.max(0, el.scrollTop - cab) / PASO_PX) * PASO_PX
        const alto = el.clientHeight
        const ancho = el.clientWidth
        return v.desde === desde && v.alto === alto && v.ancho === ancho ? v : { desde, alto, ancho }
      })
    }
    leer()
    el.addEventListener('scroll', leer, { passive: true })
    // También al cambiar de tamaño, y al pasar de oculta a visible: la sección
    // se monta escondida (display: none) y entonces mide 0 de alto.
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(leer)
    ro?.observe(el)
    return () => {
      el.removeEventListener('scroll', leer)
      ro?.disconnect()
    }
  }, [contenedor, cabecera])

  const tramos = useMemo(() => {
    const alturas = items.map(it => medidas.current.get(clave(it)) ?? estimada.current)
    const indicesFijos = new Set<number>()
    if (fijas?.size) items.forEach((it, i) => { if (fijas.has(clave(it))) indicesFijos.add(i) })
    return planVentana({ alturas, desde: vista.desde, alto: vista.alto, margen: MARGEN_PX, fijas: indicesFijos })
    // `version` cuenta como dependencia: es lo que avisa de que hay medidas nuevas.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, clave, fijas, vista, version])

  // Con table-layout automático el ancho de cada columna sale de las filas
  // pintadas, y al desplazarte cambian: medido, «Tipo» pasaba de 109 a 115 px
  // al aparecer «Temporada» y la tabla entera bailaba. Mientras la lista y el
  // ancho disponible sean los mismos, una columna solo puede crecer. La que
  // tiene width: 100% (Título) se deja: es la que reparte lo que sobra.
  const anchos = useRef<number[]>([])
  useLayoutEffect(() => {
    anchos.current = []
    for (const th of celdasDeCabecera(cabecera.current)) th.style.minWidth = ''
  }, [items, vista.ancho, cabecera])
  useLayoutEffect(() => {
    celdasDeCabecera(cabecera.current).forEach((th, i) => {
      if (th.style.width === '100%') return
      const w = th.offsetWidth
      if (w > (anchos.current[i] ?? 0)) {
        anchos.current[i] = w
        th.style.minWidth = `${w}px`
      }
    })
  })

  return (
    <>
      {tramos.map(t => {
        if (t.tipo === 'hueco') {
          return (
            <tbody key={t.clave} aria-hidden="true">
              <tr className="fila-hueco"><td colSpan={columnas} style={{ height: t.alto }} /></tr>
            </tbody>
          )
        }
        const item = items[t.indice]
        const k = clave(item)
        return (
          <CuerpoMedido key={k} clave={k} fija={!!fijas?.has(k)} observador={observador}>
            {pintar(item, t.indice)}
          </CuerpoMedido>
        )
      })}
    </>
  )
}

function celdasDeCabecera(cabecera: HTMLElement | null): HTMLElement[] {
  const fila = cabecera?.querySelector('tr')
  return fila ? Array.from(fila.children) as HTMLElement[] : []
}

// Se apunta al observador al montarse y se borra al desmontarse: un elemento
// que sale del DOM sigue observado (y retenido) si nadie lo quita.
function CuerpoMedido({ clave, fija, observador, children }: { clave: number; fija: boolean; observador: ResizeObserver | null; children: ReactNode }) {
  const ref = useRef<HTMLTableSectionElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el || !observador) return
    observador.observe(el)
    return () => observador.unobserve(el)
  }, [observador])
  return <tbody ref={ref} data-clave={clave} data-fija={fija ? '1' : undefined}>{children}</tbody>
}
