import { useEffect, useRef, useState, useCallback } from 'react'
import {
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  deleteNotification,
  deleteAllNotifications,
  type NotificationItem,
} from '../api/notifications'
import { posterUrl } from '../utils/libraryItem'
import { UploadButtonIcon, CancelButtonIcon, RequestCardIcon } from './DetailCard'
import { useTooltip } from './Tooltip'
import { useRefrescoPorAvisos } from '../hooks/useRefrescoPorAvisos'
import { IconoPelicula } from './Iconos'

const POLL_MS = 30000

// Same icon+color as the Dashboard's "Contenido único" stat card
// (DashboardPage.tsx's ICON_UNIQUE/StatCard).
function UniqueContentIconSvg({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="#a855f7" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
      <circle cx="12" cy="12" r="3.2" />
    </svg>
  )
}

// "Contenido compatible" — a checkmark-in-circle (no existing button icon
// quite fits "match found").
function MatchFoundIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="10" /><path d="M8 12.5l2.5 2.5L16 9.5" />
    </svg>
  )
}

// "Contenido nuevo faltante" — same red-alert-triangle language as the rest
// of the app's warning states.
function MissingWarningIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 3 1 21h22L12 3z" /><line x1="12" y1="10" x2="12" y2="14" /><line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

function NuevaVersionIcon() {
  // Flecha hacia abajo sobre una bandeja: descargar/actualizar.
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M3 18v1a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-1" />
    </svg>
  )
}

// Small icon to the left of the notification's status title, colored by its
// severity `level` and matching the event's meaning — reusing the app's own
// action-button icons (DetailCard.tsx) where one already fits.
function NotifTitleIcon({ eventType, level }: { eventType: string; level: string }) {
  const color = level === 'success' ? 'var(--color-available)' : level === 'error' ? 'var(--color-error)' : level === 'warning' ? 'var(--color-warning)' : 'var(--color-indigo)'
  const icon =
    eventType === 'upload_completed' ? <UploadButtonIcon /> :
    eventType === 'upload_failed' ? <CancelButtonIcon /> :
    eventType === 'request_published' ? <RequestCardIcon /> :
    eventType === 'request_match_found' ? <MatchFoundIcon /> :
    eventType === 'content_missing_new' ? <MissingWarningIcon /> :
    eventType === 'content_unique_changed' ? <UniqueContentIconSvg size={14} /> :
    eventType === 'version_available' ? <NuevaVersionIcon /> :
    null
  if (!icon) return null
  return <span style={{ display: 'inline-flex', color, marginRight: 5, verticalAlign: -2 }}>{icon}</span>
}

// Same 28x42 shape as the Dashboard's "Actividad de subida" poster thumbs —
// shared by the real poster and the "simulated poster" box below, so both
// read as the same visual family.
function PosterBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="poster-thumb" style={{ width: 28, height: 42, borderRadius: 4, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
      {children}
    </div>
  )
}

// Real poster for a notification about one specific piece of content.
function NotifPoster({ url }: { url: string | null }) {
  return (
    <PosterBox>
      {url ? (
        <img
          src={posterUrl(url, 'w154')}
          alt=""
          loading="lazy"
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
        />
      ) : (
        <span style={{ display: 'inline-flex', fontSize: 14, opacity: 0.35 }}><IconoPelicula /></span>
      )}
    </PosterBox>
  )
}

// content_unique_changed has no single item (it's a totals summary), so
// nothing to put a real poster of — a poster-shaped box with the same
// "Contenido único" icon centered inside reads as part of the same family
// instead of looking like a missing/broken image.
function NotifUniqueContentPoster() {
  return (
    <PosterBox>
      <UniqueContentIconSvg size={16} />
    </PosterBox>
  )
}

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

// Where a notification click should actually go: the specific item's own
// dedicated page whenever we know which one. Two handoffs fire together:
// - sessionStorage (same one Dashboard already uses to deep-link into
//   Biblioteca/Subidas/Peticiones) for when the target page isn't mounted
//   yet — its own mount effect reads + clears it.
// - a same-tick custom event for when the target page is ALREADY the open
//   one — pushState+popstate is a no-op then (same route, React bails out,
//   nothing remounts), so a plain mount effect would never fire again.
// Falls back to `link` (an external eMuwarez URL, or nothing) otherwise.
// `n.link` stays as-is for Discord/Telegram — those can't act on
// sessionStorage or DOM events, so the backend keeps sending them a plain URL.
function goToNotification(n: NotificationItem) {
  if (n.entity_type === 'library_item' && n.entity_id != null) {
    try { sessionStorage.setItem('emuwarez_open_library_item', String(n.entity_id)) } catch { /* ignore */ }
    window.dispatchEvent(new CustomEvent('emuwarez:open-library-item', { detail: n.entity_id }))
    navigateTo('/library')
    return
  }
  if (n.entity_type === 'upload_job' && n.entity_id != null) {
    try { sessionStorage.setItem('emuwarez_open_upload', String(n.entity_id)) } catch { /* ignore */ }
    window.dispatchEvent(new CustomEvent('emuwarez:open-upload', { detail: n.entity_id }))
    navigateTo('/uploads')
    return
  }
  if (n.entity_type === 'request_item' && n.entity_id != null) {
    try { sessionStorage.setItem('emuwarez_open_request', String(n.entity_id)) } catch { /* ignore */ }
    window.dispatchEvent(new CustomEvent('emuwarez:open-request', { detail: n.entity_id }))
    navigateTo('/requests')
    return
  }
  if (n.event_type === 'content_unique_changed') {
    // Aportes = Aporta — same "¿nuevo contenido único?" set this
    // notification's counts describe, via the Aportes column's own filter.
    try { sessionStorage.setItem('emuwarez_library_filter_aporte', 'yes') } catch { /* ignore */ }
    window.dispatchEvent(new CustomEvent('emuwarez:library-filter-aporte', { detail: 'yes' }))
    navigateTo('/library')
    return
  }
  if (n.link) navigateTo(n.link)
}

function isNotificationClickable(n: NotificationItem): boolean {
  return !!n.link
    || (!!n.entity_type && n.entity_id != null)
    || n.event_type === 'content_unique_changed'
}

function DeleteNotificationButton({ onClick }: { onClick: () => void }) {
  const { triggerProps, tooltipNode } = useTooltip('Borrar notificación')
  return (
    <button
      type="button"
      className="notif-item-delete"
      aria-label="Borrar notificación"
      onClick={onClick}
      {...triggerProps}
    >
      ✕
      {tooltipNode}
    </button>
  )
}

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<NotificationItem[]>([])
  const [unread, setUnread] = useState(0)
  const [loading, setLoading] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const botonRef = useRef<HTMLButtonElement>(null)
  const bellTip = useTooltip('Notificaciones')

  // Solo cuenta la última lista pedida, y un cambio local (marcar, borrar) también tira las que iban en vuelo:
  // una respuesta anterior al cambio devolvería el aviso que acabas de borrar o el contador que acabas de poner a 0.
  const ultimoRefresco = useRef(0)
  const refresh = useCallback(async () => {
    const esta = ++ultimoRefresco.current
    try {
      const feed = await getNotifications({ limit: 50 })
      if (esta !== ultimoRefresco.current) return
      setItems(feed.notifications)
      setUnread(feed.unread_count)
    } catch {
      /* non-blocking — bell just stays as-is */
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])
  // La campana sondeaba cada 30 segundos, así que una notificación podía tardar
  // medio minuto en aparecer. Ahora sale al momento, y el sondeo se espacia a
  // dos minutos de red de seguridad mientras el canal esté vivo.
  useRefrescoPorAvisos(['notificacion'], refresh, {
    cadaSinCanal: POLL_MS,
    cadaConCanal: 120_000,
  })

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    // Escape devuelve el foco a la campana: si no, se queda en un aviso que acaba de desaparecer.
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      botonRef.current?.focus()
    }
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
      ultimoRefresco.current++
      setUnread(u => Math.max(0, u - 1))
      setItems(prev => prev.map(i => (i.id === n.id ? { ...i, read: true } : i)))
      // Si falla, se vuelve a lo que dice el servidor.
      try { await markNotificationRead(n.id) } catch { refresh() }
    }
    if (isNotificationClickable(n)) {
      setOpen(false)
      goToNotification(n)
    }
  }

  const handleMarkAll = async () => {
    ultimoRefresco.current++
    setUnread(0)
    setItems(prev => prev.map(i => ({ ...i, read: true })))
    try { await markAllNotificationsRead() } catch { refresh() }
  }

  const handleDelete = async (n: NotificationItem) => {
    ultimoRefresco.current++
    setItems(prev => prev.filter(i => i.id !== n.id))
    if (!n.read) setUnread(u => Math.max(0, u - 1))
    try { await deleteNotification(n.id) } catch { refresh() }
  }

  const handleDeleteAll = async () => {
    ultimoRefresco.current++
    setItems([])
    setUnread(0)
    try { await deleteAllNotifications() } catch { refresh() }
  }

  return (
    <div className="notif-bell" ref={rootRef}>
      <button
        ref={botonRef}
        className="topbar-btn"
        aria-label="Notificaciones"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={toggle}
        {...bellTip.triggerProps}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && <span className="notif-badge">{unread > 99 ? '99+' : unread}</span>}
        {bellTip.tooltipNode}
      </button>

      {open && (
        <div className="notif-dropdown" role="dialog" aria-label="Notificaciones">
          <div className="notif-dropdown-header">
            <span className="notif-dropdown-title">Notificaciones</span>
            <span style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              {unread > 0 && (
                <button className="notif-markall" onClick={handleMarkAll}>Marcar todo como leído</button>
              )}
              {items.length > 0 && (
                <button className="notif-markall notif-clearall" onClick={handleDeleteAll}>Borrar todo</button>
              )}
            </span>
          </div>
          <div className="notif-list">
            {loading && items.length === 0 && (
              <div className="notif-empty">Cargando…</div>
            )}
            {!loading && items.length === 0 && (
              <div className="notif-empty">No tienes notificaciones todavía.</div>
            )}
            {items.map(n => (
              <div key={n.id} className={`notif-item ${n.read ? 'read' : 'unread'} ${isNotificationClickable(n) ? 'clickable' : ''}`}>
                <button
                  type="button"
                  className="notif-item-main"
                  onClick={() => handleItemClick(n)}
                >
                  <span className="notif-item-body">
                    {/* Line 1: the notification's status. */}
                    <span className="notif-item-title"><NotifTitleIcon eventType={n.event_type} level={n.level} />{n.title}</span>
                    {/* Line 2: poster (or a simulated one) + content name + reason. */}
                    {(n.content_title || n.event_type === 'content_unique_changed') ? (
                      <span className="notif-item-content-row">
                        {n.content_title ? <NotifPoster url={n.poster_url} /> : <NotifUniqueContentPoster />}
                        <span className="notif-item-content-col">
                          {n.content_title && <span className="notif-item-content-title">{n.content_title}</span>}
                          {n.body && <span className="notif-item-text">{n.body}</span>}
                        </span>
                      </span>
                    ) : (
                      n.body && <span className="notif-item-text">{n.body}</span>
                    )}
                    <span className="notif-item-time">{relativeTime(n.created_at)}</span>
                  </span>
                </button>
                <DeleteNotificationButton onClick={() => handleDelete(n)} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
