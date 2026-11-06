import { useState, useCallback } from 'react'
import { getWidgetKeyStatus, generateWidgetKey, removeWidgetKey } from '../../../api/widget'
import { useAlEntrar } from '../../../context/SeccionVisible'
import { Modal } from '../../../components/Modal'
import { CabeceraTarjeta } from '../CabeceraTarjeta'

// Lo que se confirma antes de tocar una clave que ya está puesta.
type Confirmacion = 'regenerar' | 'quitar'

const TEXTO_CONFIRMACION: Record<Confirmacion, { titulo: string; texto: string; boton: string }> = {
  regenerar: {
    titulo: 'Regenerar la clave del widget',
    texto: 'Homepage dejará de ver el widget hasta que pongas la clave nueva en su services.yaml.',
    boton: 'Regenerar clave',
  },
  quitar: {
    titulo: 'Quitar la clave del widget',
    texto: 'El widget dejará de responder hasta que generes otra clave.',
    boton: 'Quitar clave',
  },
}

// ---------- Widget para Homepage ----------
// La clave solo abre GET /api/widget (contadores de solo lectura). Se ve entera al generarla;
// después la base solo guarda su hash.
export function WidgetCard() {
  const [configurada, setConfigurada] = useState<boolean | null>(null)
  const [errorCarga, setErrorCarga] = useState(false)
  const [nueva, setNueva] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)
  const [confirmando, setConfirmando] = useState<Confirmacion | null>(null)
  // El aviso de lo que acaba de pasar sale bajo los botones de la tarjeta, no en la fila de pestañas: la tarjeta
  // está al fondo de la página y un aviso arriba no se veía.
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const cargar = useCallback(async () => {
    setErrorCarga(false)
    try { setConfigurada((await getWidgetKeyStatus()).configurada) } catch { setErrorCarga(true) }
  }, [])
  useAlEntrar(() => { void cargar() })

  async function ejecutar(accion: () => Promise<void>) {
    setOcupado(true)
    setMsg(null)
    try {
      await accion()
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setOcupado(false)
    }
  }

  const generar = () => ejecutar(async () => {
    setNueva((await generateWidgetKey()).clave)
    setConfigurada(true)
  })

  const quitar = () => ejecutar(async () => {
    await removeWidgetKey()
    setNueva(null)
    setConfigurada(false)
  })

  function confirmar() {
    const accion = confirmando
    setConfirmando(null)
    if (accion === 'regenerar') void generar()
    else if (accion === 'quitar') void quitar()
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
      <CabeceraTarjeta
        icono={(
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
            <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" />
            <rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" />
          </svg>
        )}
        titulo="Widget para Homepage"
        descripcion={<>
          Una clave de solo lectura para el widget «customapi» de Homepage: solo abre <code>/api/widget</code> y
          enseña unos contadores. La configuración de Homepage está en la guía de despliegue.
        </>}
        lateral={configurada === null ? undefined : (
          <span className={`aj-estado aj-estado--${configurada ? 'ok' : 'falta'}`}>
            <span className="aj-estado__punto" aria-hidden />
            {configurada ? 'Clave puesta' : 'Sin clave'}
          </span>
        )}
      />
      {configurada === null ? (
        errorCarga ? (
          <p className="form-hint">
            No se pudo cargar el estado de la clave.{' '}
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => { void cargar() }}>Reintentar</button>
          </p>
        ) : (
          <p className="form-hint">Cargando…</p>
        )
      ) : (
        <>
          {nueva && (
            <div className="widget-clave">
              <input className="form-input widget-clave__valor" readOnly value={nueva} aria-label="Clave del widget"
                onFocus={e => e.currentTarget.select()} />
              <button className="btn btn-secondary btn-sm" type="button" onClick={copiar}>Copiar</button>
              <p className="form-hint">Guárdala ahora: no se vuelve a mostrar.</p>
            </div>
          )}
          <div className="widget-botones">
            <button className="btn btn-secondary btn-sm" type="button" disabled={ocupado}
              onClick={() => { if (configurada) setConfirmando('regenerar'); else void generar() }}>
              {configurada ? 'Regenerar clave' : 'Generar clave'}
            </button>
            {configurada && (
              <button className="btn btn-secondary btn-sm" type="button" onClick={() => setConfirmando('quitar')} disabled={ocupado}>Quitar clave</button>
            )}
          </div>
          {msg && (
            <p role={msg.ok ? 'status' : 'alert'} className={`aj-resultado aj-resultado--${msg.ok ? 'ok' : 'error'} widget-aviso`}>{msg.text}</p>
          )}
        </>
      )}
      {confirmando && (
        <Modal titulo={TEXTO_CONFIRMACION[confirmando].titulo} onClose={() => setConfirmando(null)} className="modal-estrecho">
          <div className="modal-body">
            <p className="menores-sin-guardar-texto">{TEXTO_CONFIRMACION[confirmando].texto}</p>
            <div className="menores-sin-guardar-acciones">
              {/* La acción segura lleva el foco: Intro sin mirar no deja a Homepage sin widget. */}
              <button type="button" className="btn btn-secondary" onClick={() => setConfirmando(null)} autoFocus>Cancelar</button>
              <button type="button" className="btn btn-danger" onClick={confirmar}>{TEXTO_CONFIRMACION[confirmando].boton}</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
