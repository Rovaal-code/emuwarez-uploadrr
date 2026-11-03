import { logout } from '../api/auth'
import type { CurrentUserResponse } from '../types/api'
import { NotificationBell } from './NotificationBell'
import { SyncProgressBanner } from './SyncProgressBanner'
import { useTour } from '../context/TourContext'
import { TOUR_STEPS } from '../tour/steps'
import { useTooltip } from './Tooltip'
import { IconoCampana, IconoCorreo, IconoUsuario } from './Iconos'
import { ServiceIcon } from './ServiceIcon'
import { tapar, usePerfilEmu } from '../context/PerfilEmuContext'
import { enlacesCuentaEmu } from '../utils/cuentaEmu'

interface TopbarProps {
  user: CurrentUserResponse | null
  pageTitle: string
  onLogout: () => void
}

export function Topbar({ user, pageTitle, onLogout }: TopbarProps) {
  const { start: startTour } = useTour()
  const { perfil, ocultarNombre: hideName, setOcultarNombre: setHideName } = usePerfilEmu()
  const tourTip = useTooltip('Ver el tour guiado')
  const eyeTip = useTooltip(hideName ? 'Mostrar usuario' : 'Ocultar usuario')
  const logoutTip = useTooltip('Cerrar sesión')
  const mensajesTip = useTooltip('Mensajes en eMuwarez')
  const notificacionesTip = useTooltip('Notificaciones en eMuwarez')
  const cuentaEmu = perfil?.username ? enlacesCuentaEmu(perfil.username) : null

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
      {/* Center slot for live sync status — same row as the page title, so
          it never changes the topbar's height whether a sync is running or
          not (see SyncProgressBanner: it used to live in the page body and
          pushed every card/table down when it appeared). */}
      <div className="topbar-center">
        <SyncProgressBanner />
      </div>
      <div className="topbar-right" data-tour="topbar-buttons">
        {/* Guided tour — relaunch any time */}
        <button
          type="button"
          className="topbar-btn"
          aria-label="Ver el tour guiado"
          onClick={() => startTour(TOUR_STEPS)}
          {...tourTip.triggerProps}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M9.1 9a2.9 2.9 0 0 1 5.7 1c0 1.9-2.7 2-2.8 3.8" />
            <circle cx="12" cy="17.2" r="0.85" fill="currentColor" stroke="none" />
          </svg>
          {tourTip.tooltipNode}
        </button>
        {/* Mensajes y notificaciones de eMuwarez, con su logo delante para no confundirlos con la campana de la app */}
        {cuentaEmu && (
          <div className="topbar-emu" role="group" aria-label="Tu cuenta en eMuwarez">
            <ServiceIcon type="emu" size={16} />
            <a className="topbar-emu-enlace" href={cuentaEmu.mensajes} target="_blank" rel="noreferrer"
              aria-label="Mensajes en eMuwarez (se abre en otra pestaña)" {...mensajesTip.triggerProps}>
              <IconoCorreo size={16} />
              {mensajesTip.tooltipNode}
            </a>
            <a className="topbar-emu-enlace" href={cuentaEmu.notificaciones} target="_blank" rel="noreferrer"
              aria-label="Notificaciones en eMuwarez (se abre en otra pestaña)" {...notificacionesTip.triggerProps}>
              <IconoCampana size={16} />
              {notificacionesTip.tooltipNode}
            </a>
          </div>
        )}
        {/* Notifications */}
        <NotificationBell />
        {/* User info — username only, with a toggle to obfuscate it */}
        {user && (
          <div className="topbar-user">
            <IconoUsuario size={15} />
            <span className="topbar-username">
              {hideName ? tapar(user.username) : user.username}
            </span>
            <button
              type="button"
              className="topbar-eye"
              onClick={() => setHideName(h => !h)}
              aria-label={hideName ? 'Mostrar usuario' : 'Ocultar usuario'}
              {...eyeTip.triggerProps}
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
              {eyeTip.tooltipNode}
            </button>
          </div>
        )}
        {/* Logout */}
        <button className="topbar-btn" onClick={handleLogout} aria-label="Cerrar sesión" {...logoutTip.triggerProps}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16,17 21,12 16,7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          {logoutTip.tooltipNode}
        </button>
      </div>
    </header>
  )
}
