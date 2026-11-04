import type { LibraryItemResponse } from '../types/api'
import { formatItemType } from '../utils/format'
import { GruposDeRelease, gruposDeRelease } from './GruposDeRelease'
import { ServiceLabel } from './ServiceIcon'
import { useTooltip } from './Tooltip'

/** Lo que dice la línea bajo el título, en orden: tipo, resolución, source, proveedor, códec e idiomas del audio. */
export function especificaciones(item: LibraryItemResponse): string[] {
  return [
    formatItemType(item.item_type),
    item.resolution,
    item.source,
    item.provider_label ?? item.provider,
    item.video_codec,
    item.audio_languages,
  ].filter((p): p is string => !!p)
}

/** El grupo de release, en una insignia al final de la línea del título; sin él, «sin grupo». */
export function GrupoDeLaFila({ item }: { item: LibraryItemResponse }) {
  const grupos = gruposDeRelease(item)
  return grupos.length > 0
    ? <span className="bib-rg"><GruposDeRelease grupos={grupos} junto /></span>
    : <span className="bib-rg bib-rg-ninguno">sin grupo</span>
}

/** Una línea bajo el título: las especificaciones en texto y el origen. */
export function LineaDeCalidad({ item, deepLink }: { item: LibraryItemResponse; deepLink: string | null }) {
  const partes = especificaciones(item)
  const nombreOrigen = item.instance_name ?? item.instance_type ?? ''
  const { triggerProps: origenTip, tooltipNode: origenTooltip } = useTooltip(deepLink ? `Abrir en ${nombreOrigen}` : null)
  return (
    <div className="bib-spec">
      <span className="bib-spec-texto" title={partes.join(' · ')}>
        {partes.join(' · ')}
      </span>
      {item.instance_type && (deepLink
        ? <a className="hover-link bib-spec-origen" href={deepLink} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} {...origenTip}><ServiceLabel type={item.instance_type} label={nombreOrigen} size={12} />{origenTooltip}</a>
        : <span className="bib-spec-origen"><ServiceLabel type={item.instance_type} label={nombreOrigen} size={12} /></span>)}
    </div>
  )
}
