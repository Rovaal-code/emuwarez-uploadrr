// @vitest-environment jsdom
/**
 * La campana: el contador de sin leer está en el nombre del botón, «Borrar todo» pide una segunda pulsación (no hay
 * deshacer) y se desarma solo, y un toque fuera cierra el panel (pointerdown: en iOS no hay eventos de ratón).
 */
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/notifications', () => ({
  getNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  deleteNotification: vi.fn(),
  deleteAllNotifications: vi.fn(),
}))
vi.mock('../../hooks/useRefrescoPorAvisos', () => ({ useRefrescoPorAvisos: vi.fn() }))

import { deleteAllNotifications, getNotifications } from '../../api/notifications'
import { NotificationBell } from '../NotificationBell'
import { boton, desmontar, esperar, montar, pulsar } from './dom'

const AVISO = {
  id: 1, event_type: 'upload_done', level: 'info', title: 'Subida terminada', body: 'Todo bien', read: false,
  created_at: '2026-11-01T10:00:00', link: null, entity_type: null, entity_id: null, content_title: null, poster_url: null,
}

beforeEach(() => {
  vi.mocked(getNotifications).mockReset()
  vi.mocked(getNotifications).mockResolvedValue({ notifications: [AVISO], unread_count: 1 } as never)
  vi.mocked(deleteAllNotifications).mockReset()
  vi.mocked(deleteAllNotifications).mockResolvedValue(undefined as never)
})
afterEach(desmontar)

const campana = () => document.querySelector<HTMLButtonElement>('.notif-bell > button')!

describe('NotificationBell', () => {
  it('el nombre del botón dice cuántas hay sin leer', async () => {
    await montar(<NotificationBell />)
    await esperar(() => campana().getAttribute('aria-label') === 'Notificaciones (1 sin leer)')
  })

  it('«Borrar todo» no borra a la primera pulsación y sí a la segunda', async () => {
    await montar(<NotificationBell />)
    await esperar(() => campana().getAttribute('aria-label')?.includes('sin leer'))
    await pulsar(campana())
    const borrar = await esperar(() => boton('Borrar todo'))

    await pulsar(borrar)
    expect(deleteAllNotifications).not.toHaveBeenCalled()
    expect(boton('¿Seguro? Borrar todo')).toBeDefined()

    await pulsar(boton('¿Seguro? Borrar todo'))
    expect(deleteAllNotifications).toHaveBeenCalledTimes(1)
  })

  it('la confirmación se desarma sola a los 4 segundos', async () => {
    await montar(<NotificationBell />)
    await esperar(() => campana().getAttribute('aria-label')?.includes('sin leer'))
    await pulsar(campana())
    const borrar = await esperar(() => boton('Borrar todo'))

    // Se espía el temporizador que arma la confirmación y se dispara a mano, sin esperar cuatro segundos de verdad.
    const espia = vi.spyOn(globalThis, 'setTimeout')
    await pulsar(borrar)
    expect(boton('¿Seguro? Borrar todo')).toBeDefined()
    const llamada = espia.mock.calls.find(c => c[1] === 4000)!
    expect(llamada).toBeDefined()
    await act(async () => { (llamada[0] as () => void)() })
    espia.mockRestore()

    expect(boton('¿Seguro? Borrar todo')).toBeUndefined()
    expect(boton('Borrar todo')).toBeDefined()
  })

  it('un toque fuera cierra el panel', async () => {
    await montar(<NotificationBell />)
    await pulsar(campana())
    expect(document.querySelector('.notif-dropdown')).not.toBeNull()
    await act(async () => { document.body.dispatchEvent(new Event('pointerdown', { bubbles: true })) })
    expect(document.querySelector('.notif-dropdown')).toBeNull()
  })
})
