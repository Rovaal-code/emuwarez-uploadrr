import { useState } from 'react'
import { logout } from '../api/auth'
import type { CurrentUserResponse } from '../types/api'
import { NotificationBell } from './NotificationBell'

interface TopbarProps {
  user: CurrentUserResponse | null
  pageTitle: string
  onLogout: () => void
}

export function Topbar({ user, pageTitle, onLogout }: TopbarProps) {
  const [hideName, setHideName] = useState(false)

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
        {/* Notifications */}
        <NotificationBell />
        {/* User info — username only, with a toggle to obfuscate it */}
        {user && (
          <div className="topbar-user">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
            <span className="topbar-username">
              {hideName ? '*'.repeat(Math.max(4, user.username.length)) : user.username}
            </span>
            <button
              type="button"
              className="topbar-eye"
              onClick={() => setHideName(h => !h)}
              title={hideName ? 'Mostrar usuario' : 'Ocultar usuario'}
              aria-label={hideName ? 'Mostrar usuario' : 'Ocultar usuario'}
            >
              {hideName ? (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                  <line x1="1" y1="1" x2="23" y2="23" />
                </svg>
              ) : (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
            </button>
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
