import { useState, useEffect } from 'react'
import { setLeavePrompt } from '../utils/unsavedGuard'
import { Modal } from './Modal'

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
    <Modal titulo="Cambios sin guardar" onClose={cancel} style={{ maxWidth: 420 }}>
      <div className="modal-body">
        <p className="menores-sin-guardar-texto">
          Tienes cambios sin guardar en Configuración. Si sales ahora se perderán.
        </p>
        <div className="menores-sin-guardar-acciones">
          <button className="btn btn-danger" onClick={confirm}>Salir sin guardar</button>
        </div>
      </div>
    </Modal>
  )
}
