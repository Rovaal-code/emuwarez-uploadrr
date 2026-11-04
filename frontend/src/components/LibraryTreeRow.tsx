import { useState, useCallback, useEffect, useRef, memo } from 'react'
import { getLibrary } from '../api/library'
import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { StatusBadge } from './StatusBadge'
import { formatBytes } from '../utils/format'
import { buildDeepLink, posterUrl, listDisplayTitle } from '../utils/libraryItem'
import { GrupoDeLaFila, LineaDeCalidad } from './LineaDeCalidad'
import { LibraryActionButtons } from './LibraryActionButtons'
import { useTooltip } from './Tooltip'
import { ValueChip, ValueIcon, SizeValueIcon, DetailTitleText } from './DetailCard'
import { estadoCastellano, CASTELLANO_INFO } from '../utils/castellano'
import { IconoDesplegar, IconoTipo } from './Iconos'
import { CasillaLote } from './lote/CasillaLote'

const NESTED_PAGE_SIZE = 25
// Seasons per series — well under the API's max limit=500 (a season list
// is never paginated, unlike episodes), but still bounded defensively.
const MAX_SEASONS_PER_SERIES = 500

export type LibraryActionKind = 'nomenclature' | 'fields' | 'upload' | 'request'

interface LibraryTreeRowProps {
  item: LibraryItemResponse
  depth: number
  instances: InstanceSafeResponse[]
  onSelect: (item: LibraryItemResponse) => void
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
  // Called after a nomenclature check so the list can refresh the badges.
  onReload?: () => void
  // Compact mode (used inside a Series detail): hides the Actualizado and
  // Acciones columns.
  compact?: boolean
  // Above-the-fold rows (top of the list on initial load) — eager + high
  // fetch priority so their poster is already there instead of popping in
  // as the browser's own lazy-load catches up.
  priority?: boolean
  // Avisa al desplegar y plegar. La lista de Biblioteca solo pinta las filas
  // que se ven (FilasVirtuales), y así mantiene montada una serie desplegada
  // aunque salga de la pantalla: dentro guarda sus temporadas y su página.
  onExpandedChange?: (id: number, expanded: boolean) => void
  // «Subir por lotes»: con `onAlternar`, una película lleva su casilla dentro de la celda del título (sin columna
  // nueva). Va un booleano y una función estable, nunca la selección entera: rompería el memo de cada fila. No se
  // pasa a las hijas (solo las películas se marcan) ni desde la ficha (LibraryChildrenSection).
  seleccionado?: boolean
  loteLleno?: boolean
  onAlternar?: (item: LibraryItemResponse) => void
}

// Series -> Season -> Episode collapsible tree, one row per level, reused
// as-is in the list view, the small detail modal (for a selected Series),
// and the large "Serr-style" detail card. Series/season rows are rollup
// entities with no file of their own, so their Nomenclatura/Campos/Subir
// buttons are placeholders here — the batch action wiring for them lands
// in Phase 6; showing them disabled-with-explanation now avoids calling
// single-item endpoints with a rollup id that would error.
// "¿En eMuwarez?" — badge (same visual format as Estado/Nomenclatura):
// "No" = not on the tracker (an upload opportunity, green), "Sí" = already
// there (neutral gray), — = catalog not synced yet.
export function EmuStatusCell({ item }: { item: LibraryItemResponse }) {
  if (item.emu_in_catalog == null) {
    return <span className="bib-guion bib-guion-12">—</span>
  }
  // 0 = No, 1 = Sí, 2 = Parcial (series with some seasons on eMuwarez, some not).
  const status = item.emu_in_catalog === 0 ? 'No' : item.emu_in_catalog === 2 ? 'Parcial' : 'Sí'
  return <StatusBadge status={status} type="emu" />
}

// Castellano en el audio, en los subtítulos, en los dos o en ninguno (ver
// utils/castellano). El guion es un estado de verdad, no un hueco de estilo:
// un capítulo cuyo MediaInfo no se ha leído, un Faltante que no está en disco,
// o un archivo del que no se puede sacar nada. Enseñarlo como "No" sería
// afirmar algo que nadie ha comprobado, y es justo lo que uno miraría para
// decidir si lo vuelve a descargar.
export function SpanishAudioCell({ item }: { item: LibraryItemResponse }) {
  const estado = estadoCastellano(item)
  if (estado === 'desconocido') {
    return <span className="bib-guion bib-guion-12">—</span>
  }
  const { label, cssClass } = CASTELLANO_INFO[estado]
  return <span className={`badge ${cssClass}`}>{label}</span>
}

// Memoized: the list can hold hundreds of rows, and typing in the title
// search box (LibraryPage's own `search` state) used to re-render every one
// of them on every keystroke even though their own props hadn't changed —
// this (plus onSelect/onAction/onReload staying referentially stable at the
// call site) is what makes that skip actually happen.
export const LibraryTreeRow = memo(function LibraryTreeRow({ item, depth, instances, onSelect, onAction, onReload, compact = false, priority = false, onExpandedChange, seleccionado = false, loteLleno = false, onAlternar }: LibraryTreeRowProps) {
  const [expanded, setExpanded] = useState(false)
  const [children, setChildren] = useState<LibraryItemResponse[]>([])
  const [childTotal, setChildTotal] = useState(0)
  const [childOffset, setChildOffset] = useState(0)
  const [loadingChildren, setLoadingChildren] = useState(false)
  const [errorHijos, setErrorHijos] = useState(false)
  const hijosVistos = useRef(0)
  hijosVistos.current = children.length
  // Solo vale la última petición de hijos: pulsar «Siguiente» varias veces seguidas lanza varias.
  const ultimaCargaHijos = useRef(0)
  const deepLink = buildDeepLink(item, instances)
  const { triggerProps: titleTip, tooltipNode: titleTooltip } = useTooltip('Abrir ficha')
  const { triggerProps: expandTip, tooltipNode: expandTooltip } = useTooltip(expanded ? 'Ocultar' : 'Desplegar')

  // Desmontada desplegada (un filtro la ha quitado de la lista): que la lista
  // deje de tenerla por abierta, o la seguiría pintando fuera de la vista.
  const expandedRef = useRef(expanded)
  expandedRef.current = expanded
  useEffect(() => () => {
    if (expandedRef.current) onExpandedChange?.(item.id, false)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al desmontar; lee expanded por la ref
  }, [])

  const isSeries = item.item_type === 'series'
  const isSeason = item.item_type === 'season'
  const expandable = isSeries || isSeason              // has children to load
  // Episodes are leaf rows: no dropdown — their title opens their own detail
  // card, which is where you consult their data.
  const canExpand = expandable
  const childType = isSeries ? 'season' : 'episode'

  // `porDetras`: refresca lo que ya se ve sin cambiarlo por «Cargando…»; si falla se queda lo de antes.
  const loadChildren = useCallback(async (off: number, porDetras = false) => {
    const esta = ++ultimaCargaHijos.current
    if (!porDetras) {
      setLoadingChildren(true)
      setErrorHijos(false)
    }
    try {
      const result = await getLibrary({
        parent_id: item.id,
        type: childType,
        limit: isSeries ? MAX_SEASONS_PER_SERIES : NESTED_PAGE_SIZE,
        offset: isSeries ? 0 : off,
      })
      if (esta !== ultimaCargaHijos.current) return
      setChildren(result.items)
      setChildTotal(result.total)
      setChildOffset(off)
      setErrorHijos(false)
    } catch {
      if (esta !== ultimaCargaHijos.current) return
      // Una recarga por detrás que falla deja lo que ya se ve; sin nada que ver, es un error como otro.
      if (porDetras && hijosVistos.current > 0) return
      setChildren([])
      setChildTotal(0)
      setErrorHijos(true)
    } finally {
      if (esta === ultimaCargaHijos.current) setLoadingChildren(false)
    }
  }, [item.id, childType, isSeries])

  // La lista se recarga (sincronización, filtro, acción) y trae la fila nueva: lo desplegado se refresca,
  // porque la fila sigue montada con sus temporadas o capítulos de antes.
  const paginaDeHijos = useRef(0)
  paginaDeHijos.current = childOffset
  useEffect(() => {
    if (expandedRef.current && expandable) loadChildren(paginaDeHijos.current, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo cuando llega la fila nueva; expanded y la página van por refs
  }, [item])

  function toggle() {
    if (expanded) {
      setExpanded(false)
      onExpandedChange?.(item.id, false)
      return
    }
    setExpanded(true)
    onExpandedChange?.(item.id, true)
    // Only series/season load child rows; an episode just reveals its own
    // inline detail panel (no children to fetch).
    if (expandable && children.length === 0) loadChildren(0)
  }

  const indent = depth * 20
  const colSpan = compact ? 6 : 7

  return (
    <>
      <tr className={canExpand ? 'clickable bib-fila' : 'bib-fila'} onClick={canExpand ? toggle : undefined}>
        <td className="bib-celda-titulo">
          {/* La sangría depende de la profundidad: se queda en línea. */}
          <div className="bib-titulo-fila" style={{ paddingLeft: indent }}>
            {onAlternar && item.item_type === 'movie' && (
              <CasillaLote item={item} seleccionado={seleccionado} bloqueada={loteLleno} onAlternar={onAlternar} />
            )}
            {canExpand ? (
              // Sin recuadro: el triángulo se ilumina él solo al pasar por
              // encima (.tree-expander). Un botón con caja aquí competía
              // visualmente con la carátula que tiene al lado.
              <button
                type="button"
                className="tree-expander"
                onClick={e => { e.stopPropagation(); toggle() }}
                aria-label={expanded ? 'Ocultar' : 'Desplegar'}
                {...expandTip}
              >
                <IconoDesplegar abierto={expanded} size={12} />
                {expandTooltip}
              </button>
            ) : item.item_type === 'episode' && item.episode_number != null ? (
              // Episodes use the chevron's slot to show their episode number.
              <span className="bib-num-episodio">
                {item.episode_number}
              </span>
            ) : depth > 0 ? (
              // Una fila hoja ANIDADA sí reserva el hueco del triángulo, para
              // quedar un nivel más adentro que su padre.
              <span className="bib-hueco-triangulo" />
            ) : null}
            <div className="poster-thumb bib-miniatura">
              {item.poster_url ? (
                <img
                  src={posterUrl(item.poster_url, 'w154')}
                  alt=""
                  loading={priority ? 'eager' : 'lazy'}
                  fetchPriority={priority ? 'high' : 'auto'}
                  className="bib-tarjeta-img"
                  onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
                />
              ) : (
                <span className="bib-miniatura-icono">
                  <IconoTipo serie={item.item_type === 'series' || item.item_type === 'episode'} />
                </span>
              )}
            </div>
            <div className="bib-titulo-caja">
              <div className="bib-titulo-cab">
                <div
                  className="lib-title-link bib-titulo-enlace"
                  onClick={e => { e.stopPropagation(); onSelect(item) }}
                  {...titleTip}
                >
                  <DetailTitleText title={listDisplayTitle(item)} />
                  {titleTooltip}
                </div>
                <GrupoDeLaFila item={item} />
              </div>
              <LineaDeCalidad item={item} deepLink={deepLink} />
            </div>
          </div>
        </td>
        <td><StatusBadge status={item.local_status} type="local" /></td>
        <td><StatusBadge status={item.request_status} type="request" /></td>
        <td className="bib-nowrap"><SpanishAudioCell item={item} /></td>
        <td className="bib-nowrap"><EmuStatusCell item={item} /></td>
        <td className="bib-nowrap">
          {item.size_bytes
            ? <ValueChip><ValueIcon><SizeValueIcon /></ValueIcon><span className="txt">{formatBytes(item.size_bytes)}</span></ValueChip>
            : <span className="bib-guion">—</span>}
        </td>
        {!compact && (
          <td className="col-actions" onClick={e => e.stopPropagation()}>
            <div className="bib-acciones-fila">
              {/* Same multi-season wizard the series' own page opens: the
                  two used to disagree, and "Subir" on a series meaning two
                  different things depending on where you clicked it was the
                  bug, not the feature. */}
              <LibraryActionButtons item={item} onAction={onAction} soloIcono />
            </div>
          </td>
        )}
      </tr>
      {expanded && loadingChildren && (
        <tr>
          <td colSpan={colSpan} className="bib-aviso">
            Cargando…
          </td>
        </tr>
      )}
      {expanded && !loadingChildren && errorHijos && (
        <tr>
          <td colSpan={colSpan} className="bib-aviso" style={{ paddingLeft: indent + 20 }}>
            No se pudo cargar{' '}
            <button type="button" className="btn btn-secondary btn-sm" onClick={e => { e.stopPropagation(); loadChildren(childOffset) }}>
              Reintentar
            </button>
          </td>
        </tr>
      )}
      {expanded && !loadingChildren && !errorHijos && children.length === 0 && (
        <tr>
          <td colSpan={colSpan} className="bib-aviso" style={{ paddingLeft: indent + 20 }}>
            Sin {childType === 'season' ? 'temporadas' : 'episodios'}
          </td>
        </tr>
      )}
      {expanded && !loadingChildren && children.map(child => (
        <LibraryTreeRow
          key={child.id}
          item={child}
          depth={depth + 1}
          instances={instances}
          onSelect={onSelect}
          onAction={onAction}
          onReload={onReload}
          compact={compact}
        />
      ))}
      {expanded && !loadingChildren && !isSeries && childTotal > NESTED_PAGE_SIZE && (
        <tr>
          <td colSpan={colSpan} className="bib-paginacion">
            <div className="bib-paginacion-fila" style={{ paddingLeft: indent }}>
              <button
                className="btn btn-secondary btn-sm"
                disabled={childOffset === 0}
                onClick={() => loadChildren(Math.max(0, childOffset - NESTED_PAGE_SIZE))}
              >
                Anterior
              </button>
              <span className="bib-paginacion-cuenta">
                {Math.floor(childOffset / NESTED_PAGE_SIZE) + 1} / {Math.ceil(childTotal / NESTED_PAGE_SIZE)}
              </span>
              <button
                className="btn btn-secondary btn-sm"
                disabled={childOffset + NESTED_PAGE_SIZE >= childTotal}
                onClick={() => loadChildren(childOffset + NESTED_PAGE_SIZE)}
              >
                Siguiente
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  )
})
