import { useState } from 'react'
import { login } from '../api/auth'
import { ApiClientError } from '../api/client'
import { ServiceIcon } from '../components/ServiceIcon'

interface LoginPageProps {
  onSuccess: () => void
}

export function LoginPage({ onSuccess }: LoginPageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!username.trim() || !password) return
    setError(null)
    setLoading(true)
    try {
      await login(username.trim(), password)
      onSuccess()
    } catch (err) {
      if (err instanceof ApiClientError) {
        if (err.status === 401) {
          setError('Credenciales incorrectas. Revisa usuario y contraseña.')
        } else if (err.status === 0 || err.message === 'Failed to fetch') {
          setError('No se pudo conectar con el servidor. Verifica que el backend está arrancado.')
        } else {
          setError(err.message)
        }
      } else {
        setError('Error inesperado. Inténtalo de nuevo.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-logo">
          <ServiceIcon type="emu" size={40} />
          <div className="login-title" style={{ marginTop: 10 }}>eMuwarez Uploadrr</div>
          <div className="login-sub">Inicia sesión para continuar</div>
        </div>
        <form onSubmit={handleSubmit} className="login-fields" autoComplete="on">
          <div className="form-group">
            <label className="form-label" htmlFor="username">Usuario</label>
            <input
              id="username"
              className="form-input"
              type="text"
              placeholder="admin"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              disabled={loading}
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="password">Contraseña</label>
            <input
              id="password"
              className="form-input"
              type="password"
              placeholder="••••••••••••"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={loading}
            />
          </div>
          {error && <div className="alert alert-error">{error}</div>}
          <button
            type="submit"
            className="btn btn-primary login-submit"
            disabled={loading || !username.trim() || !password}
          >
            {loading ? <><span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Iniciando…</> : 'Iniciar sesión'}
          </button>
        </form>
      </div>
    </div>
  )
}
