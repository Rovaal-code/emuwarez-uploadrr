import { useState, useEffect, useCallback } from 'react'
import { useUnsavedGuard } from '../../../utils/unsavedGuard'
import { getMe, changeCredentials } from '../../../api/auth'
import { IconoUsuario } from '../../../components/Iconos'
import { useSettingsMessageAdapter } from '../mensajes'
import { Campo } from '../Campo'
import { CabeceraTarjeta } from '../CabeceraTarjeta'

// Self-contained: its own "Guardar" instead of joining ConfigTab's shared
// save button — changing credentials always needs the current password
// re-entered, so it can't silently ride along with the rest of the form.
export function AccountCard() {
  const [username, setUsername] = useState('')
  const [newUsername, setNewUsername] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [errorClave, setErrorClave] = useState<string | null>(null)
  const setMsg = useSettingsMessageAdapter()

  // Sin esto, un fallo dejaba «…» en el usuario actual para siempre, como si siguiera cargando.
  const [errorUsuario, setErrorUsuario] = useState(false)
  const cargarUsuario = useCallback(() => {
    setErrorUsuario(false)
    getMe().then(u => setUsername(u.username)).catch(() => setErrorUsuario(true))
  }, [])
  useEffect(() => { cargarUsuario() }, [cargarUsuario])

  const dirty = newUsername.trim() !== '' || newPassword !== ''
  useUnsavedGuard('cuenta', dirty)

  async function handleSave() {
    setMsg(null)
    setErrorClave(null)
    if (!currentPassword) { setErrorClave('Introduce tu contraseña actual para confirmar el cambio.'); return }
    if (!dirty) { setMsg({ ok: false, text: 'No hay ningún cambio que guardar.' }); return }
    setSaving(true)
    try {
      const resp = await changeCredentials({
        current_password: currentPassword,
        new_username: newUsername.trim() || undefined,
        new_password: newPassword || undefined,
      })
      setUsername(resp.username)
      setNewUsername('')
      setNewPassword('')
      setCurrentPassword('')
      setMsg({ ok: true, text: '✓ Credenciales actualizadas correctamente.' })
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="placeholder-card">
      <CabeceraTarjeta
        icono={<IconoUsuario size={18} />}
        titulo="Cuenta"
        descripcion="Cambia el usuario y/o la contraseña con la que inicias sesión en esta aplicación."
      />
      <Campo
        etiqueta="Usuario actual"
        ayuda={errorUsuario ? (
          <>
            No se pudo leer el usuario actual.{' '}
            <button type="button" className="btn btn-secondary btn-sm" onClick={cargarUsuario}>Reintentar</button>
          </>
        ) : undefined}
      >
        {c => <input {...c} className="form-input" value={username || (errorUsuario ? '' : '…')} disabled />}
      </Campo>
      <Campo etiqueta="Nuevo usuario" nota="dejar vacío para no cambiarlo">
        {c => <input {...c} className="form-input" value={newUsername} onChange={e => setNewUsername(e.target.value)} autoComplete="off" />}
      </Campo>
      <Campo etiqueta="Nueva contraseña" nota="dejar vacío para no cambiarla">
        {c => <input {...c} type="password" className="form-input" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Nueva contraseña" autoComplete="new-password" />}
      </Campo>
      <Campo etiqueta="Contraseña actual" nota="obligatoria para confirmar" error={errorClave}>
        {c => <input {...c} type="password" className="form-input" value={currentPassword} onChange={e => { setCurrentPassword(e.target.value); setErrorClave(null) }} placeholder="Tu contraseña actual" autoComplete="current-password" />}
      </Campo>
      <div className="aj-acciones">
        <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving || !dirty}>
          {saving ? 'Guardando…' : 'Guardar cambios'}
        </button>
      </div>
    </div>
  )
}
