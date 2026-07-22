import { useState, useEffect } from 'react'
import { setLeavePrompt } from '../utils/unsavedGuard'
import { useTooltip } from './Tooltip'

// Card-styled confirmation shown when the user tries to leave a form with
// unsaved changes. Rendered once (in AppShell); it registers itself as the
// guard's "leave prompt" opener.
export function UnsavedChangesModal() {
  const [pending, setPending] = useState<{ proceed: () => void } | null>(null)
  const closeTip = useTooltip('Cerrar')

  useEffect(() => {
    setLeavePrompt((proceed) => setPending({ proceed }))
    return () => setLeavePrompt(null)
  }, [])

  if (!pending) return null

  const cancel = () => setPending(null)
  const confirm = () => {
    const p = pending.proceed
    setPending(null)
    p()
  }

  return (
    <div className="modal-overlay" onClick={cancel}>
      <div className="modal" style={{ maxWidth: 420 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Cambios sin guardar</h2>
          <button className="btn-icon" onClick={cancel} {...closeTip.triggerProps}>✕{closeTip.tooltipNode}</button>
        </div>
        <div className="modal-body">
          <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 13.5, lineHeight: 1.5 }}>
            Tienes cambios sin guardar en Configuración. Si sales ahora se perderán.
          </p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
            <button className="btn btn-danger" onClick={confirm}>Salir sin guardar</button>
          </div>
        </div>
      </div>
    </div>
  )
}
