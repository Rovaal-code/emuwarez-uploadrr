import { useState, useEffect } from 'react'
import { useUnsavedGuard } from '../../../utils/unsavedGuard'
import { getMe, changeCredentials } from '../../../api/auth'
import { IconoUsuario } from '../../../components/Iconos'
import { useSettingsMessageAdapter } from '../mensajes'

// Self-contained: its own "Guardar" instead of joining ConfigTab's shared
// save button — changing credentials always needs the current password
// re-entered, so it can't silently ride along with the rest of the form.
export function AccountCard() {
  const [username, setUsername] = useState('')
  const [newUsername, setNewUsername] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const setMsg = useSettingsMessageAdapter()

  useEffect(() => { getMe().then(u => setUsername(u.username)).catch(() => {}) }, [])

  const dirty = newUsername.trim() !== '' || newPassword !== ''
  useUnsavedGuard('cuenta', dirty)

  async function handleSave() {
    setMsg(null)
    if (!currentPassword) { setMsg({ ok: false, text: 'Introduce tu contraseña actual para confirmar el cambio.' }); return }
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
      <h3 className="aj-card-titulo aj-mb-6">
        <IconoUsuario size={18} style={{ color: 'var(--text-accent)' }} /> Cuenta
      </h3>
      <p className="form-hint aj-mt-0 aj-mb-14">
        Cambia el usuario y/o la contraseña con la que inicias sesión en esta aplicación.
      </p>
      <div className="form-group aj-mb-12">
        <label className="form-label">Usuario actual</label>
        <input className="form-input" value={username || '…'} disabled />
      </div>
      <div className="form-group aj-mb-12">
        <label className="form-label">Nuevo usuario <span className="form-hint">(dejar vacío para no cambiarlo)</span></label>
        <input className="form-input" value={newUsername} onChange={e => setNewUsername(e.target.value)} placeholder={username} autoComplete="off" />
      </div>
      <div className="form-group aj-mb-12">
        <label className="form-label">Nueva contraseña <span className="form-hint">(dejar vacío para no cambiarla)</span></label>
        <input type="password" className="form-input" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Nueva contraseña" autoComplete="new-password" />
      </div>
      <div className="form-group aj-mb-14">
        <label className="form-label">Contraseña actual <span className="form-hint">(obligatoria para confirmar)</span></label>
        <input type="password" className="form-input" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} placeholder="Tu contraseña actual" autoComplete="current-password" />
      </div>
      <div className="aj-flex-c-12">
        <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving || !dirty}>
          {saving ? 'Guardando…' : 'Guardar cambios'}
        </button>
      </div>
    </div>
  )
}
