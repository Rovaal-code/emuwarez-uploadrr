// Las comprobaciones previas del paso 2: las de un solo elemento, y las de una
// tanda (varias temporadas o capítulos).
import { useCallback, useEffect, useState } from 'react'
import {
  runUploadChecks, getUploadChecksProgress, type UploadChecksResult, type UploadCheck,
} from '../../api/uploads'
import { seguirProgreso } from '../../api/eventos'
import { proveedorParaServidor, type ProveedoresElegidos } from '../../utils/origenProveedor'
import { cacheCubre } from '../../utils/seleccionSubida'

export function useComprobaciones(targetId: number | null, proveedorElegido: ProveedoresElegidos) {
  const [checks, setChecks] = useState<UploadChecksResult | null>(null)
  const [checksLoading, setChecksLoading] = useState(false)
  // Checks landing one at a time while the run (POST, ~30s of real network
  // calls) is in flight — polled separately so the UI can reveal each one as
  // it actually completes instead of sitting on a static spinner.
  const [liveChecks, setLiveChecks] = useState<UploadCheck[]>([])

  const runChecks = useCallback(async () => {
    if (targetId == null) return
    setChecksLoading(true)
    setLiveChecks([])
    const pedir = async () => {
      try {
        const p = await getUploadChecksProgress(targetId)
        setLiveChecks(p.checks)
      } catch { /* fallo pasajero — el siguiente aviso o tic reintenta */ }
    }
    const dejarDeSeguir = seguirProgreso(
      'comprobaciones-progreso', a => a.item_id === targetId, pedir, 400)
    try { setChecks(await runUploadChecks(targetId, undefined, proveedorParaServidor(proveedorElegido, targetId))) }
    catch { setChecks(null) }
    finally {
      dejarDeSeguir()
      setChecksLoading(false)
      setLiveChecks([])
    }
  }, [targetId, proveedorElegido])

  return { checks, checksLoading, liveChecks, runChecks }
}

// Paso 2 con varios elementos elegidos. Las comprobaciones del ENTORNO
// (directorio de salida, qBittorrent, hosts de imágenes, eMuwarez) se piden
// UNA vez para toda la tanda: con 30 capítulos, preguntarle 30 veces a
// eMuwarez si está vivo no aporta nada y multiplica por 30 la espera. Las
// del CONTENIDO sí van una por elemento, porque dependen del fichero.
export function useComprobacionesTanda({ step, batchQueue, batchPhase, proveedorElegido }: {
  step: 0 | 1 | 2
  batchQueue: readonly number[]
  batchPhase: 'idle' | 'processing' | 'done'
  proveedorElegido: ProveedoresElegidos
}) {
  const [batchEnvChecks, setBatchEnvChecks] = useState<UploadChecksResult | null>(null)
  const [batchContentChecks, setBatchContentChecks] = useState<Map<number, UploadChecksResult>>(new Map())
  const [batchChecksLoading, setBatchChecksLoading] = useState(false)
  const [batchChecksIndex, setBatchChecksIndex] = useState(0)
  // Cuál se está mirando en el desplegable de arriba a la derecha.
  const [batchViewId, setBatchViewId] = useState<number | null>(null)

  // Contenido + entorno reconstruye exactamente la pasada completa de siempre
  // (fijado por tests/test_upload_checks.py), así que el snapshot que se
  // guarda con el job es el mismo que antes.
  const mergedChecksFor = (id: number): UploadChecksResult | null => {
    const content = batchContentChecks.get(id)
    if (!content || !batchEnvChecks) return null
    return {
      checks: [...content.checks, ...batchEnvChecks.checks],
      ready: content.ready && batchEnvChecks.ready,
    }
  }

  // Al entrar en el paso 2 con varios elegidos: el entorno una vez, el
  // contenido uno a uno. Se guardan para que "Subir todos" no las repita y
  // para que el desplegable pueda enseñar las de cualquiera sin volver a
  // pedirlas.
  useEffect(() => {
    if (step !== 2 || batchQueue.length <= 1 || batchPhase !== 'idle') return
    if (batchChecksLoading || (batchEnvChecks && cacheCubre(batchQueue, batchContentChecks))) return
    let alive = true
    const run = async () => {
      setBatchChecksLoading(true)
      setBatchChecksIndex(0)
      try {
        // El item_id da igual para las de entorno, pero el endpoint lo pide.
        const env = await runUploadChecks(batchQueue[0], 'environment')
        if (!alive) return
        setBatchEnvChecks(env)
        const acc = new Map<number, UploadChecksResult>()
        for (let i = 0; i < batchQueue.length; i++) {
          if (!alive) return
          setBatchChecksIndex(i)
          acc.set(batchQueue[i], await runUploadChecks(
            batchQueue[i], 'content', proveedorParaServidor(proveedorElegido, batchQueue[i])))
          setBatchContentChecks(new Map(acc))
        }
        if (alive) setBatchViewId(prev => prev ?? batchQueue[0])
      } finally {
        if (alive) setBatchChecksLoading(false)
      }
    }
    run()
    return () => { alive = false; setBatchChecksLoading(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- se relanza al cambiar la tanda o su fase, no con cada elección
  }, [step, batchQueue.length, batchPhase])

  // Otra selección: lo comprobado para la anterior ya no vale.
  const olvidar = () => { setBatchEnvChecks(null); setBatchContentChecks(new Map()); setBatchViewId(null) }

  return {
    batchEnvChecks, batchContentChecks, batchChecksLoading, batchChecksIndex, batchViewId, setBatchViewId,
    mergedChecksFor, olvidar,
  }
}
