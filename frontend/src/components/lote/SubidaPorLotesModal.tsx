// «Subir por lotes»: varias películas y temporadas (packs) de Biblioteca, o lo marcado en «Listo para subir» del
// Panel (con la petición de cada fila y, si la petición es de un capítulo, ese capítulo), encoladas de una vez, con
// el nombre que genere la nomenclatura para cada una (sin editar: para eso está el asistente). Una serie marcada
// entra como sus temporadas. Paso 1, qué entra; paso 2, el resumen de cada una y las comprobaciones (las del entorno una sola
// vez); «Subir N» manda el lote al servidor (POST /uploads/lote), que encola cada una en este orden y salta la que
// no pueda con su motivo.
import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiClientError } from '../../api/client'
import { queueLote, type LoteEncolado } from '../../api/uploads'
import type { LibraryItemResponse } from '../../types/api'
import {
  CLAVE_ABRIR_LOTE, MAX_ELEMENTOS_LOTE, marcadaPorDefecto, nombresRepetidos, razonNoSubible, type EntradaLote,
} from '../../utils/lote'
import type { ProveedoresElegidos } from '../../utils/origenProveedor'
import { useComprobacionesTanda } from '../asistente/useComprobaciones'
import { Modal } from '../Modal'
import { PasoContenidoLote } from './PasoContenidoLote'
import { PasoResumenLote, primerFallo, type FilaResumenLote } from './PasoResumenLote'
import { useAnalisisLote, useExpansionLote, useSubidasEnParalelo } from './useLote'

// Nadie elige proveedor en un lote: el de una película va en `campos`, y el de un pack lo decide su plan como en
// el asistente sin tocar Proveedor (el nombre de los capítulos o TMDb). Con proveedores distintos el pack se salta.
const SIN_ELECCION: ProveedoresElegidos = new Map()

// El check del pack falla así cuando sus capítulos traen proveedores distintos: elegir uno es cosa del asistente.
const CONFLICTO_PROVEEDOR = /proveedores distintos/i

const PASOS = [{ paso: 'contenido', nombre: 'Contenido' }, { paso: 'resumen', nombre: 'Resumen' }] as const
type Paso = (typeof PASOS)[number]['paso']

function motivosDelRechazo(e: ApiClientError): string[] {
  const detalle = (e.body as { detail?: unknown } | null)?.detail
  return Array.isArray(detalle) && detalle.length ? detalle.map(String) : [e.message]
}

export function SubidaPorLotesModal({ entradas, onClose, onDone, onNavigate }: {
  // Lo marcado en Biblioteca (películas, series y temporadas) o en el Panel (con su petición y su alcance). Se copia
  // al abrir: salir de la sección limpia la selección de origen.
  entradas: readonly EntradaLote[]
  onClose: () => void
  // En cuanto el servidor encola alguna: limpia la selección (también si luego se cierra con Escape).
  onDone?: () => void
  onNavigate?: (page: string) => void
}) {
  const [copia] = useState(() => [...entradas])
  const expansion = useExpansionLote(copia, MAX_ELEMENTOS_LOTE)
  const elementos = useMemo(() => expansion.elementos ?? [], [expansion.elementos])
  const [paso, setPaso] = useState<Paso>('contenido')
  // Lo cambiado a mano en el paso 1; hasta entonces, las que llegan marcadas al expandir.
  const [marcadasAMano, setMarcadasAMano] = useState<ReadonlySet<number> | null>(null)
  const marcadas = marcadasAMano ?? expansion.iniciales
  // Dos peticiones sobre el mismo elemento: la elegida a mano; si no, la primera.
  const [peticionElegida, setPeticionElegida] = useState<ReadonlyMap<number, number>>(() => new Map())
  const peticionDe = (id: number): number | undefined => peticionElegida.get(id) ?? expansion.peticiones.get(id)?.[0]
  const enCola = useMemo(
    () => elementos.filter(e => marcadas.has(e.id) && !razonNoSubible(e)),
    [elementos, marcadas],
  )
  const cola = useMemo(() => enCola.map(e => e.id), [enCola])
  const [fase, setFase] = useState<'idle' | 'processing' | 'done'>('idle')
  // Lo que se cambió a mano en «Incluir»; lo demás va según lo que diga cada fila.
  const [elegidas, setElegidas] = useState<ReadonlyMap<number, boolean>>(() => new Map())
  const [resultado, setResultado] = useState<LoteEncolado | null>(null)
  const [rechazo, setRechazo] = useState<string[] | null>(null)
  const [falloEnvio, setFalloEnvio] = useState<string | null>(null)

  const comprobaciones = useComprobacionesTanda({
    step: paso === 'resumen' ? 2 : 1, batchQueue: cola, batchPhase: fase, proveedorElegido: SIN_ELECCION, minimo: 1,
  })
  const analisis = useAnalisisLote({ activo: paso === 'resumen' && fase === 'idle', elementos: enCola })
  const paralelo = useSubidasEnParalelo()

  // Otra selección en el paso 1: lo comprobado y lo elegido para la anterior ya no vale.
  const alternar = (id: number) => {
    setMarcadasAMano(prev => {
      const sig = new Set(prev ?? expansion.iniciales)
      if (sig.has(id)) sig.delete(id); else sig.add(id)
      return sig
    })
    comprobaciones.olvidar()
    analisis.olvidar()
    setElegidas(new Map())
  }

  // El nombre del torrent: el de una película sale de su nomenclatura; el de un pack, de sus comprobaciones.
  // undefined mientras no ha llegado.
  const nombreDe = (item: LibraryItemResponse): string | null | undefined => {
    if (item.item_type !== 'season') return analisis.analisis.get(item.id)?.nombre
    const contenido = comprobaciones.batchContentChecks.get(item.id)
    return contenido ? contenido.nombre ?? null : undefined
  }
  // Solo chocan las que se podrían subir: una que ya se salta por otro motivo no puede bloquear a la otra.
  const candidatas = enCola.filter(item =>
    comprobaciones.batchContentChecks.get(item.id)?.ready !== false && !analisis.analisis.get(item.id)?.bloqueo)
  const repetidos = nombresRepetidos(candidatas.map(item => ({ id: item.id, nombre: nombreDe(item) })))
  const filas: FilaResumenLote[] = enCola.map(item => {
    const id = item.id
    const contenido = comprobaciones.batchContentChecks.get(id)
    const a = analisis.analisis.get(id)
    const fallo = contenido?.ready === false ? primerFallo(contenido) : null
    const salto = fallo
      ? (item.item_type === 'season' && CONFLICTO_PROVEEDOR.test(fallo) ? `${fallo} Súbela suelta para elegirlo.` : fallo)
      : a?.bloqueo ?? (repetidos.has(id) ? 'Otro elemento del lote saldría con el mismo nombre.' : null)
    const pendiente = !contenido || !a
    const porDefecto = !!a && !a.sinIdioma && marcadaPorDefecto(a.nivel)
    return {
      item, contenido, analisis: a, nombre: nombreDe(item), salto, pendiente,
      incluida: !pendiente && !salto && (elegidas.get(id) ?? porDefecto),
    }
  })

  const subir = async () => {
    if (fase !== 'idle') return
    const incluidas = filas.filter(f => f.incluida)
    const elementosLote = incluidas.map(f => {
      const peticion = peticionDe(f.item.id)
      return {
        item_id: f.item.id,
        ...(peticion != null ? { request_item_id: peticion } : {}),
        checks: comprobaciones.mergedChecksFor(f.item.id)!,
        ...(f.analisis?.campos ? { campos: f.analisis.campos } : {}),
      }
    })
    if (elementosLote.length === 0 || elementosLote.some(e => !e.checks)) return
    setFase('processing'); setRechazo(null); setFalloEnvio(null)
    try {
      const r = await queueLote(elementosLote)
      setResultado(r)
      setFase('done')
      if (r.encolados > 0) onDone?.()
    } catch (e: unknown) {
      if (e instanceof ApiClientError && e.status === 409) setRechazo(motivosDelRechazo(e))
      else setFalloEnvio(e instanceof Error ? e.message : 'Error desconocido')
      setFase('idle')
    }
  }

  // Mientras se encola no se cierra: no se vería qué entró y qué no.
  const cerrar = () => { if (fase !== 'processing') onClose() }

  const verLote = () => {
    if (!resultado?.lote_id) return
    try { sessionStorage.setItem(CLAVE_ABRIR_LOTE, resultado.lote_id) } catch { /* ignore */ }
    onNavigate?.('uploads')
    onClose()
  }

  // Al cambiar de paso el foco pasa al paso nuevo, para que el lector lo anuncie y Tab siga desde arriba.
  const pasoActual = useRef<HTMLLIElement>(null)
  const primerPintado = useRef(true)
  useEffect(() => {
    if (primerPintado.current) { primerPintado.current = false; return }
    pasoActual.current?.focus()
  }, [paso])

  const indiceActual = PASOS.findIndex(p => p.paso === paso)
  const titulo = (id: number) => elementos.find(e => e.id === id)?.title ?? `#${id}`
  return (
    <Modal titulo="Subir por lotes" onClose={cerrar} className="modal-wide asist-modal-ancho">
      <nav aria-label="Pasos de la subida por lotes" className="asist-pasos">
        <ol>
          {PASOS.map(({ paso: p, nombre }, i) => {
            const estado = i < indiceActual ? 'hecho' : i === indiceActual ? 'actual' : 'pendiente'
            return (
              <li
                key={p} className={`asist-paso asist-paso-${estado}`}
                aria-current={estado === 'actual' ? 'step' : undefined}
                ref={estado === 'actual' ? pasoActual : undefined} tabIndex={estado === 'actual' ? -1 : undefined}
              >
                {estado === 'hecho' && <span aria-hidden="true">✓ </span>}{i + 1} · {nombre}
                {estado === 'hecho' && <span className="solo-lector"> (hecho)</span>}
              </li>
            )
          })}
        </ol>
      </nav>

      {paso === 'contenido' && (
        <PasoContenidoLote
          elementos={elementos} marcadas={marcadas} onAlternar={alternar} onContinuar={() => setPaso('resumen')}
          expandiendo={expansion.elementos ? null : { hechas: expansion.hechas, series: expansion.series }}
          avisos={expansion.avisos}
          peticiones={expansion.peticiones} peticionDe={peticionDe}
          onElegirPeticion={(id, peticion) => setPeticionElegida(prev => new Map(prev).set(id, peticion))}
        />
      )}

      {paso === 'resumen' && fase !== 'done' && (
        <PasoResumenLote
          filas={filas}
          entorno={comprobaciones.batchEnvChecks}
          comprobando={comprobaciones.batchChecksLoading}
          comprobandoIndice={comprobaciones.batchChecksIndex}
          errorComprobando={comprobaciones.batchChecksError}
          analizando={analisis.analizando}
          paralelo={paralelo}
          enviando={fase === 'processing'}
          rechazo={rechazo}
          falloEnvio={falloEnvio}
          onIncluir={(id, incluir) => setElegidas(prev => new Map(prev).set(id, incluir))}
          onRepetir={() => { comprobaciones.repetir(); analisis.repetir(); setRechazo(null); setFalloEnvio(null) }}
          onVolver={() => { setPaso('contenido'); setRechazo(null); setFalloEnvio(null) }}
          onSubir={subir}
        />
      )}

      {fase === 'done' && resultado && (
        <div className="modal-body">
          <div className="asist-resultado-titulo" role="status">
            {resultado.encolados} de {resultado.resultados.length} {resultado.resultados.length === 1 ? 'encolada' : 'encoladas'}
          </div>
          {resultado.saltados > 0 && (
            <div className="detail-card asist-tarjeta asist-mb-14">
              {resultado.resultados.filter(r => r.status !== 'queued').map(r => (
                <p key={r.item_id} className="asist-bloqueo">
                  ✗ {titulo(r.item_id)}: {r.errors.join(' ') || 'No se pudo encolar.'}
                </p>
              ))}
              <p className="asist-nota-saltan">
                {resultado.encolados > 0 ? 'Se han saltado. El resto ya está en la cola.' : 'No se ha encolado ninguna.'}
              </p>
            </div>
          )}
          <div className="asist-fila-centro">
            {resultado.lote_id ? (
              <button className="btn btn-primary" type="button" onClick={verLote}>Ver el lote en Subidas</button>
            ) : (
              <button className="btn btn-secondary" type="button" onClick={onClose}>Cerrar</button>
            )}
          </div>
        </div>
      )}
    </Modal>
  )
}
