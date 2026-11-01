import { useState, useEffect, useCallback } from 'react'
import { getVersionInfo, type VersionInfo } from '../../../api/maintenance'
import { HoverTitle } from '../../../components/Tooltip'
import { useSettingsMessage } from '../mensajes'

export function VersionCard() {
  const [info, setInfo] = useState<VersionInfo | null>(null)
  const [comprobando, setComprobando] = useState(false)
  const mensaje = useSettingsMessage()

  const cargar = useCallback(async (refrescar = false) => {
    setComprobando(refrescar)
    try {
      const datos = await getVersionInfo(refrescar)
      setInfo(datos)
      // Al hueco de la fila de pestañas, como el resto de mensajes.
      //
      // Permanente solo cuando queda algo por hacer: hay versión nueva, o no
      // se ha podido comprobar. "Estás al día" es una confirmación de que la
      // comprobación se hizo, así que se comporta como los demás y desaparece
      // a los cinco segundos; dejarlo fijo era ruido en todas las pestañas.
      if (datos.estado === 'hay_novedad') {
        mensaje(false, `Hay una versión más nueva${datos.ultima.version ? `: v${datos.ultima.version}` : ''}`,
                { tono: 'aviso', permanente: true })
      } else if (datos.estado === 'al_dia') {
        mensaje(true, 'Estás en la última versión publicada', { borrarPermanente: true })
      } else {
        mensaje(false, datos.motivo || 'No se ha podido comprobar si hay una versión más nueva',
                { tono: 'aviso', permanente: true })
      }
    } catch (e: unknown) {
      mensaje(false, e instanceof Error ? e.message : String(e), { permanente: true })
    } finally {
      setComprobando(false)
    }
  }, [mensaje])

  useEffect(() => { cargar() }, [cargar])

  const fila = (etiqueta: string, valor: React.ReactNode) => (
    <tr className="aj-fila-borde">
      <td className="aj-td-etq-150">{etiqueta}</td>
      <td className="aj-td-6 aj-corta">{valor}</td>
    </tr>
  )

  // El digest es largo y no aporta leído entero: se enseña recortado y entero
  // al pasar el ratón, como el resto de identificadores de la aplicación.
  const digest = (valor?: string | null) => {
    if (!valor) return <span className="aj-muted">—</span>
    const corto = valor.startsWith('sha256:') ? valor.slice(0, 19) + '…' : valor.slice(0, 12) + '…'
    return <HoverTitle tip={valor}><code className="aj-fs-12">{corto}</code></HoverTitle>
  }

  return (
    <div className="placeholder-card">
      <div className="aj-entre-12">
        <h3 className="aj-m-0">Versión</h3>
        <button className="btn btn-secondary btn-sm" type="button"
                onClick={() => cargar(true)} disabled={comprobando}>
          {comprobando ? 'Comprobando…' : 'Comprobar ahora'}
        </button>
      </div>
      {!info && <p className="aj-sec-13">Cargando…</p>}
      {info && (
        <>
          <table className="aj-tabla aj-fs-13">
            <tbody>
              {fila('Versión', info.version)}
              {fila('Commit', info.commit_corto
                ? <HoverTitle tip={info.commit!}><code className="aj-fs-12">{info.commit_corto}</code></HoverTitle>
                : <span className="aj-muted">sin sellar</span>)}
              {fila('Construida', info.construida || <span className="aj-muted">—</span>)}
              {fila('Digest', digest(info.digest))}
              {info.estado === 'hay_novedad' && fila('Última publicada',
                <>
                  {info.ultima.commit_corto
                    ? <HoverTitle tip={info.ultima.commit!}><code className="aj-fs-12">{info.ultima.commit_corto}</code></HoverTitle>
                    : '—'}
                  {info.ultima.publicada ? <span className="aj-muted"> · {info.ultima.publicada}</span> : null}
                </>)}
              {info.estado === 'hay_novedad' && fila('Digest publicado', digest(info.ultima.digest))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}
