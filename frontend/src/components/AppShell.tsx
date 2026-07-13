import { useState, useEffect, useCallback } from 'react'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import type { CurrentUserResponse } from '../types/api'
import { guardedLeave, hasUnsavedChanges } from '../utils/unsavedGuard'
import { UnsavedChangesModal } from './UnsavedChangesModal'

// Pages
import { DashboardPage } from '../pages/DashboardPage'
import { LibraryPage } from '../pages/LibraryPage'
import { RequestsPage } from '../pages/RequestsPage'
import { UploadsPage } from '../pages/UploadsPage'
import { TasksPage } from '../pages/TasksPage'
import { InstancesPage } from '../pages/InstancesPage'
import { LogsPage } from '../pages/LogsPage'
import { SettingsPage } from '../pages/SettingsPage'

interface AppShellProps {
  user: CurrentUserResponse | null
  onLogout: () => void
}

const PAGE_TITLE: Record<string, string> = {
  dashboard:  'Dashboard',
  library:    'Biblioteca',
  requests:   'Peticiones',
  uploads:    'Subidas',
  tasks:      'Tareas',
  instances:  'Instancias',
  logs:       'Logs',
  settings:   'Configuración',
}

function PageContent({ page, onNavigate }: { page: string; onNavigate: (p: string) => void }) {
  switch (page) {
    case 'dashboard':  return <DashboardPage onNavigate={onNavigate} />
    case 'library':    return <LibraryPage />
    case 'requests':   return <RequestsPage />
    case 'uploads':    return <UploadsPage />
    case 'tasks':      return <TasksPage />
    case 'instances':  return <InstancesPage />
    case 'logs':       return <LogsPage />
    case 'settings':   return <SettingsPage />
    default:           return <DashboardPage />
  }
}

// Tabs that map to a URL path, so the address bar reflects the current tab
// (bookmarkable / reloadable). The backend already serves index.html for any
// non-/api path (SPA fallback), so a deep link like /library works on reload.
const VALID_PAGES = ['dashboard', 'library', 'uploads', 'requests', 'tasks', 'instances', 'logs', 'settings']

function pageFromPath(): string {
  const seg = window.location.pathname.replace(/^\/+/, '').split('/')[0]
  return VALID_PAGES.includes(seg) ? seg : 'dashboard'
}

export function AppShell({ user, onLogout }: AppShellProps) {
  const [activePage, setActivePage] = useState<string>(pageFromPath)

  const navigate = useCallback((page: string) => {
    if (page === pageFromPath()) return
    // Ask (styled modal) before leaving a form with unsaved changes.
    guardedLeave(() => {
      setActivePage(page)
      const path = page === 'dashboard' ? '/' : `/${page}`
      if (window.location.pathname !== path) {
        window.history.pushState({}, '', path)
      }
    })
  }, [])

  // Keep the tab in sync with browser back/forward.
  useEffect(() => {
    const onPop = () => setActivePage(pageFromPath())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  // Warn before a full reload / closing the tab while there are unsaved changes.
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges()) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [])

  return (
    <div className="app-shell">
      <UnsavedChangesModal />
      <Sidebar active={activePage} onNavigate={navigate} />
      <div className="main-content">
        <Topbar
          user={user}
          pageTitle={PAGE_TITLE[activePage] ?? ''}
          onLogout={onLogout}
        />
        <main className="page-container">
          <PageContent page={activePage} onNavigate={navigate} />
        </main>
      </div>
    </div>
  )
}
