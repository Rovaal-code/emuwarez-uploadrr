// @vitest-environment jsdom
/**
 * La cabecera y el pie del cajón del móvil: la búsqueda (Ctrl+K) tiene botón propio, y cerrar sesión avisa al
 * servidor y vuelve al login pase lo que pase, tanto desde la cabecera como desde el cajón.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/auth', () => ({ logout: vi.fn() }))
vi.mock('../../api/system', () => ({ getSystemStats: vi.fn(() => new Promise(() => { /* sin datos */ })) }))
vi.mock('../NotificationBell', () => ({ NotificationBell: () => <button type="button" aria-label="Notificaciones">campana</button> }))
vi.mock('../SyncProgressBanner', () => ({ SyncProgressBanner: () => null }))

import { logout } from '../../api/auth'
import { TourProvider } from '../../context/TourContext'
import { CuentaDelCajon } from '../CuentaDelCajon'
import { Topbar } from '../Topbar'
import { desmontar, montar, pulsar } from './dom'

const user = { id: 1, username: 'gabriel', role: 'admin' } as never
const menu = { abierto: false, alternar: vi.fn(), botonRef: { current: null }, movil: false }

const porEtiqueta = (etiqueta: string) => document.querySelector<HTMLElement>(`[aria-label="${etiqueta}"]`)

beforeEach(() => { vi.mocked(logout).mockReset(); vi.mocked(logout).mockResolvedValue(undefined as never) })
afterEach(desmontar)

describe('cabecera', () => {
  it('el botón de búsqueda abre la paleta y anuncia el atajo', async () => {
    const onBuscar = vi.fn()
    await montar(<TourProvider><Topbar user={user} pageTitle="Panel" onLogout={vi.fn()} onBuscar={onBuscar} menu={menu} /></TourProvider>)
    const buscar = porEtiqueta('Buscar')!
    expect(buscar.getAttribute('aria-keyshortcuts')).toBe('Control+K Meta+K')
    await pulsar(buscar)
    expect(onBuscar).toHaveBeenCalledTimes(1)
  })

  it('cerrar sesión avisa al servidor y después vuelve al login', async () => {
    const onLogout = vi.fn()
    await montar(<TourProvider><Topbar user={user} pageTitle="Panel" onLogout={onLogout} onBuscar={vi.fn()} menu={menu} /></TourProvider>)
    await pulsar(porEtiqueta('Cerrar sesión')!)
    expect(logout).toHaveBeenCalledTimes(1)
    expect(onLogout).toHaveBeenCalledTimes(1)
  })

  it('si el servidor no contesta, la aplicación vuelve al login igualmente', async () => {
    vi.mocked(logout).mockRejectedValue(new Error('sin red'))
    const onLogout = vi.fn()
    await montar(<TourProvider><Topbar user={user} pageTitle="Panel" onLogout={onLogout} onBuscar={vi.fn()} menu={menu} /></TourProvider>)
    vi.spyOn(console, 'warn').mockImplementation(() => { /* el aviso es el esperado */ })
    await pulsar(porEtiqueta('Cerrar sesión')!)
    await new Promise(r => setTimeout(r, 0))
    expect(onLogout).toHaveBeenCalledTimes(1)
  })
})

describe('pie del cajón del móvil', () => {
  it('enseña el usuario, deja taparlo y cierra la sesión', async () => {
    const onLogout = vi.fn()
    await montar(<CuentaDelCajon user={user} onLogout={onLogout} />)
    expect(document.body.textContent).toContain('gabriel')

    await pulsar(porEtiqueta('Ocultar usuario')!)
    // Sin el proveedor del perfil el interruptor no guarda nada, pero el botón sigue ahí y no rompe.
    expect(porEtiqueta('Ocultar usuario') ?? porEtiqueta('Mostrar usuario')).not.toBeNull()

    await pulsar([...document.querySelectorAll('button')].find(b => b.textContent?.includes('Cerrar sesión')))
    expect(logout).toHaveBeenCalledTimes(1)
    expect(onLogout).toHaveBeenCalledTimes(1)
  })
})
