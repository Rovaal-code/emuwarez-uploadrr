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
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      <td style={{ padding: '6px 8px', color: 'var(--text-secondary)', width: 150 }}>{etiqueta}</td>
      <td style={{ padding: '6px 8px', wordBreak: 'break-all' }}>{valor}</td>
    </tr>
  )

  // El digest es largo y no aporta leído entero: se enseña recortado y entero
  // al pasar el ratón, como el resto de identificadores de la aplicación.
  const digest = (valor?: string | null) => {
    if (!valor) return <span style={{ color: 'var(--text-muted)' }}>—</span>
    const corto = valor.startsWith('sha256:') ? valor.slice(0, 19) + '…' : valor.slice(0, 12) + '…'
    return <HoverTitle tip={valor}><code style={{ fontSize: 12 }}>{corto}</code></HoverTitle>
  }

  return (
    <div className="placeholder-card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <h3 style={{ margin: 0 }}>Versión</h3>
        <button className="btn btn-secondary btn-sm" type="button"
                onClick={() => cargar(true)} disabled={comprobando}>
          {comprobando ? 'Comprobando…' : 'Comprobar ahora'}
        </button>
      </div>
      {!info && <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Cargando…</p>}
      {info && (
        <>
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <tbody>
              {fila('Versión', info.version)}
              {fila('Commit', info.commit_corto
                ? <HoverTitle tip={info.commit!}><code style={{ fontSize: 12 }}>{info.commit_corto}</code></HoverTitle>
                : <span style={{ color: 'var(--text-muted)' }}>sin sellar</span>)}
              {fila('Construida', info.construida || <span style={{ color: 'var(--text-muted)' }}>—</span>)}
              {fila('Digest', digest(info.digest))}
              {info.estado === 'hay_novedad' && fila('Última publicada',
                <>
                  {info.ultima.commit_corto
                    ? <HoverTitle tip={info.ultima.commit!}><code style={{ fontSize: 12 }}>{info.ultima.commit_corto}</code></HoverTitle>
                    : '—'}
                  {info.ultima.publicada ? <span style={{ color: 'var(--text-muted)' }}> · {info.ultima.publicada}</span> : null}
                </>)}
              {info.estado === 'hay_novedad' && fila('Digest publicado', digest(info.ultima.digest))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}
