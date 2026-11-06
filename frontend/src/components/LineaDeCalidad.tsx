import type { LibraryItemResponse } from '../types/api'
import { formatItemType } from '../utils/format'
import { GruposDeRelease, gruposDeRelease } from './GruposDeRelease'

/** Lo que dice la línea bajo el título, en orden: lo que ninguna columna filtra (tipo, códec e idiomas del audio). */
export function especificaciones(item: LibraryItemResponse): string[] {
  return [formatItemType(item.item_type), item.video_codec, item.audio_languages].filter((p): p is string => !!p)
}

/** El grupo de release de la columna «Grupo»; sin él, «sin grupo». */
export function GrupoDeLaFila({ item }: { item: LibraryItemResponse }) {
  const grupos = gruposDeRelease(item)
  return grupos.length > 0
    ? <GruposDeRelease grupos={grupos} junto plano />
    : <span className="bib-rg-ninguno">sin grupo</span>
}

/** Una línea bajo el título con lo que no se filtra. */
export function LineaDeCalidad({ item }: { item: LibraryItemResponse }) {
  const texto = especificaciones(item).join(' · ')
  return (
    <div className="bib-spec">
      <span className="bib-spec-texto" title={texto}>{texto}</span>
    </div>
  )
}
