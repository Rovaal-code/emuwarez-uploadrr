// El nombre del torrent de cada capítulo de una tanda, para el Resumen. Se calcula con los mismos campos que «Subir
// todos» guardará (lo generado más lo editado), con la vista previa barata de la nomenclatura. Las temporadas no pasan
// por aquí: su nombre llega con las comprobaciones (`nombre` de runUploadChecks).
import { useEffect, useState } from 'react'
import { previewNomenclatureFields, type NomenclatureFields } from '../../api/nomenclature'

// undefined: aún se calcula; null: no se pudo (nomenclatura bloqueada o la petición falló).
export type NombresTanda = ReadonlyMap<number, string | null>

export function useNombresTanda({ activo, ids, camposDe }: {
  activo: boolean
  ids: readonly number[]
  // Los campos con los que se subirá ese capítulo; null si su nomenclatura está bloqueada o no se generó.
  camposDe: (id: number) => NomenclatureFields | null
}) {
  const [nombres, setNombres] = useState<NombresTanda>(new Map())
  const clave = ids.join(',')

  useEffect(() => {
    if (!activo || ids.length === 0) return
    let vivo = true
    setNombres(new Map())
    ids.forEach(async id => {
      const campos = camposDe(id)
      let nombre: string | null = null
      if (campos) {
        try { nombre = (await previewNomenclatureFields(id, campos, false)).torrent_name || null } catch { nombre = null }
      }
      if (vivo) setNombres(prev => new Map(prev).set(id, nombre))
    })
    return () => { vivo = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- se calcula al entrar en el paso o cambiar la tanda; lo editado ya no cambia dentro del paso
  }, [activo, clave])

  return nombres
}
