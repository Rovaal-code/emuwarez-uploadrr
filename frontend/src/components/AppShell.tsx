import { useState } from 'react'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import type { CurrentUserResponse } from '../types/api'

// Pages
import { DashboardPage } from '../pages/DashboardPage'
import { LibraryPage } from '../pages/LibraryPage'
import { RequestsPage } from '../pages/RequestsPage'
import { UploadsPage } from '../pages/UploadsPage'
import { TasksPage } from '../pages/TasksPage'
import { InstancesPage } from '../pages/InstancesPage'
import { LogsPage } from '../pages/LogsPage'
import { SettingsPage } from '../pages/SettingsPage'
import { QueuePage } from '../pages/QueuePage'

interface AppShellProps {
  user: CurrentUserResponse | null
  onLogout: () => void
}

const PAGE_TITLE: Record<string, string> = {
  dashboard:  'Dashboard',
  queue:      'Cola operativa',
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
    case 'queue':      return <QueuePage onNavigate={onNavigate} />
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

export function AppShell({ user, onLogout }: AppShellProps) {
  const [activePage, setActivePage] = useState<string>('dashboard')

  return (
    <div className="app-shell">
      <Sidebar active={activePage} onNavigate={setActivePage} />
      <div className="main-content">
        <Topbar
          user={user}
          pageTitle={PAGE_TITLE[activePage] ?? ''}
          onLogout={onLogout}
        />
        <main className="page-container">
          <PageContent page={activePage} onNavigate={setActivePage} />
        </main>
      </div>
    </div>
  )
}
