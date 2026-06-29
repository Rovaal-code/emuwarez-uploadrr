import { useState, useEffect } from 'react'
import { getSetupStatus } from './api/setup'
import { getMe } from './api/auth'
import { getToken, clearToken } from './api/client'
import type { SetupStatusResponse, CurrentUserResponse } from './types/api'
import { LoginPage } from './pages/LoginPage'
import { SetupWizard } from './pages/SetupWizard'
import { AppShell } from './components/AppShell'
import { LoadingState } from './components/LoadingState'

type AppState = 'loading' | 'setup' | 'login' | 'app'

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
            setState('setup')
          } else {
            setState('app')
          }
          return
        } catch {
          clearToken()
        }
      }

      // No valid token
      setState('login')
    } catch {
      // Backend not available — show login and let it fail with an error
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

  return <AppShell user={user} onLogout={handleLogout} />
}
