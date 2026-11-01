import { useState } from 'react'
import { runIntegrityCheck, runVacuum } from '../../../api/maintenance'
import { useSettingsMessage } from '../mensajes'

// Integridad y VACUUM, dentro de la tarjeta "Base de datos" de Diagnóstico.
export function DatabaseActions({ onRefresh }: { onRefresh: () => void }) {
  const [busy, setBusy] = useState(false)
  const [vacuumConfirm, setVacuumConfirm] = useState('')
  const showMessage = useSettingsMessage()

  async function handleIntegrity() {
    setBusy(true)
    try {
      const r = await runIntegrityCheck()
      showMessage(r.ok, r.ok ? `✓ ${r.message}` : `✗ ${r.message || r.error}`)
    } catch (e: unknown) {
      showMessage(false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally { setBusy(false) }
  }

  async function handleVacuum(dry: boolean) {
    if (!dry && vacuumConfirm !== 'MANTENIMIENTO_DB') {
      showMessage(false, 'Escribe MANTENIMIENTO_DB para confirmar'); return
    }
    setBusy(true)
    try {
      const r = await runVacuum({ dry_run: dry, apply: !dry, confirmation: dry ? undefined : vacuumConfirm })
      showMessage(r.ok ?? false, r.ok ? `✓ ${r.message}` : `✗ ${r.error}`)
      if (r.ok && !dry) onRefresh()
    } catch (e: unknown) {
      showMessage(false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally { setBusy(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 14 }}>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: 0 }}>
        <strong>Verificar integridad</strong> ejecuta <code>PRAGMA integrity_check</code> (solo lectura).{' '}
        <strong>VACUUM</strong> compacta la BD y libera las páginas libres; escribe <code>MANTENIMIENTO_DB</code> para ejecutarlo.
      </p>
      <input
        type="text"
        placeholder="Confirmación: MANTENIMIENTO_DB"
        aria-label="Confirmación de VACUUM"
        value={vacuumConfirm}
        onChange={e => setVacuumConfirm(e.target.value)}
        style={{ width: '100%', padding: '6px 10px', fontSize: 13, boxSizing: 'border-box' }}
      />
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button className="btn btn-secondary" onClick={handleIntegrity} disabled={busy}>Verificar integridad</button>
        <button className="btn btn-secondary" onClick={() => handleVacuum(true)} disabled={busy}>Previsualizar VACUUM</button>
        <button className="btn btn-danger" onClick={() => handleVacuum(false)} disabled={busy}>Ejecutar VACUUM</button>
      </div>
    </div>
  )
}
