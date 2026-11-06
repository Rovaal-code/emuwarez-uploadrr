import type { CurrentUserResponse } from '../types/api'
import { tapar, usePerfilEmu } from '../context/PerfilEmuContext'
import { enlacesCuentaEmu } from '../utils/cuentaEmu'
import { cerrarSesion } from '../utils/cerrarSesion'
import { IconoCampana, IconoCorreo, IconoOjo, IconoSalir, IconoUsuario } from './Iconos'

// Lo que en escritorio vive en la cabecera (usuario, enlaces a eMuwarez, cerrar sesión) y en el móvil no cabe en ella:
// va al pie del cajón del menú.
export function CuentaDelCajon({ user, onLogout }: { user: CurrentUserResponse | null; onLogout: () => void }) {
  const { perfil, ocultarNombre, setOcultarNombre } = usePerfilEmu()
  const enlaces = perfil?.username ? enlacesCuentaEmu(perfil.username) : null

  return (
    <div className="cajon-cuenta">
      {user && (
        <div className="cajon-usuario">
          <IconoUsuario size={16} />
          <span className="cajon-usuario-nombre">{ocultarNombre ? tapar(user.username) : user.username}</span>
          <button
            type="button"
            className="cajon-ojo"
            onClick={() => setOcultarNombre(o => !o)}
            aria-label={ocultarNombre ? 'Mostrar usuario' : 'Ocultar usuario'}
          >
            <IconoOjo tachado={ocultarNombre} size={16} />
          </button>
        </div>
      )}
      {enlaces && (
        <>
          <a className="nav-item cajon-enlace" href={enlaces.mensajes} target="_blank" rel="noreferrer">
            <IconoCorreo size={18} /> Mensajes en eMuwarez<span className="solo-lector"> (se abre en otra pestaña)</span>
          </a>
          <a className="nav-item cajon-enlace" href={enlaces.notificaciones} target="_blank" rel="noreferrer">
            <IconoCampana size={18} /> Notificaciones en eMuwarez<span className="solo-lector"> (se abre en otra pestaña)</span>
          </a>
        </>
      )}
      <button type="button" className="nav-item cajon-salir" onClick={() => cerrarSesion(onLogout)}>
        <IconoSalir size={18} /> Cerrar sesión
      </button>
    </div>
  )
}
