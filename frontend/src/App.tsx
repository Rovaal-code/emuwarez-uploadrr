import { useState, useEffect, useRef } from 'react'
import { getSetupStatus } from './api/setup'
import { getMe } from './api/auth'
import { getToken, clearToken, esSesionCaducada, setUnauthorizedHandler } from './api/client'
import { esperaDelIntento } from './api/eventos'
import type { SetupStatusResponse, CurrentUserResponse } from './types/api'
import { LoginPage } from './pages/LoginPage'
import { SetupWizard } from './pages/SetupWizard'
import { AppShell } from './components/AppShell'
import { LoadingState } from './components/LoadingState'
import { SyncProvider } from './context/SyncContext'
import { PerfilEmuProvider } from './context/PerfilEmuContext'
import { TourProvider } from './context/TourContext'

type AppState = 'loading' | 'reconectando' | 'setup' | 'login' | 'app'

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
  window.history.replaceState(null, '', next || '/dashboard')
}

export function App() {
  const [state, setState] = useState<AppState>('loading')
  const [setupStatus, setSetupStatus] = useState<SetupStatusResponse | null>(null)
  const [user, setUser] = useState<CurrentUserResponse | null>(null)

  // Los intentos seguidos que han fallado: la espera crece igual que la del canal de avisos.
  const intentos = useRef(0)
  const reintento = useRef<ReturnType<typeof setTimeout> | null>(null)

  // El servidor no contesta bien (red, 502, base ocupada): ni login ni asistente, que
  // serían mentira. Se muestra «reconectando» y se vuelve a probar sin tirar el token.
  function reconectar() {
    setState('reconectando')
    reintento.current = setTimeout(() => bootstrap(true), esperaDelIntento(intentos.current++))
  }

  async function bootstrap(reintentando = false) {
    if (!reintentando) {
      intentos.current = 0
      setState('loading')
    }
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
            // Leftover from a previous incomplete setup, or a bare "/" — once
            // we're fully in the app, /setup isn't a real tab and "/" has no
            // dedicated address of its own the way every other tab does, so
            // both send it to /dashboard instead of leaving an inconsistent
            // URL in the address bar.
            if (window.location.pathname === '/setup' || window.location.pathname === '/') {
              normalizePath('/dashboard')
            } else {
              restoreFromLogin()
            }
            setState('app')
          }
          return
        } catch (err) {
          // Solo un 401 es un token que ya no vale; cualquier otro fallo no dice nada de él.
          if (!esSesionCaducada(err)) { reconectar(); return }
          clearToken()
        }
      }

      // No valid token
      normalizeToLogin()
      setState('login')
    } catch {
      reconectar()
    }
  }

  useEffect(() => {
    bootstrap()
    return () => { if (reintento.current) clearTimeout(reintento.current) }
  }, [])

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

  // A 401 while state === 'app' means a session that WAS working just died
  // server-side — bounce to login immediately instead of leaving the page
  // looking half-logged-in with a local error until a manual refresh. Gated
  // on 'app': the setup wizard's early (pre-admin) steps make their own
  // best-effort authenticated prefetches expecting a 401 there and already
  // handle it locally (e.g. its provider-order prefetch) — those must not
  // also bounce the whole app to /login.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (state === 'app') handleLogout()
    })
    return () => setUnauthorizedHandler(null)
  }, [state])

  if (state === 'loading') {
    return <LoadingState label="Conectando con el servidor…" />
  }

  if (state === 'reconectando') {
    return <LoadingState label="No se puede conectar con el servidor. Reintentando…" />
  }

  if (state === 'setup' && setupStatus) {
    return <SetupWizard setupStatus={setupStatus} onComplete={handleSetupComplete} />
  }

  if (state === 'login') {
    return <LoginPage onSuccess={handleLoginSuccess} />
  }

  return (
    <SyncProvider>
      <PerfilEmuProvider>
        <TourProvider>
          <AppShell user={user} onLogout={handleLogout} />
        </TourProvider>
      </PerfilEmuProvider>
    </SyncProvider>
  )
}
