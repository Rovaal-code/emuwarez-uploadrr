import { cerrarSesion } from '../utils/cerrarSesion'
import type { CurrentUserResponse } from '../types/api'
import { NotificationBell } from './NotificationBell'
import { SyncProgressBanner } from './SyncProgressBanner'
import { useTour } from '../context/TourContext'
import { pasosDelTour } from '../tour/steps'
import { useTooltip } from './Tooltip'
import { IconoAyuda, IconoBuscar, IconoCampana, IconoCorreo, IconoOjo, IconoSalir, IconoUsuario } from './Iconos'
import { ServiceIcon } from './ServiceIcon'
import { tapar, usePerfilEmu } from '../context/PerfilEmuContext'
import { enlacesCuentaEmu } from '../utils/cuentaEmu'
import { BotonMenu } from './BotonMenu'
import type { useMenuMovil } from '../hooks/useMenuMovil'

interface TopbarProps {
  user: CurrentUserResponse | null
  pageTitle: string
  onLogout: () => void
  onBuscar: () => void
  menu: Pick<ReturnType<typeof useMenuMovil>, 'abierto' | 'alternar' | 'botonRef' | 'movil'>
}

// ⌘ K en Mac, Ctrl K en el resto: es lo que se lee en el botón de búsqueda.
function textoDelAtajo(): string {
  return /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘\u00A0K' : 'Ctrl\u00A0K'
}

export function Topbar({ user, pageTitle, onLogout, onBuscar, menu }: TopbarProps) {
  const { start: startTour } = useTour()
  const { perfil, ocultarNombre: hideName, setOcultarNombre: setHideName } = usePerfilEmu()
  const tourTip = useTooltip('Ver el tour guiado')
  const buscarTip = useTooltip('Buscar secciones y títulos de la Biblioteca')
  const eyeTip = useTooltip(hideName ? 'Mostrar usuario' : 'Ocultar usuario')
  const logoutTip = useTooltip('Cerrar sesión')
  const mensajesTip = useTooltip('Mensajes en eMuwarez')
  const notificacionesTip = useTooltip('Notificaciones en eMuwarez')
  const cuentaEmu = perfil?.username ? enlacesCuentaEmu(perfil.username) : null

  return (
    <header className="topbar">
      <div className="topbar-left">
        <BotonMenu abierto={menu.abierto} onAlternar={menu.alternar} botonRef={menu.botonRef} />
        {/* Miga de pan, no encabezado: el h1 de la pantalla es el título de la página (o el de la ficha abierta), y
            el lector de pantalla no tiene por qué oír el nombre de la sección dos veces seguidas. */}
        <p className="topbar-title" aria-hidden="true">{pageTitle}</p>
      </div>
      {/* Center slot for live sync status — same row as the page title, so
          it never changes the topbar's height whether a sync is running or
          not (see SyncProgressBanner: it used to live in the page body and
          pushed every card/table down when it appeared). */}
      <div className="topbar-center">
        <SyncProgressBanner />
      </div>
      <div className="topbar-right" data-tour="topbar-buttons">
        {/* Búsqueda (la misma paleta que Ctrl+K): en el móvil es el único camino, no hay teclado */}
        <button
          type="button"
          className="topbar-btn topbar-buscar"
          aria-label="Buscar"
          aria-haspopup="dialog"
          aria-keyshortcuts="Control+K Meta+K"
          onClick={onBuscar}
          {...buscarTip.triggerProps}
        >
          <IconoBuscar size={16} />
          <kbd className="topbar-atajo">{textoDelAtajo()}</kbd>
          {buscarTip.tooltipNode}
        </button>
        {/* Guided tour — relaunch any time (en el móvil está en el cajón) */}
        <button
          type="button"
          className="topbar-btn topbar-tour"
          aria-label="Ver el tour guiado"
          onClick={() => startTour(pasosDelTour(menu.movil))}
          {...tourTip.triggerProps}
        >
          <IconoAyuda size={16} />
          {tourTip.tooltipNode}
        </button>
        {/* Mensajes y notificaciones de eMuwarez, con su logo delante para no confundirlos con la campana de la app
            (en el móvil están en el cajón) */}
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
        {/* User info — username only, with a toggle to obfuscate it (en el móvil, en el cajón) */}
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
              <IconoOjo tachado={hideName} size={15} />
              {eyeTip.tooltipNode}
            </button>
          </div>
        )}
        {/* Logout (en el móvil, en el cajón) */}
        <button type="button" className="topbar-btn topbar-salir" onClick={() => cerrarSesion(onLogout)} aria-label="Cerrar sesión" {...logoutTip.triggerProps}>
          <IconoSalir size={16} />
          {logoutTip.tooltipNode}
        </button>
      </div>
    </header>
  )
}
