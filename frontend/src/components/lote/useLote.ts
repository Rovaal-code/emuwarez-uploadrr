// Lo que «Subir por lotes» mira además de las comprobaciones previas. En el paso 1, las temporadas de cada serie
// marcada. En el Resumen, de cada película el nombre del torrent que saldría y los avisos de ese nombre, y de cada
// película o temporada lo que el catálogo local de eMuwarez ya tiene de lo mismo (el nombre de un pack lo dan sus
// comprobaciones, `nombre` en runUploadChecks).
import { useEffect, useState } from 'react'
import { getEmuComparison, getLibrary, suggestProvider } from '../../api/library'
import { getNomenclatureFields, previewNomenclatureFields, type NomenclatureFields } from '../../api/nomenclature'
import { fetchSettings } from '../../api/settings'
import type { LibraryItemResponse } from '../../types/api'
import { expandirEntradas, razonNoSubible, type EntradaLote } from '../../utils/lote'
import { conclusionDuplicados, resumirComparaciones, type NivelDuplicado } from '../../utils/resumenSubida'
import { PROVIDER_SOURCES } from '../asistente/constantes'

export interface AnalisisElemento {
  // El nombre del torrent que saldría; null si no se pudo generar (y en una temporada, que lo dan sus comprobaciones).
  nombre: string | null
  // Por qué no se puede subir así (nomenclatura bloqueada, o no se pudo calcular): se salta.
  bloqueo: string | null
  // Los avisos del nombre que el asistente deja corregir y el lote no.
  avisos: string[]
  // Una pista de audio sin idioma: el nombre no la incluye. Llega desmarcada.
  sinIdioma: boolean
  // El juego completo de campos con el proveedor sugerido, para que el servidor lo guarde; null si no se sugirió.
  campos: NomenclatureFields | null
  // «En eMuwarez»: el nivel de `conclusionDuplicados` (null: nada con lo que comparar) y la frase.
  nivel: NivelDuplicado | null
  enEmu: string
}

const mensaje = (e: unknown, defecto: string) => (e instanceof Error && e.message ? e.message : defecto)

function textoSinConclusion(estado: 'error' | 'sin-catalogo' | 'listo' | 'cargando'): string {
  if (estado === 'error') return 'No se pudo consultar el catálogo local.'
  if (estado === 'sin-catalogo') return 'Sin catálogo de eMuwarez: sincronízalo para comparar.'
  return 'No hay nada igual en eMuwarez.'
}

/** Una película, paso a paso. No lanza: lo que falla queda dicho en el resultado. */
export async function analizarPelicula(id: number): Promise<AnalisisElemento> {
  let r: Awaited<ReturnType<typeof getNomenclatureFields>>
  try {
    r = await getNomenclatureFields(id)
  } catch (e) {
    return {
      nombre: null, bloqueo: `No se pudo calcular el nombre: ${mensaje(e, 'error desconocido')}`, avisos: [],
      sinIdioma: false, campos: null, nivel: null, enEmu: '—',
    }
  }
  if (r.blocked) {
    return {
      nombre: null, bloqueo: r.error || 'La nomenclatura está bloqueada.', avisos: [], sinIdioma: false,
      campos: null, nivel: null, enEmu: '—',
    }
  }
  let nombre: string | null = r.torrent_name || null
  let campos: NomenclatureFields | null = null
  const avisos = [r.audio_warning, r.source_mismatch_warning, r.title_warning].filter((a): a is string => !!a)

  // WEB-DL sin proveedor: el que sugiere TMDb, como el asistente. Se manda el juego completo para que el servidor
  // lo guarde igual que «Guardar campos», y el nombre que se enseña es ya el que lo lleva.
  if (PROVIDER_SOURCES.has(r.fields.source || '') && !r.fields.provider) {
    const sugerido = await suggestProvider(id).then(s => s.suggested).catch(() => null)
    if (sugerido) {
      campos = { ...r.fields, provider: sugerido }
      nombre = await previewNomenclatureFields(id, campos, false).then(p => p.torrent_name || nombre).catch(() => nombre)
    } else {
      avisos.push('WEB-DL sin proveedor: el nombre irá sin él.')
    }
  }

  const fields = campos ?? r.fields
  const enEmu = await enEmuwarez(id, { resolution: fields.resolution, source: fields.source })
  return { nombre, bloqueo: null, avisos, sinIdioma: !!r.audio_warning, campos, ...enEmu }
}

/** Lo que ya hay en eMuwarez de lo mismo; `tuya`, lo que irá en el nombre (como el Resumen del asistente). */
async function enEmuwarez(
  id: number, tuya?: { resolution?: string | null; source?: string | null },
): Promise<Pick<AnalisisElemento, 'nivel' | 'enEmu'>> {
  const comparacion = await getEmuComparison(id, tuya).catch(() => null)
  const yaHay = resumirComparaciones([comparacion])
  const conclusion = yaHay.estado === 'listo' ? conclusionDuplicados(yaHay.filas) : null
  return { nivel: conclusion?.nivel ?? null, enEmu: conclusion?.texto ?? textoSinConclusion(yaHay.estado) }
}

/**
 * Una temporada (un pack): solo lo que hay en eMuwarez, comparado con lo que tienes, como hace el asistente con una
 * tanda de temporadas. Su nombre, su bloqueo y su proveedor salen de sus comprobaciones (el plan del pack).
 */
export async function analizarTemporada(id: number): Promise<AnalisisElemento> {
  const enEmu = await enEmuwarez(id)
  return { nombre: null, bloqueo: null, avisos: [], sinIdioma: false, campos: null, ...enEmu }
}

/**
 * El análisis de cada elemento del lote, de uno en uno (son peticiones locales, pero cada película abre el
 * fichero), mientras `activo`. Lo ya analizado se guarda: volver al paso 1 sin cambiar nada no lo repite.
 */
export function useAnalisisLote({ activo, elementos }: { activo: boolean; elementos: readonly LibraryItemResponse[] }) {
  const [analisis, setAnalisis] = useState<ReadonlyMap<number, AnalisisElemento>>(() => new Map())
  const [analizando, setAnalizando] = useState(false)
  const [intento, setIntento] = useState(0)
  const clave = elementos.map(e => e.id).join(',')

  useEffect(() => {
    if (!activo) return
    const faltan = elementos.filter(e => !analisis.has(e.id))
    if (faltan.length === 0) return
    let vivo = true
    setAnalizando(true)
    const run = async () => {
      for (const e of faltan) {
        const resultado = e.item_type === 'season' ? await analizarTemporada(e.id) : await analizarPelicula(e.id)
        // Una pasada abandonada (otra selección, otro paso) no apunta lo que ya no se mira.
        if (!vivo) return
        setAnalisis(prev => new Map(prev).set(e.id, resultado))
      }
      if (vivo) setAnalizando(false)
    }
    run()
    return () => { vivo = false; setAnalizando(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- se relanza al cambiar lo que se mira, no con cada resultado
  }, [activo, clave, intento])

  // Otra selección: el nombre y lo que hay en eMuwarez se vuelven a mirar.
  const olvidar = () => setAnalisis(new Map())
  // «Volver a comprobar»: repite lo que no se pudo calcular (lo bloqueado de verdad también, por si se arregló).
  const repetir = () => {
    setAnalisis(prev => new Map([...prev].filter(([, a]) => !a.bloqueo)))
    setIntento(n => n + 1)
  }

  // Mientras no estén todas, «Subir» no se habilita aunque el efecto aún no haya arrancado.
  const completo = elementos.every(e => analisis.has(e.id))
  return { analisis, analizando: analizando || (activo && !completo), olvidar, repetir }
}

/** «Subidas en paralelo» de Ajustes, para decir de cuántas en cuántas irá el lote; null si no se pudo leer. */
export function useSubidasEnParalelo() {
  const [paralelo, setParalelo] = useState<number | null>(null)
  useEffect(() => {
    let vivo = true
    fetchSettings().then(s => { if (vivo) setParalelo(s.upload_max_concurrent) }).catch(() => {})
    return () => { vivo = false }
  }, [])
  return paralelo
}

export interface ExpansionLote {
  // Lo que entra en el paso 1, con cada serie cambiada por sus temporadas; null mientras se cargan.
  elementos: LibraryItemResponse[] | null
  // Las que llegan marcadas: las que se pueden subir, hasta el tope del lote (cuenta después de expandir).
  iniciales: ReadonlySet<number>
  // Desde el Panel: las peticiones que cubre cada elemento (la primera es la que se enlaza si no se elige otra).
  peticiones: ReadonlyMap<number, readonly number[]>
  // Cuántas series hay que expandir y cuántas van.
  series: number
  hechas: number
  // Una serie sin temporadas o que no se pudo cargar, o una petición cuya temporada o capítulo no está.
  avisos: string[]
}

type Expandido = Pick<ExpansionLote, 'elementos' | 'iniciales' | 'peticiones' | 'avisos'>

/**
 * El paso 1: cada serie marcada, cambiada por sus temporadas (como el asistente, `getLibrary` con `parent_id`), de
 * una en una para poder decir cuántas van. `entradas` es la copia tomada al abrir: no cambia. Una serie que llega
 * dos veces (dos peticiones de temporadas distintas) se carga una vez.
 */
export function useExpansionLote(entradas: readonly EntradaLote[], maximo: number): ExpansionLote {
  const series = [...new Map(
    entradas.filter(e => e.item.item_type === 'series').map(e => [e.item.id, e.item] as const),
  ).values()]
  const [hechas, setHechas] = useState(0)
  const [resultado, setResultado] = useState<Expandido>(() => (
    series.length === 0
      ? listo(entradas, new Map(), [], maximo)
      : { elementos: null, iniciales: new Set(), peticiones: new Map(), avisos: [] }
  ))

  useEffect(() => {
    if (series.length === 0) return
    let vivo = true
    setHechas(0)
    const run = async () => {
      const temporadas = new Map<number, LibraryItemResponse[]>()
      const avisos: string[] = []
      for (const serie of series) {
        try {
          const r = await getLibrary({ parent_id: serie.id, type: 'season', limit: 500 })
          if (!vivo) return
          temporadas.set(serie.id, r.items)
          if (r.items.length === 0) avisos.push(`«${serie.title}» no tiene temporadas en la biblioteca.`)
        } catch (e: unknown) {
          if (!vivo) return
          avisos.push(`No se pudieron cargar las temporadas de «${serie.title}»: ${mensaje(e, 'error desconocido')}`)
        }
        setHechas(n => n + 1)
      }
      if (vivo) setResultado(listo(entradas, temporadas, avisos, maximo))
    }
    run()
    return () => { vivo = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- una vez: la selección es la copia tomada al abrir
  }, [])

  return { ...resultado, series: series.length, hechas }
}

function listo(
  entradas: readonly EntradaLote[], temporadas: ReadonlyMap<number, readonly LibraryItemResponse[]>,
  avisos: string[], maximo: number,
): Expandido {
  const expandido = expandirEntradas(entradas, temporadas)
  const iniciales = new Set(expandido.elementos.filter(e => !razonNoSubible(e)).slice(0, maximo).map(e => e.id))
  return {
    elementos: expandido.elementos, iniciales, peticiones: expandido.peticiones,
    avisos: [...avisos, ...expandido.avisos],
  }
}
