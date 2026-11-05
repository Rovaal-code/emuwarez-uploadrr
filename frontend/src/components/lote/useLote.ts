// Lo que el Resumen de «Subir por lotes» mira de cada película además de las comprobaciones previas: el nombre
// del torrent que saldría, los avisos de ese nombre y lo que el catálogo local de eMuwarez ya tiene de lo mismo.
import { useEffect, useState } from 'react'
import { getEmuComparison, suggestProvider } from '../../api/library'
import { getNomenclatureFields, previewNomenclatureFields, type NomenclatureFields } from '../../api/nomenclature'
import { fetchSettings } from '../../api/settings'
import { conclusionDuplicados, resumirComparaciones, type NivelDuplicado } from '../../utils/resumenSubida'
import { PROVIDER_SOURCES } from '../asistente/constantes'

export interface AnalisisPelicula {
  // El nombre del torrent que saldría; null si no se pudo generar.
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
export async function analizarPelicula(id: number): Promise<AnalisisPelicula> {
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
  const comparacion = await getEmuComparison(id, { resolution: fields.resolution, source: fields.source }).catch(() => null)
  const yaHay = resumirComparaciones([comparacion])
  const conclusion = yaHay.estado === 'listo' ? conclusionDuplicados(yaHay.filas) : null
  return {
    nombre, bloqueo: null, avisos, sinIdioma: !!r.audio_warning, campos,
    nivel: conclusion?.nivel ?? null, enEmu: conclusion?.texto ?? textoSinConclusion(yaHay.estado),
  }
}

/**
 * El análisis de cada película del lote, de una en una (son peticiones locales, pero cada una abre el fichero),
 * mientras `activo`. Lo ya analizado se guarda: volver al paso 1 sin cambiar nada no lo repite.
 */
export function useAnalisisLote({ activo, ids }: { activo: boolean; ids: readonly number[] }) {
  const [analisis, setAnalisis] = useState<ReadonlyMap<number, AnalisisPelicula>>(() => new Map())
  const [analizando, setAnalizando] = useState(false)
  const [intento, setIntento] = useState(0)
  const clave = ids.join(',')

  useEffect(() => {
    if (!activo) return
    const faltan = ids.filter(id => !analisis.has(id))
    if (faltan.length === 0) return
    let vivo = true
    setAnalizando(true)
    const run = async () => {
      for (const id of faltan) {
        const resultado = await analizarPelicula(id)
        // Una pasada abandonada (otra selección, otro paso) no apunta lo que ya no se mira.
        if (!vivo) return
        setAnalisis(prev => new Map(prev).set(id, resultado))
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
  const completo = ids.every(id => analisis.has(id))
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
