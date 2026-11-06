// @vitest-environment jsdom
/**
 * La franja «Tu cuenta en eMuwarez» del Panel lleva solo «Mis subidas»: Mensajes y Notificaciones ya están en la barra
 * superior (y en el cajón del móvil), y repetirlos la hacía caer a una segunda fila.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../context/PerfilEmuContext', () => ({
  tapar: (n: string) => '*'.repeat(Math.max(4, n.length)),
  usePerfilEmu: () => ({
    perfil: {
      configured: true, username: 'Kisnov', group: 'Uploader', uploaded: '1.23 TiB', downloaded: '412.8 GiB',
      ratio: '3.05', buffer: '2.6 TiB', seeding: 148, leeching: 0, seedbonus: 125430, hit_and_runs: 0,
      updated_at: null, error: null,
    },
    actualizar: async () => {},
    ocultarNombre: false,
    setOcultarNombre: () => {},
  }),
}))

import { CuentaEmu } from '../CuentaEmu'
import { desmontar, montar } from './dom'

describe('CuentaEmu', () => {
  afterEach(desmontar)

  it('enseña las cifras y un único enlace, «Mis subidas»', async () => {
    await montar(<CuentaEmu />)
    const enlaces = [...document.querySelectorAll('.cuenta-emu-enlaces a')]
    expect(enlaces).toHaveLength(1)
    expect(enlaces[0].textContent).toContain('Mis subidas')
    expect(enlaces[0].getAttribute('href')).toContain('/users/Kisnov/uploads')
    expect(document.body.textContent).not.toContain('Mensajes')
    expect(document.body.textContent).not.toContain('Notificaciones')
    expect(document.querySelector('.cuenta-emu-cifras')!.textContent).toContain('Ratio')
  })
})
