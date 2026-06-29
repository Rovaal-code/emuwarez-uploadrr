import { logout } from '../api/auth'
import type { CurrentUserResponse } from '../types/api'

interface TopbarProps {
  user: CurrentUserResponse | null
  pageTitle: string
  onLogout: () => void
}

export function Topbar({ user, pageTitle, onLogout }: TopbarProps) {
  async function handleLogout() {
    try {
      await logout()
    } finally {
      onLogout()
    }
  }

  return (
    <header className="topbar">
      <div className="topbar-left">
        <span className="topbar-title">{pageTitle}</span>
      </div>
      <div className="topbar-right">
        {/* Bell icon */}
        <button className="topbar-btn" title="Notificaciones" aria-label="Notificaciones">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
        </button>
        {/* User info */}
        {user && (
          <div className="topbar-user">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
            <div>
              <div className="topbar-username">{user.username}</div>
              <div className="topbar-role">{user.role}</div>
            </div>
          </div>
        )}
        {/* Logout */}
        <button className="topbar-btn" title="Cerrar sesión" onClick={handleLogout} aria-label="Cerrar sesión">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16,17 21,12 16,7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
        </button>
      </div>
    </header>
  )
}
