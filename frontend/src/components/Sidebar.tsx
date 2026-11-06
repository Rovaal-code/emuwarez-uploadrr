import { useEffect, useRef, useState } from 'react'
import { NAV_ITEMS, type NavItem } from '../types/domain'
import { ServiceIcon } from './ServiceIcon'
import { useTooltip } from './Tooltip'
import { SystemStatusPanel } from './SystemStatusPanel'
import { CuentaDelCajon } from './CuentaDelCajon'
import { IconoAyuda, IconoCerrar, IconoDesplegar } from './Iconos'
import type { CurrentUserResponse } from '../types/api'

interface SidebarProps {
  active: string
  onNavigate: (id: string) => void
  // En ventanas estrechas la barra es un cajón: siempre con textos, y el logo la cierra.
  movil?: boolean
  abierta?: boolean
  onCerrar?: () => void
  // En el cajón: volver a ver el tour guiado (en la cabecera no cabe el botón).
  onTour?: () => void
  // En el cajón, al pie: tu usuario y cerrar sesión (en la cabecera del móvil no caben).
  user?: CurrentUserResponse | null
  onLogout?: () => void
}

const SIDEBAR_COLLAPSED_KEY = 'emuwarez_uploadrr_sidebar_collapsed'

// Entre el cajón (≤768 px) y unos 1100 px, la barra abierta se comía casi un tercio del ancho (240 de 820): ahí arranca
// plegada mientras el usuario no haya elegido. Lo que elija con el logo se guarda y manda en cualquier ancho.
export const CONSULTA_PLEGADA = '(max-width: 1099px)'

function loadCollapsed(): boolean | null {
  try {
    const guardado = localStorage.getItem(SIDEBAR_COLLAPSED_KEY)
    return guardado === null ? null : guardado === 'true'
  } catch { return null }
}

/** Si la ventana es de las que arrancan con la barra plegada; sigue los cambios de tamaño. */
function useVentanaPlegada(): boolean {
  const [plegada, setPlegada] = useState(() => window.matchMedia?.(CONSULTA_PLEGADA).matches ?? false)
  useEffect(() => {
    const consulta = window.matchMedia?.(CONSULTA_PLEGADA)
    if (!consulta) return
    const alCambiar = () => setPlegada(consulta.matches)
    consulta.addEventListener('change', alCambiar)
    return () => consulta.removeEventListener('change', alCambiar)
  }, [])
  return plegada
}

function NavIcon({ id }: { id: string }) {
  const icons: Record<string, React.ReactNode> = {
    dashboard: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" />
      </svg>
    ),
    queue: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <path d="M8 6h13M8 12h13M8 18h13" /><path d="M3 6h.01M3 12h.01M3 18h.01" />
      </svg>
    ),
    library: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <path d="M4 19V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14" />
        <path d="M4 19h16" /><path d="M8 7h8M8 11h5" />
      </svg>
    ),
    requests: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
        <rect x="9" y="3" width="6" height="4" rx="1" /><path d="M9 12h6M9 16h4" />
      </svg>
    ),
    uploads: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <path d="M12 19V5M5 12l7-7 7 7" /><path d="M5 19h14" />
      </svg>
    ),
    stats: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <path d="M3 3v18h18" /><path d="M7 15l4-4 3 3 5-6" />
      </svg>
    ),
    tasks: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </svg>
    ),
    instances: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <rect x="2" y="2" width="20" height="8" rx="2" /><rect x="2" y="14" width="20" height="8" rx="2" />
        <path d="M6 6h.01M6 18h.01" />
      </svg>
    ),
    logs: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14,2 14,8 20,8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" />
      </svg>
    ),
    settings: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
    ),
    guide: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
        <path d="M9 7h7M9 11h5" />
      </svg>
    ),
  }
  return <span className="nav-item-icon">{icons[id] ?? null}</span>
}

// Own component (not inlined in the .map() below) so its useTooltip() hook
// call — one per row — stays a top-level hook call of a component instance,
// not a hook called from inside a loop callback. Only shows the tooltip
// while collapsed (icon-only): the label is already visible as text
// otherwise, no need to hover for it.
function NavItemRow({ item, active, collapsed, onNavigate }: {
  item: NavItem
  active: boolean
  collapsed: boolean
  onNavigate: (id: string) => void
}) {
  const { triggerProps, tooltipNode } = useTooltip(collapsed ? item.label : null)
  return (
    <button
      type="button"
      className={`nav-item${active ? ' active' : ''}`}
      onClick={() => onNavigate(item.id)}
      aria-current={active ? 'page' : undefined}
      aria-label={collapsed ? item.label : undefined}
      {...triggerProps}
    >
      <NavIcon id={item.id} />
      {!collapsed && item.label}
      {tooltipNode}
    </button>
  )
}

export function Sidebar({ active, onNavigate, movil = false, abierta = false, onCerrar, onTour, user = null, onLogout }: SidebarProps) {
  const [collapsedGuardado, setCollapsed] = useState(loadCollapsed)
  const ventanaPlegada = useVentanaPlegada()
  const collapsed = (collapsedGuardado ?? ventanaPlegada) && !movil
  const nav = useRef<HTMLElement>(null)
  const { triggerProps: logoTip, tooltipNode: logoTooltip } =
    useTooltip(movil ? null : collapsed ? 'Expandir menú' : 'Contraer menú')

  // Al abrir el cajón el foco pasa a la sección actual.
  useEffect(() => {
    if (abierta) nav.current?.querySelector<HTMLElement>('[aria-current="page"]')?.focus()
  }, [abierta])

  function toggleCollapsed() {
    const next = !collapsed
    try { localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next)) } catch { /* ignore */ }
    setCollapsed(next)
  }

  return (
    <aside id="menu-lateral" className={`sidebar${collapsed ? ' collapsed' : ''}${abierta ? ' abierta' : ''}`}>
      <button
        type="button"
        className="sidebar-logo"
        onClick={movil ? onCerrar : toggleCollapsed}
        aria-expanded={movil ? undefined : !collapsed}
        aria-label={movil ? 'Cerrar menú' : collapsed ? 'Expandir menú' : 'Contraer menú'}
        {...logoTip}
      >
        <ServiceIcon type="emu" size={28} />
        {!collapsed && <span className="sidebar-logo-text" translate="no">eMuwarez Uploadrr</span>}
        {/* Plegada, el tooltip del logo no sale con el dedo: el chevrón dice que se puede abrir. */}
        {collapsed && <span className="sidebar-expandir"><IconoDesplegar abierto={false} size={12} /></span>}
        {movil && <span className="sidebar-cerrar"><IconoCerrar size={18} /></span>}
        {logoTooltip}
      </button>
      <nav className="sidebar-nav" ref={nav} aria-label="Secciones">
        {NAV_ITEMS.map((item) => (
          <NavItemRow
            key={item.id}
            item={item}
            active={active === item.id}
            collapsed={collapsed}
            onNavigate={id => { onNavigate(id); if (movil) onCerrar?.() }}
          />
        ))}
        {movil && onTour && (
          <button type="button" className="nav-item" onClick={onTour}>
            <span className="nav-item-icon"><IconoAyuda size={18} /></span>Ver el tour guiado
          </button>
        )}
      </nav>
      {movil && onLogout && <CuentaDelCajon user={user} onLogout={onLogout} />}
      <SystemStatusPanel collapsed={collapsed} />
    </aside>
  )
}
