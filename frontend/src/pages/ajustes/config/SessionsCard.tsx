import { useState, useCallback } from 'react'
import { getSessions, closeOtherSessions, type SesionAbierta } from '../../../api/auth'
import { timeAgo, formatDate } from '../../../utils/format'
import { descripcionDeSesion } from '../../../utils/sesiones'
import { useAlEntrar } from '../../../context/SeccionVisible'
import { useSettingsMessageAdapter } from '../mensajes'

// ---------- Sesiones abiertas ----------
// Caducan a los 30 días sin usarse. «Cerrar las demás» deja solo esta: sirve tras un
// dispositivo perdido o una contraseña que se ha visto de más.
export function SessionsCard() {
  const [datos, setDatos] = useState<{ sessions: SesionAbierta[]; inactive_days: number } | null>(null)
  const [cerrando, setCerrando] = useState(false)
  const setMsg = useSettingsMessageAdapter()

  const cargar = useCallback(async () => {
    try { setDatos(await getSessions()) } catch { /* sin lista: la tarjeta queda cargando */ }
  }, [])
  useAlEntrar(() => { void cargar() })

  async function handleCerrarLasDemas() {
    setCerrando(true)
    try {
      const { closed } = await closeOtherSessions()
      setMsg({ ok: true, text: closed === 1 ? '✓ Se ha cerrado 1 sesión.' : `✓ Se han cerrado ${closed} sesiones.` })
      await cargar()
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setCerrando(false)
    }
  }

  return (
    <div className="placeholder-card">
      <h3>Sesiones abiertas</h3>
      {datos === null ? (
        <p className="form-hint">Cargando…</p>
      ) : (
        <>
          <p className="form-hint sesiones-nota">
            Los navegadores donde has iniciado sesión. Una sesión se cierra sola a los {datos.inactive_days} días sin usarse.
          </p>
          <div className="sesiones-lista">
            {datos.sessions.map(s => (
              <div key={s.id}>
                <div className="sesiones-lista__nombre">
                  <span title={s.user_agent ?? undefined}>{descripcionDeSesion(s.user_agent)}</span>
                  {s.current && <span className="badge status-available">Esta sesión</span>}
                </div>
                <div className="form-hint">
                  {s.ip_address ?? 'IP desconocida'} · {s.current ? 'activa ahora' : `última actividad ${timeAgo(s.last_used_at)}`} · abierta el {formatDate(s.created_at)}
                </div>
              </div>
            ))}
          </div>
          <button className="btn btn-secondary btn-sm" type="button" onClick={handleCerrarLasDemas} disabled={cerrando || datos.sessions.length < 2}>
            {cerrando ? 'Cerrando…' : 'Cerrar las demás'}
          </button>
        </>
      )}
    </div>
  )
}
