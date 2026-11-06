import { logout } from '../api/auth'

/**
 * Cerrar sesión: avisa al servidor y, pase lo que pase, la aplicación vuelve al login. Si el aviso falla (sin red) la
 * sesión local se cierra igual y el error no queda sin atender. Lo comparten la cabecera y el cajón del móvil.
 */
export async function cerrarSesion(alSalir: () => void) {
  try {
    await logout()
  } catch (e) {
    console.warn('No se pudo avisar al servidor del cierre de sesión:', e)
  } finally {
    alSalir()
  }
}
