// Pack de temporada: lo que se pide capítulo a capítulo al abrir «Ver nombre de
// todos los capítulos», «Ver MediaInfo» y «Ver Pistas».
import { useCallback, useEffect, useState, type MutableRefObject } from 'react'
import type { NomenclatureFields } from '../../api/nomenclature'
import {
  getSeasonEpisodeNames, getSeasonEpisodeMediaInfo, getSeasonEpisodeRemuxPreview,
  type SeasonEpisodeName, type SeasonEpisodeMediaInfo, type SeasonEpisodeRemux,
} from '../../api/seasonPack'
import { proveedorParaServidor, type ProveedoresElegidos } from '../../utils/origenProveedor'
import { idiomasParaServidor, type IdiomasPorPosicion } from '../../utils/idiomasPack'

export function useDetallesTemporada({
  targetId, targetIsSeason, objetivoActual, versionDatosPack, fields, proveedorElegido, idiomasPorTemporada,
  pistasAbiertas,
}: {
  targetId: number | null
  targetIsSeason: boolean
  // El objetivo vigente y la versión de los datos del pack (ver useAsistente):
  // una respuesta que llega cuando ya cambió alguno de los dos no se aplica.
  objetivoActual: MutableRefObject<number | null>
  versionDatosPack: MutableRefObject<number>
  fields: NomenclatureFields
  proveedorElegido: ProveedoresElegidos
  idiomasPorTemporada: ReadonlyMap<number, IdiomasPorPosicion>
  // «Ver Pistas» abierto (su estado lo comparte con el de un fichero suelto).
  pistasAbiertas: boolean
}) {
  // Season target — per-episode final names ("Ver nombre de todos los
  // capítulos"), on demand.
  const [seasonNames, setSeasonNames] = useState<SeasonEpisodeName[] | null>(null)
  const [seasonNamesLoading, setSeasonNamesLoading] = useState(false)
  const [showSeasonNamesCard, setShowSeasonNamesCard] = useState(false)
  // Capítulo elegido dentro de "Ver nombre de todos los capítulos": se navega
  // con un desplegable, igual que Ver MediaInfo, en vez de una lista de 25
  // bloques uno debajo de otro.
  const [seasonNamesEpisodeId, setSeasonNamesEpisodeId] = useState<number | null>(null)

  // Season target — per-episode MediaInfo/Remux (accordion, one entry per
  // episode), replacing the single-file "Ver MediaInfo"/"Ver Pistas" cards.
  const [seasonMi, setSeasonMi] = useState<SeasonEpisodeMediaInfo[] | null>(null)
  const [seasonMiLoading, setSeasonMiLoading] = useState(false)
  const [seasonMiError, setSeasonMiError] = useState<string | null>(null)
  // Capítulo que se está viendo dentro de la tarjeta: se navega con un
  // desplegable, igual que "Ver nombre de todos los capítulos", en vez de una
  // lista de 25 acordeones que obliga a bajar buscando el que interesa.
  const [miEpisodeId, setMiEpisodeId] = useState<number | null>(null)

  const [seasonRemux, setSeasonRemux] = useState<SeasonEpisodeRemux[] | null>(null)
  const [seasonRemuxLoading, setSeasonRemuxLoading] = useState(false)
  const [seasonRemuxError, setSeasonRemuxError] = useState<string | null>(null)
  const [remuxEpisodeId, setRemuxEpisodeId] = useState<number | null>(null)

  // Las cargas siguientes no tocan nada si, al llegar la respuesta, el
  // objetivo ya es otro: era la de un elemento que ya no se está viendo.
  const loadSeasonNames = useCallback(async () => {
    const id = targetId
    if (id == null) return
    const datos = versionDatosPack.current
    const vigente = () => objetivoActual.current === id && datos === versionDatosPack.current
    setSeasonNamesLoading(true)
    try {
      const overrides = {
        source: fields.source, provider: proveedorParaServidor(proveedorElegido, id) ?? fields.provider, tag: fields.tag,
        idiomas: idiomasParaServidor(idiomasPorTemporada.get(id)),
      }
      const r = await getSeasonEpisodeNames(id, overrides)
      if (vigente()) setSeasonNames(r.episodes)
    }
    catch { if (vigente()) setSeasonNames(null) }
    finally { if (vigente()) setSeasonNamesLoading(false) }
  }, [targetId, fields.source, fields.provider, fields.tag, proveedorElegido, idiomasPorTemporada, objetivoActual, versionDatosPack])

  const loadSeasonMi = useCallback(async () => {
    const id = targetId
    if (id == null) return
    setSeasonMiLoading(true); setSeasonMiError(null)
    try {
      const r = await getSeasonEpisodeMediaInfo(id)
      if (objetivoActual.current === id) setSeasonMi(r.episodes)
    }
    catch (e: unknown) {
      if (objetivoActual.current === id) { setSeasonMi(null); setSeasonMiError(e instanceof Error ? e.message : 'Error cargando MediaInfo') }
    }
    finally { if (objetivoActual.current === id) setSeasonMiLoading(false) }
  }, [targetId, objetivoActual])

  const loadSeasonRemux = useCallback(async () => {
    const id = targetId
    if (id == null) return
    const datos = versionDatosPack.current
    const vigente = () => objetivoActual.current === id && datos === versionDatosPack.current
    setSeasonRemuxLoading(true); setSeasonRemuxError(null)
    try {
      const r = await getSeasonEpisodeRemuxPreview(id, idiomasParaServidor(idiomasPorTemporada.get(id)))
      if (vigente()) setSeasonRemux(r.episodes)
    }
    catch (e: unknown) {
      if (vigente()) { setSeasonRemux(null); setSeasonRemuxError(e instanceof Error ? e.message : 'Error calculando el remux') }
    }
    finally { if (vigente()) setSeasonRemuxLoading(false) }
  }, [targetId, idiomasPorTemporada, objetivoActual, versionDatosPack])

  // Otro objetivo, otros capítulos: se descarta lo cargado del anterior.
  useEffect(() => {
    setSeasonNames(null); setShowSeasonNamesCard(false); setSeasonNamesLoading(false)
    setSeasonMi(null); setSeasonMiError(null); setMiEpisodeId(null); setSeasonMiLoading(false)
    setSeasonRemux(null); setSeasonRemuxError(null); setRemuxEpisodeId(null); setSeasonRemuxLoading(false)
  }, [targetId])

  // Season target: invalidate the cached per-episode names list whenever
  // Source/Proveedor/Tag change, so a stale (pre-edit) list isn't shown next
  // time "Ver nombre de todos los capítulos" is reopened — it must always
  // reflect the same override the season pack's own title uses.
  useEffect(() => {
    if (!targetIsSeason) return
    setSeasonNames(null)
  }, [targetIsSeason, fields.source, fields.provider, fields.tag])

  // Los nombres y las pistas por capítulo ya no valen tras cambiar el idioma
  // del pack: cerrados se piden al abrirlos; abiertos, en el efecto de abajo.
  const [idiomaCambiado, setIdiomaCambiado] = useState(0)
  const olvidarPorIdioma = () => {
    versionDatosPack.current++
    setSeasonNames(null); setSeasonNamesLoading(false)
    setSeasonRemux(null); setSeasonRemuxLoading(false)
    setIdiomaCambiado(n => n + 1)
  }
  // Tras el render con el idioma confirmado, para que la carga ya lo lleve.
  useEffect(() => {
    if (!idiomaCambiado) return
    if (showSeasonNamesCard) loadSeasonNames()
    if (pistasAbiertas) loadSeasonRemux()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idiomaCambiado])

  return {
    seasonNames, seasonNamesLoading, showSeasonNamesCard, setShowSeasonNamesCard,
    seasonNamesEpisodeId, setSeasonNamesEpisodeId, loadSeasonNames,
    seasonMi, seasonMiLoading, seasonMiError, miEpisodeId, setMiEpisodeId, loadSeasonMi,
    seasonRemux, seasonRemuxLoading, seasonRemuxError, remuxEpisodeId, setRemuxEpisodeId, loadSeasonRemux,
    olvidarPorIdioma,
  }
}
