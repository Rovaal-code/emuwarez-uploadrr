// @vitest-environment jsdom
/**
 * El paso «Configuración» del tour tiene que encontrar su objetivo estando Configuración en cualquiera de sus
 * pestañas: antes el `data-tour` vivía dentro de la pestaña Configuración y, con otra abierta, el paso no resaltaba
 * nada. Hoy cuelga del marco de la página; esto lo fija, con las pestañas sustituidas por maquetas (aquí solo importa
 * el marco).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/maintenance', () => ({ getMaintenanceStatus: vi.fn(() => Promise.resolve({})) }))
vi.mock('../../pages/ajustes/ConfigTab', () => ({ ConfigTab: () => <div>pestaña config</div> }))
vi.mock('../../pages/ajustes/NotificationsTab', () => ({ NotificationsTab: () => <div>pestaña notificaciones</div> }))
vi.mock('../../pages/ajustes/DiagnosticsTab', () => ({ DiagnosticsTab: () => <div>pestaña diagnóstico</div> }))
vi.mock('../../pages/ajustes/BackupTab', () => ({ BackupTab: () => <div>pestaña backup</div> }))

import { SettingsPage } from '../../pages/SettingsPage'
import { TOUR_STEPS } from '../../tour/steps'
import { boton, desmontar, montar, pulsar } from './dom'

beforeEach(() => { localStorage.clear() })
afterEach(desmontar)

describe('paso «Configuración» del tour', () => {
  const paso = TOUR_STEPS.find(s => s.tab === 'settings')!

  it('el paso apunta a la sección Configuración', () => {
    expect(paso).toBeDefined()
    expect(paso.selector).toContain('settings-content')
  })

  it.each(['Configuración', 'Notificaciones', 'Diagnóstico', 'Backup'])('su objetivo existe con la pestaña «%s» abierta', async (pestana) => {
    await montar(<SettingsPage />)
    // «Configuración» está en el título de la página y en la pestaña: se pulsa la de las pestañas.
    await pulsar([...document.querySelectorAll('.aj-tab')].find(b => b.textContent === pestana) ?? boton(pestana))
    expect(document.querySelector(paso.selector)).not.toBeNull()
  })
})
