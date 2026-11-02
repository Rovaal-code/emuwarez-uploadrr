import { useState, useCallback } from 'react'
import { getWidgetKeyStatus, generateWidgetKey, removeWidgetKey } from '../../../api/widget'
import { useAlEntrar } from '../../../context/SeccionVisible'
import { useSettingsMessageAdapter } from '../mensajes'

// ---------- Widget para Homepage ----------
// La clave solo abre GET /api/widget (contadores de solo lectura). Se ve entera al generarla;
// después la base solo guarda su hash.
export function WidgetCard() {
  const [configurada, setConfigurada] = useState<boolean | null>(null)
  const [nueva, setNueva] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const setMsg = useSettingsMessageAdapter()

  const cargar = useCallback(async () => {
    try { setConfigurada((await getWidgetKeyStatus()).configurada) } catch { /* sin estado: la tarjeta queda cargando */ }
  }, [])
  useAlEntrar(() => { void cargar() })

  async function ejecutar(accion: () => Promise<void>) {
    setOcupado(true)
    try {
      await accion()
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setOcupado(false)
    }
  }

  const generar = () => {
    if (configurada && !window.confirm('Homepage dejará de ver el widget hasta que pongas la clave nueva en su services.yaml. ¿Regenerar la clave?')) return
    return ejecutar(async () => {
      setNueva((await generateWidgetKey()).clave)
      setConfigurada(true)
    })
  }

  const quitar = () => {
    if (!window.confirm('El widget dejará de responder. ¿Quitar la clave?')) return
    return ejecutar(async () => {
      await removeWidgetKey()
      setNueva(null)
      setConfigurada(false)
    })
  }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(nueva ?? '')
      setMsg({ ok: true, text: '✓ Clave copiada.' })
    } catch {
      // El portapapeles solo existe en https o en localhost.
      setMsg({ ok: false, text: 'No se pudo copiar: selecciónala y cópiala a mano.' })
    }
  }

  return (
    <div className="placeholder-card">
      <h3>Widget para Homepage</h3>
      {configurada === null ? (
        <p className="form-hint">Cargando…</p>
      ) : (
        <>
          <p className="form-hint widget-nota">
            Una clave de solo lectura para el widget «customapi» de Homepage: solo abre <code>/api/widget</code> y
            enseña unos contadores. La configuración de Homepage está en la guía de despliegue.
          </p>
          {nueva && (
            <div className="widget-clave">
              <input className="form-input widget-clave__valor" readOnly value={nueva} aria-label="Clave del widget"
                onFocus={e => e.currentTarget.select()} />
              <button className="btn btn-secondary btn-sm" type="button" onClick={copiar}>Copiar</button>
              <p className="form-hint">Guárdala ahora: no se vuelve a mostrar.</p>
            </div>
          )}
          {!nueva && <p className="form-hint">{configurada ? 'Clave puesta.' : 'Sin clave: el widget está desactivado.'}</p>}
          <div className="widget-botones">
            <button className="btn btn-secondary btn-sm" type="button" onClick={generar} disabled={ocupado}>
              {configurada ? 'Regenerar clave' : 'Generar clave'}
            </button>
            {configurada && (
              <button className="btn btn-secondary btn-sm" type="button" onClick={quitar} disabled={ocupado}>Quitar clave</button>
            )}
          </div>
        </>
      )}
    </div>
  )
}
