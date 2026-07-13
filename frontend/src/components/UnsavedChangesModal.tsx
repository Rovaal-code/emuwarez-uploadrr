import { useState, useEffect } from 'react'
import { setLeavePrompt } from '../utils/unsavedGuard'

// Card-styled confirmation shown when the user tries to leave a form with
// unsaved changes. Rendered once (in AppShell); it registers itself as the
// guard's "leave prompt" opener.
export function UnsavedChangesModal() {
  const [pending, setPending] = useState<{ proceed: () => void } | null>(null)

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
          <button className="btn-icon" onClick={cancel} title="Cerrar">✕</button>
        </div>
        <div className="modal-body">
          <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 13.5, lineHeight: 1.5 }}>
            Tienes cambios sin guardar en Configuración. Si sales ahora se perderán.
          </p>
        </div>
        <div className="modal-actions" style={{ justifyContent: 'flex-end' }}>
          <button className="btn btn-secondary" onClick={cancel}>Seguir editando</button>
          <button className="btn btn-danger" onClick={confirm}>Salir sin guardar</button>
        </div>
      </div>
    </div>
  )
}
