import { useRef, useState } from 'react'
import { login } from '../api/auth'
import { ApiClientError } from '../api/client'
import { ServiceIcon } from '../components/ServiceIcon'

interface LoginPageProps {
  onSuccess: () => void
}

export function LoginPage({ onSuccess }: LoginPageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Qué campo tiene la culpa del error: solo ese se marca como inválido. Un fallo de red no es culpa de ninguno.
  const [invalido, setInvalido] = useState<'usuario' | 'clave' | 'ambos' | null>(null)
  const [loading, setLoading] = useState(false)
  const usuarioRef = useRef<HTMLInputElement>(null)
  const claveRef = useRef<HTMLInputElement>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    // El botón no se apaga con los campos vacíos (parecería roto): se dice qué falta y el foco va al primero vacío.
    if (!username.trim() || !password) {
      const falta = !username.trim() ? usuarioRef : claveRef
      setError(!username.trim() ? 'Escribe tu usuario.' : 'Escribe tu contraseña.')
      setInvalido(!username.trim() ? 'usuario' : 'clave')
      falta.current?.focus()
      return
    }
    setError(null)
    setInvalido(null)
    setLoading(true)
    try {
      await login(username.trim(), password, remember)
      onSuccess()
    } catch (err) {
      // The screen only ever shows a summary, so make sure the real cause
      // reaches somewhere it can be read: behind a proxy, WHY the request
      // failed is the whole diagnosis.
      console.error('Fallo al iniciar sesión:', err)
      if (err instanceof ApiClientError) {
        if (err.status === 401) {
          setError('Credenciales incorrectas. Revisa usuario y contraseña.')
          setInvalido('ambos')
        } else if (err.status === 429) {
          setError(err.message)
        } else if (err.status === 0) {
          // status 0 = the request never reached the server (see client.ts).
          setError(
            'No se pudo conectar con el servidor. Comprueba que el backend está arrancado y, '
            + 'si la aplicación va detrás de un proxy o de Cloudflare, que /api no se esté '
            + 'redirigiendo a otro dominio. El motivo exacto está en la consola del navegador.',
          )
        } else {
          setError(`${err.message} (HTTP ${err.status})`)
        }
      } else {
        setError('Error inesperado. Inténtalo de nuevo. El detalle está en la consola del navegador.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-wrap hud-app">
      <div className="login-card">
        <div className="login-logo">
          <ServiceIcon type="emu" size={40} />
          <h1 className="login-title login-titulo-mt" translate="no">eMuwarez Uploadrr</h1>
          <div className="login-sub">Inicia sesión para continuar</div>
        </div>
        <form onSubmit={handleSubmit} className="login-fields" autoComplete="on" noValidate>
          <div className="form-group">
            <label className="form-label" htmlFor="username">Usuario</label>
            <input
              id="username"
              ref={usuarioRef}
              className="form-input"
              type="text"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-describedby={error ? 'login-error' : undefined}
              aria-invalid={invalido === 'usuario' || invalido === 'ambos' ? true : undefined}
              disabled={loading}
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="password">Contraseña</label>
            <input
              id="password"
              ref={claveRef}
              className="form-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby={error ? 'login-error' : undefined}
              aria-invalid={invalido === 'clave' || invalido === 'ambos' ? true : undefined}
              disabled={loading}
            />
          </div>
          <label className="checkbox-label">
            <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} disabled={loading} /> Recordarme
          </label>
          {error && <div className="alert alert-error" role="alert" id="login-error">{error}</div>}
          <button
            type="submit"
            className="btn btn-primary login-submit"
            disabled={loading}
            aria-busy={loading}
          >
            {loading ? <><span className="spinner login-spinner" /> Iniciando…</> : 'Iniciar sesión'}
          </button>
        </form>
      </div>
    </div>
  )
}
