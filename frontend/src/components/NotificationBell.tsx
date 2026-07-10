import { useEffect, useRef, useState, useCallback } from 'react'
import {
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  type NotificationItem,
} from '../api/notifications'

const POLL_MS = 30000

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const diff = Math.max(0, Date.now() - then)
  const min = Math.floor(diff / 60000)
  if (min < 1) return 'ahora mismo'
  if (min < 60) return `hace ${min} min`
  const h = Math.floor(min / 60)
  if (h < 24) return `hace ${h} h`
  const d = Math.floor(h / 24)
  if (d < 7) return `hace ${d} d`
  return new Date(iso).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

function navigateTo(link: string) {
  if (/^https?:\/\//i.test(link)) {
    window.open(link, '_blank', 'noopener,noreferrer')
    return
  }
  // Internal SPA path — push and let AppShell's popstate listener react.
  window.history.pushState({}, '', link)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<NotificationItem[]>([])
  const [unread, setUnread] = useState(0)
  const [loading, setLoading] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async () => {
    try {
      const feed = await getNotifications({ limit: 30 })
      setItems(feed.notifications)
      setUnread(feed.unread_count)
    } catch {
      /* non-blocking — bell just stays as-is */
    }
  }, [])

  // Initial load + polling for the unread badge.
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, POLL_MS)
    return () => clearInterval(t)
  }, [refresh])

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (next) {
      setLoading(true)
      await refresh()
      setLoading(false)
    }
  }

  const handleItemClick = async (n: NotificationItem) => {
    if (!n.read) {
      setUnread(u => Math.max(0, u - 1))
      setItems(prev => prev.map(i => (i.id === n.id ? { ...i, read: true } : i)))
      try { await markNotificationRead(n.id) } catch { /* ignore */ }
    }
    if (n.link) {
      setOpen(false)
      navigateTo(n.link)
    }
  }

  const handleMarkAll = async () => {
    setUnread(0)
    setItems(prev => prev.map(i => ({ ...i, read: true })))
    try { await markAllNotificationsRead() } catch { /* ignore */ }
  }

  return (
    <div className="notif-bell" ref={rootRef}>
      <button className="topbar-btn" title="Notificaciones" aria-label="Notificaciones" onClick={toggle}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && <span className="notif-badge">{unread > 99 ? '99+' : unread}</span>}
      </button>

      {open && (
        <div className="notif-dropdown" role="menu">
          <div className="notif-dropdown-header">
            <span className="notif-dropdown-title">Notificaciones</span>
            {unread > 0 && (
              <button className="notif-markall" onClick={handleMarkAll}>Marcar todo como leído</button>
            )}
          </div>
          <div className="notif-list">
            {loading && items.length === 0 && (
              <div className="notif-empty">Cargando…</div>
            )}
            {!loading && items.length === 0 && (
              <div className="notif-empty">No tienes notificaciones todavía.</div>
            )}
            {items.map(n => (
              <button
                key={n.id}
                className={`notif-item ${n.read ? 'read' : 'unread'} ${n.link ? 'clickable' : ''}`}
                onClick={() => handleItemClick(n)}
              >
                <span className="notif-item-dot" aria-hidden />
                <span className="notif-item-body">
                  <span className="notif-item-title">{n.title}</span>
                  {n.body && <span className="notif-item-text">{n.body}</span>}
                  <span className="notif-item-time">{relativeTime(n.created_at)}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
