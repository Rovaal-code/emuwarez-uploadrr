import { Fragment, memo, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { planVentana, columnasAutoFill, filasDeRejilla, medidaCorregida, cuentaTrasMedir, topeRecienAlcanzado, AJUSTES_SEGUIDOS_MAX } from '../utils/ventana'
import { medir } from '../utils/uiScale'

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
  contenedor: RefObject<HTMLElement | null>
  cabecera: RefObject<HTMLElement | null>
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
  const vista = useVista(contenedor, cabecera)
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

  const tramos = useMemo(() => {
    const alturas = items.map(it => medidas.current.get(clave(it)) ?? estimada.current)
    const indicesFijos = new Set<number>()
    if (fijas?.size) items.forEach((it, i) => { if (fijas.has(clave(it))) indicesFijos.add(i) })
    return planVentana({ alturas, desde: vista.desde, alto: vista.alto, margen: MARGEN_PX, fijas: indicesFijos })
    // `version` cuenta como dependencia: es lo que avisa de que hay medidas nuevas.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- version avisa de medidas nuevas (ver arriba)
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
          <CuerpoMedido key={k} clave={k} fija={!!fijas?.has(k)} observador={observador} item={item} indice={t.indice} pintar={pintar} />
        )
      })}
    </>
  )
}

interface PropsRejilla<T> {
  items: readonly T[]
  clave: (item: T) => number
  // El ancho mínimo de una tarjeta y el hueco entre ellas, como en minmax(…, 1fr).
  minimo: number
  hueco: number
  contenedor: RefObject<HTMLElement | null>
  pintar: (item: T, indice: number) => ReactNode
}

/**
 * Una rejilla de tarjetas iguales pintando solo las filas que se ven. Como
 * miden todas lo mismo basta con medir una, y lo que no se pinta es relleno
 * arriba y abajo de la rejilla.
 */
export function RejillaVirtual<T>({ items, clave, minimo, hueco, contenedor, pintar }: PropsRejilla<T>) {
  const vista = useVista(contenedor)
  const rejilla = useRef<HTMLDivElement>(null)
  const [medida, setMedida] = useState({ columnas: 1, alto: minimo * 1.5 })

  // Las columnas, del ancho (las mismas que pondría auto-fill); el alto de
  // fila, de la primera tarjeta, que crece o mengua con las columnas.
  // Corre tras cada pintado y repinta si la medida cambió, así que tiene que
  // calmarse: las correcciones seguidas están limitadas (medidaCorregida). Sin
  // ese tope, dos medidas que se provocan una a la otra repintaban sin fin,
  // React lo cortaba con el error 185 y Biblioteca quedaba en negro.
  const ajustes = useRef({ clave: '', usados: 0 })
  // Lo medido desde que empezó la cuenta, para el aviso del tope.
  const medidas = useRef<string[]>([])
  // Qué lista es: cambia con la identidad de `items`, no solo con su largo
  // (otro orden o contenido de la misma longitud también es otra lista). Los
  // repintados de este componente no la tocan: la medida es estado propio.
  const lista = useRef({ items, version: 0 })
  // eslint-disable-next-line react-hooks/exhaustive-deps -- sin dependencias a propósito: mide tras cada pintado y el tope de medidaCorregida lo calma
  useLayoutEffect(() => {
    const el = rejilla.current
    if (!el) return
    const columnas = columnasAutoFill(el.clientWidth, minimo, hueco)
    const alto = (el.firstElementChild as HTMLElement | null)?.offsetHeight || medida.alto
    if (lista.current.items !== items) lista.current = { items, version: lista.current.version + 1 }
    // Un scroll, un cambio de lista o de ancho, o una medida ya calmada,
    // empiezan la cuenta de nuevo.
    const clave = `${lista.current.version}|${minimo}|${hueco}|${vista.desde}|${vista.ancho}`
    const coincide = columnas === medida.columnas && alto === medida.alto
    ajustes.current = cuentaTrasMedir(ajustes.current, clave, coincide)
    if (ajustes.current.usados === 0) medidas.current = []
    if (medidas.current.length <= AJUSTES_SEGUIDOS_MAX) medidas.current.push(`${columnas}×${alto}`)
    // El tope para la oscilación sin que se vea: esto es lo único que dice qué medida salta y por qué.
    if (topeRecienAlcanzado(ajustes.current, coincide)) {
      ajustes.current.usados++
      const primera = el.firstElementChild
      console.warn(`RejillaVirtual no se calma: ${medidas.current.join(' → ')}`, {
        ancho: el.clientWidth, altoReal: primera ? medir(primera).height : null,
        zoom: getComputedStyle(document.body).zoom, dpr: window.devicePixelRatio,
        items: items.length, desde: vista.desde,
      })
    }
    const nueva = medidaCorregida(medida, { columnas, alto }, ajustes.current.usados)
    if (!nueva) return
    ajustes.current.usados++
    setMedida(nueva)
  })

  const { columnas } = medida
  const paso = medida.alto + hueco
  const { filas, primera, ultima } = filasDeRejilla({
    total: items.length, columnas, paso, desde: vista.desde, alto: vista.alto, margen: MARGEN_PX,
  })
  const inicio = primera * columnas
  return (
    <div
      ref={rejilla}
      style={{
        display: 'grid', gridTemplateColumns: `repeat(${columnas}, minmax(0, 1fr))`, gap: hueco,
        paddingTop: primera * paso, paddingBottom: (filas - 1 - ultima) * paso,
      }}
    >
      {items.slice(inicio, (ultima + 1) * columnas).map((item, i) => (
        <Fragment key={clave(item)}>{pintar(item, inicio + i)}</Fragment>
      ))}
    </div>
  )
}

// Dónde está el scroll del contenedor, descontada la cabecera fija si la hay.
function useVista(contenedor: RefObject<HTMLElement | null>, cabecera?: RefObject<HTMLElement | null>) {
  const [vista, setVista] = useState({ desde: 0, alto: 0, ancho: 0 })
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
      const cab = cabecera?.current?.offsetHeight ?? 0
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
  return vista
}

function celdasDeCabecera(cabecera: HTMLElement | null): HTMLElement[] {
  const fila = cabecera?.querySelector('tr')
  return fila ? Array.from(fila.children) as HTMLElement[] : []
}

// Se apunta al observador al montarse y se borra al desmontarse: un elemento
// que sale del DOM sigue observado (y retenido) si nadie lo quita.
//
// Pinta él mismo su elemento y va memorizado: al desplazarse solo cambia la
// ventana, así que las filas que siguen a la vista no se vuelven a pintar
// (con `pintar` estable entre desplazamientos, que lo es: el padre no se
// repinta por el scroll). Sin esto, cada salto de PASO_PX repintaba todas las
// filas visibles, y con la CPU a ×4 los fotogramas pasaban de 33 ms.
const CuerpoMedido = memo(CuerpoMedidoSinMemo) as typeof CuerpoMedidoSinMemo

function CuerpoMedidoSinMemo<T>({ clave, fija, observador, item, indice, pintar }: {
  clave: number
  fija: boolean
  observador: ResizeObserver | null
  item: T
  indice: number
  pintar: (item: T, indice: number) => ReactNode
}) {
  const ref = useRef<HTMLTableSectionElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el || !observador) return
    observador.observe(el)
    return () => observador.unobserve(el)
  }, [observador])
  return <tbody ref={ref} data-clave={clave} data-fija={fija ? '1' : undefined}>{pintar(item, indice)}</tbody>
}
