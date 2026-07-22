import { useState, useEffect } from 'react'
import { getSetupStatus } from './api/setup'
import { getMe } from './api/auth'
import { getToken, clearToken } from './api/client'
import type { SetupStatusResponse, CurrentUserResponse } from './types/api'
import { LoginPage } from './pages/LoginPage'
import { SetupWizard } from './pages/SetupWizard'
import { AppShell } from './components/AppShell'
import { LoadingState } from './components/LoadingState'
import { SyncProvider } from './context/SyncContext'

type AppState = 'loading' | 'setup' | 'login' | 'app'

// The backend's SPA fallback serves index.html for any non-/api path, so
// visiting an arbitrary URL (or a normal deep link like /library) while the
// app isn't set up yet used to show the wizard with whatever path the user
// typed left in the address bar untouched. Normalizing it to a dedicated
// path makes it clear the wizard IS the page you're on, not an override
// glued on top of wherever you happened to land.
function normalizePath(path: string) {
  if (window.location.pathname !== path) {
    window.history.replaceState(null, '', path)
  }
}

// Same idea as /setup, but the login screen also needs to remember what you
// were actually trying to reach (e.g. a bookmark to /library while logged
// out) so a successful login can still take you there instead of always
// landing on the dashboard.
function normalizeToLogin() {
  if (window.location.pathname === '/login') return
  const current = window.location.pathname + window.location.search
  const next = current === '/' ? '' : `?next=${encodeURIComponent(current)}`
  window.history.replaceState(null, '', `/login${next}`)
}

function restoreFromLogin() {
  if (window.location.pathname !== '/login') return
  const next = new URLSearchParams(window.location.search).get('next')
  window.history.replaceState(null, '', next || '/')
}

export function App() {
  const [state, setState] = useState<AppState>('loading')
  const [setupStatus, setSetupStatus] = useState<SetupStatusResponse | null>(null)
  const [user, setUser] = useState<CurrentUserResponse | null>(null)

  async function bootstrap() {
    setState('loading')
    try {
      const status = await getSetupStatus()
      setSetupStatus(status)

      // No admin yet → setup wizard (admin step)
      if (!status.admin_configured) {
        normalizePath('/setup')
        setState('setup')
        return
      }

      // Try to use existing token
      const token = getToken()
      if (token) {
        try {
          const me = await getMe()
          setUser(me)
          if (!status.initialized) {
            normalizePath('/setup')
            setState('setup')
          } else {
            // Leftover from a previous incomplete setup — once we're fully
            // in the app, /setup isn't a real tab, so send it back to the
            // dashboard instead of leaving a dead URL in the address bar.
            if (window.location.pathname === '/setup') {
              normalizePath('/')
            } else {
              restoreFromLogin()
            }
            setState('app')
          }
          return
        } catch {
          clearToken()
        }
      }

      // No valid token
      normalizeToLogin()
      setState('login')
    } catch {
      // Backend not available — show login and let it fail with an error
      normalizeToLogin()
      setState('login')
    }
  }

  useEffect(() => { bootstrap() }, [])

  function handleLoginSuccess() {
    bootstrap()
  }

  function handleSetupComplete() {
    bootstrap()
  }

  function handleLogout() {
    setUser(null)
    normalizeToLogin()
    setState('login')
  }

  if (state === 'loading') {
    return <LoadingState label="Conectando con el servidor…" />
  }

  if (state === 'setup' && setupStatus) {
    return <SetupWizard setupStatus={setupStatus} onComplete={handleSetupComplete} />
  }

  if (state === 'login') {
    return <LoginPage onSuccess={handleLoginSuccess} />
  }

  return (
    <SyncProvider>
      <AppShell user={user} onLogout={handleLogout} />
    </SyncProvider>
  )
}
