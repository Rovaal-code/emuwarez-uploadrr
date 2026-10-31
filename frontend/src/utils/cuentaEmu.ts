import { EMU_URL } from '../constants/emu'

// Las páginas de tu cuenta en eMuwarez (rutas de UNIT3D). Mensajes y
// notificaciones no están en la API: de ellos solo se puede dar el enlace.
export function enlacesCuentaEmu(usuario: string) {
  const perfil = `${EMU_URL}/users/${encodeURIComponent(usuario)}`
  return {
    perfil,
    mensajes: `${perfil}/conversations`,
    notificaciones: `${perfil}/notifications`,
    subidas: `${perfil}/uploads`,
  }
}

// Por debajo de 1 eMuwarez desactiva la API key (FAQ 1.9). "∞" es no haber bajado nada.
export function ratioBajo(ratio: string | null): boolean {
  return ratio != null && Number(ratio) < 1
}

// UNIT3D escribe "1.23 TiB" y "4.1"; en la app la coma es el decimal.
export function decimalEs(valor: string): string {
  return valor.replace(/(\d)\.(\d)/, '$1,$2')
}
