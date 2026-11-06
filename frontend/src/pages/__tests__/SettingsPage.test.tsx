// @vitest-environment jsdom
// Fija el comportamiento de Configuración (guardar, cambios sin guardar, secretos enmascarados,
// confirmaciones de VACUUM y de restaurar) para poder partir la página sin cambiarlo.
import { act, StrictMode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SettingsData } from '../../api/settings'

vi.mock('../../api/settings', () => ({ fetchSettings: vi.fn(), updateSettings: vi.fn() }))
vi.mock('../../api/maintenance', () => ({
  getMaintenanceStatus: vi.fn(), createBackup: vi.fn(), listBackups: vi.fn(), downloadBackup: vi.fn(),
  uploadBackup: vi.fn(), restoreBackup: vi.fn(), runIntegrityCheck: vi.fn(), runVacuum: vi.fn(),
  getVersionInfo: vi.fn(),
}))
vi.mock('../../api/integrationTests', () => ({
  testTmdbConnection: vi.fn(), testEmuwarezConnection: vi.fn(), testQbitConnection: vi.fn(), testImghostConnection: vi.fn(),
}))
vi.mock('../../api/notifications', () => ({ testDiscordNotification: vi.fn(), testTelegramNotification: vi.fn() }))
vi.mock('../../api/auth', () => ({
  getMe: vi.fn(), changeCredentials: vi.fn(), getSessions: vi.fn(), closeOtherSessions: vi.fn(),
}))
vi.mock('../../api/system', () => ({ getUploadConcurrencyEstimate: vi.fn() }))
vi.mock('../../api/widget', () => ({
  getWidgetKeyStatus: vi.fn(), generateWidgetKey: vi.fn(), removeWidgetKey: vi.fn(),
}))

import { fetchSettings, updateSettings } from '../../api/settings'
import {
  getMaintenanceStatus, listBackups, getVersionInfo, runVacuum, restoreBackup,
} from '../../api/maintenance'
import { testImghostConnection, testQbitConnection } from '../../api/integrationTests'
import { testDiscordNotification } from '../../api/notifications'
import { getMe, changeCredentials, getSessions, closeOtherSessions } from '../../api/auth'
import { getWidgetKeyStatus, generateWidgetKey, removeWidgetKey } from '../../api/widget'
import { hasUnsavedChanges, setLeavePrompt } from '../../utils/unsavedGuard'
import { SettingsPage } from '../SettingsPage'
import { formatDate } from '../../utils/format'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const AJUSTES: SettingsData = {
  default_release_tag: 'GRUPO',
  upload_tags: ['GRUPO', 'OTRO'],
  provider_priority_order: ['netflix'],
  tmdb_watch_region: 'ES',
  tmdb_localize_series_titles: true,
  qbit_url: 'http://qbit:8080',
  qbit_tag: 'Subidas',
  qbit_public_url: null,
  source_engine_enabled: false,
  emu_add_logo: true,
  emu_per_episode_screens: false,
  remux_track_mode: 'solo_renombrar',
  remux_no_reflink_copies: false,
  qbit_username: 'admin',
  qbit_password_configured: true,
  qbit_qui_configured: false,
  qbit_configured: true,
  image_hosts_available: [
    { id: 'imgbox', label: 'imgbox', needs_key: false, url: 'https://imgbox.com' },
    { id: 'imgbb', label: 'imgbb', needs_key: true, url: 'https://imgbb.com' },
  ],
  image_hosts_enabled: ['imgbb'],
  image_host_keys_configured: [],
  tmdb_api_key_configured: true,
  tmdb_api_key_masked: 'tmdb****1234',
  emu_api_key_configured: true,
  emu_api_key_masked: 'emu****5678',
  emu_username: 'gabriel',
  uploadrr_path: null,
  uploadrr_runtime_type: 'uploadrr_emu',
  uploadrr_python_path: null,
  uploadrr_timeout: 600,
  uploadrr_allowed_roots: ['/data'],
  notify_discord_enabled: true,
  notify_discord_webhook_configured: true,
  notify_discord_webhook_masked: 'https://discord****abcd',
  notify_telegram_enabled: false,
  notify_telegram_bot_token_configured: false,
  notify_telegram_bot_token_masked: null,
  notify_telegram_chat_id: '',
  notify_ui_enabled: true,
  notify_event_types: [{ code: 'upload_done', label: 'Subida terminada' }],
  notify_ui_events: ['upload_done'],
  notify_discord_events: [],
  notify_telegram_events: [],
  notify_lote_modo: 'por_subida',
  series_ignore_specials: true,
  sincronizar_al_volver_instancia: true,
  recent_activity_limit: 100,
  upload_max_concurrent: 1,
  path_mappings: [],
}

const COPIA = {
  name: 'copia-1.tar.gz', path: '/b/copia-1.tar.gz', size_bytes: 2048,
  created_at: '2026-11-01T10:00:00', tipo: 'manual' as const, con_claves: false,
}

let raiz: Root
let contenedor: HTMLDivElement

async function esperar() {
  await act(async () => { await new Promise(r => setTimeout(r, 0)) })
}

async function montar(estricto = false) {
  contenedor = document.createElement('div')
  document.body.appendChild(contenedor)
  raiz = createRoot(contenedor)
  await act(async () => { raiz.render(estricto ? <StrictMode><SettingsPage /></StrictMode> : <SettingsPage />) })
  await esperar()
}

function boton(texto: string): HTMLButtonElement {
  const b = [...document.body.querySelectorAll('button')].find(x => x.textContent?.trim() === texto)
  if (!b) throw new Error(`No hay botón «${texto}»`)
  return b as HTMLButtonElement
}

function porPlaceholder(texto: string): HTMLInputElement {
  const i = [...document.body.querySelectorAll('input')].find(x => x.placeholder.startsWith(texto))
  if (!i) throw new Error(`No hay campo con placeholder «${texto}»`)
  return i
}

// El campo de la etiqueta que empieza por `texto`.
function campo(texto: string): HTMLInputElement {
  const l = [...document.body.querySelectorAll('label')].find(x => x.textContent?.trim().startsWith(texto))
  const i = l?.parentElement?.querySelector('input')
  if (!i) throw new Error(`No hay campo «${texto}»`)
  return i
}

async function pulsar(el: HTMLElement) {
  await act(async () => { el.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
  await esperar()
}

async function escribir(el: HTMLInputElement | HTMLSelectElement, valor: string) {
  await act(async () => {
    const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(proto, 'value')!.set!.call(el, valor)
    el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }))
  })
}

const texto = () => document.body.textContent ?? ''
// La barra de guardado de Configuración, con su contador.
const hayCambios = () => /campos? (ha|han) cambiado/.test(texto())

beforeEach(() => {
  vi.mocked(fetchSettings).mockImplementation(async () => structuredClone(AJUSTES))
  // Como el servidor: devuelve los ajustes ya guardados, y las rutas permitidas como lista.
  vi.mocked(updateSettings).mockImplementation(async p => ({
    ...structuredClone(AJUSTES), ...p, clear: undefined,
    uploadrr_allowed_roots: typeof p.uploadrr_allowed_roots === 'string' ? p.uploadrr_allowed_roots.split(',').map(x => x.trim()) : AJUSTES.uploadrr_allowed_roots,
  } as unknown as SettingsData))
  vi.mocked(getMaintenanceStatus).mockResolvedValue({
    ok: true,
    config_inventory: { config_dir: '/config', exists: true, files: [], total_size_bytes: 0 },
    database: { ok: true, db_path: '/config/app.db', size_bytes: 4096, page_count: 4, freelist_count: 0, fragmentation_pct: 0 },
    backups_count: 1,
    latest_backup: null,
  })
  vi.mocked(listBackups).mockResolvedValue({ ok: true, backups: [COPIA], count: 1, backup_dir: '/b' })
  vi.mocked(getVersionInfo).mockResolvedValue({ version: '0.14.0', estado: 'al_dia', ultima: {} })
  vi.mocked(getMe).mockResolvedValue({ username: 'admin' } as Awaited<ReturnType<typeof getMe>>)
  vi.mocked(getWidgetKeyStatus).mockResolvedValue({ configurada: false })
  vi.mocked(getSessions).mockResolvedValue({
    sessions: [
      { id: 1, current: true, created_at: '2026-11-01T10:00:00', last_used_at: '2026-11-01T10:00:00', user_agent: null, ip_address: '1.1.1.1' },
      { id: 2, current: false, created_at: '2026-10-01T10:00:00', last_used_at: '2026-10-02T10:00:00', user_agent: null, ip_address: '2.2.2.2' },
    ],
    inactive_days: 30,
  })
})

afterEach(async () => {
  await act(async () => { raiz.unmount() })
  contenedor.remove()
  setLeavePrompt(null)
  vi.clearAllMocks()
})

describe('Configuración: pestaña de ajustes', () => {
  it('carga los ajustes, enseña las claves enmascaradas y no vuelca ningún secreto en los campos', async () => {
    await montar()
    expect(fetchSettings).toHaveBeenCalled()
    expect(texto()).toContain('emu****5678')
    expect(texto()).toContain('tmdb****1234')
    expect(porPlaceholder('API key de eMuwarez').value).toBe('')
    expect(porPlaceholder('API key de TMDb').value).toBe('')
    // qBittorrent: hay contraseña guardada, el campo solo lo insinúa
    const pass = campo('Contraseña (dejar vacío')
    expect(pass.value).toBe('')
    expect(pass.placeholder).toBe('••••••••')
    expect(campo('Tag').value).toBe('Subidas')
    expect(document.querySelector('[data-tour="settings-content"]')).not.toBeNull()
    expect(hayCambios()).toBe(false)
  })

  it('el paso «Configuración» del tour encuentra su marco en todas las pestañas', async () => {
    await montar()
    for (const pestana of ['Configuración', 'Notificaciones', 'Diagnóstico', 'Backup']) {
      await pulsar(boton(pestana))
      expect(document.querySelectorAll('[data-tour="settings-content"]')).toHaveLength(1)
    }
  })

  it('un cambio marca «Cambios sin guardar», registra el guardián y guardar envía solo lo cambiado más el resto del formulario', async () => {
    await montar()
    expect(hasUnsavedChanges()).toBe(false)
    await escribir(campo('Tag'), 'Nuevo')
    expect(hayCambios()).toBe(true)
    expect(hasUnsavedChanges()).toBe(true)

    await pulsar(boton('Guardar'))
    expect(updateSettings).toHaveBeenCalledTimes(1)
    const payload = vi.mocked(updateSettings).mock.calls[0][0]
    expect(payload).toMatchObject({
      default_release_tag: 'GRUPO',
      upload_tags: ['GRUPO', 'OTRO'],
      tmdb_watch_region: 'ES',
      tmdb_localize_series_titles: true,
      qbit_url: 'http://qbit:8080',
      qbit_public_url: '',
      qbit_tag: 'Nuevo',
      qbit_username: 'admin',
      image_hosts_enabled: ['imgbb'],
      uploadrr_allowed_roots: '/data',
      remux_track_mode: 'solo_renombrar',
      upload_max_concurrent: 1,
    })
    // sin escribir una clave nueva no viaja ninguna
    for (const k of ['tmdb_api_key', 'emu_api_key', 'qbit_password', 'qbit_qui_proxy_url', 'clear']) {
      expect(payload).not.toHaveProperty(k)
    }
    expect(texto()).toContain('✓ Configuración guardada')
    expect(hayCambios()).toBe(false)
    expect(hasUnsavedChanges()).toBe(false)
  })

  it('una clave nueva viaja al guardar y el campo se vacía después', async () => {
    await montar()
    await escribir(porPlaceholder('API key de eMuwarez'), '  clave-nueva  ')
    await escribir(porPlaceholder('API key de TMDb'), 'tmdb-nueva')
    expect(hayCambios()).toBe(true)
    await pulsar(boton('Guardar'))
    const payload = vi.mocked(updateSettings).mock.calls[0][0]
    expect(payload.emu_api_key).toBe('clave-nueva')
    expect(payload.tmdb_api_key).toBe('tmdb-nueva')
    expect(porPlaceholder('API key de eMuwarez').value).toBe('')
    expect(porPlaceholder('API key de TMDb').value).toBe('')
    expect(hayCambios()).toBe(false)
  })

  it('quitar la contraseña de qBittorrent la manda en `clear` y se puede deshacer', async () => {
    await montar()
    await pulsar(boton('Quitar la contraseña'))
    expect(campo('Contraseña (dejar vacío').placeholder).toBe('Se quitará al guardar')
    expect(hayCambios()).toBe(true)
    await pulsar(boton('No quitarla'))
    expect(hayCambios()).toBe(false)
    await pulsar(boton('Quitar la contraseña'))
    await pulsar(boton('Guardar'))
    expect(vi.mocked(updateSettings).mock.calls[0][0]).toMatchObject({ clear: ['qbit_password'] })
  })

  it('una URL de qBittorrent inválida no se guarda', async () => {
    await montar()
    await escribir(campo('URL del WebUI'), 'qbit.local')
    await pulsar(boton('Guardar'))
    expect(updateSettings).not.toHaveBeenCalled()
    expect(texto()).toContain('La URL de qBittorrent debe empezar por http:// o https://')
  })

  it('la URL pública de qBittorrent viaja al guardar, sin espacios', async () => {
    await montar()
    expect(campo('URL pública del WebUI').value).toBe('')
    await escribir(campo('URL pública del WebUI'), '  https://qbit.midominio.es  ')
    expect(hayCambios()).toBe(true)
    await pulsar(boton('Guardar'))
    expect(vi.mocked(updateSettings).mock.calls[0][0]).toMatchObject({
      qbit_url: 'http://qbit:8080', qbit_public_url: 'https://qbit.midominio.es',
    })
  })

  it.each(['qbit.local', 'ftp://qbit.local', 'http://admin:clave@qbit.local:8080'])(
    'la URL pública «%s» no se guarda: sin http(s) o con usuario y contraseña', async (mala) => {
      await montar()
      await escribir(campo('URL pública del WebUI'), mala)
      await pulsar(boton('Guardar'))
      expect(updateSettings).not.toHaveBeenCalled()
      expect(texto()).toContain('La URL pública debe empezar por http:// o https://')
      expect(campo('URL pública del WebUI').getAttribute('aria-invalid')).toBe('true')
    })

  it('un grupo escrito sin pulsar «Añadir» también se guarda', async () => {
    await montar()
    await escribir(porPlaceholder('Añadir otro grupo'), 'TERCERO')
    expect(hayCambios()).toBe(true)
    await pulsar(boton('Guardar'))
    expect(vi.mocked(updateSettings).mock.calls[0][0].upload_tags).toEqual(['GRUPO', 'OTRO', 'TERCERO'])
    expect(porPlaceholder('Añadir otro grupo').value).toBe('')
  })

  it('el botón Probar de qBittorrent usa lo escrito y enseña el resultado', async () => {
    vi.mocked(testQbitConnection).mockResolvedValue({ ok: true, service: 'qbittorrent', status: 'ok', message: 'Conectado' })
    await montar()
    await escribir(campo('Contraseña (dejar vacío'), 'secreta')
    const probar = [...document.body.querySelectorAll('button')].filter(b => b.textContent === 'Probar conexión')
    // eMuwarez, TMDb y qBittorrent, en ese orden
    await pulsar(probar[2])
    expect(testQbitConnection).toHaveBeenCalledWith({
      url: 'http://qbit:8080', username: 'admin', password: 'secreta', qui_proxy_url: undefined,
    })
  })

  it('la clave de un proveedor de imágenes se comprueba antes de guardarla y se guarda aparte del botón global', async () => {
    vi.mocked(testImghostConnection).mockResolvedValue({ ok: true, service: 'imghost', status: 'ok', message: 'ok' })
    await montar()
    await pulsar(boton('API key'))
    const entrada = porPlaceholder('API key de imgbb')
    await escribir(entrada, ' kk ')
    // la clave sin guardar cuenta como cambio pendiente aunque el formulario no lo sea
    expect(hasUnsavedChanges()).toBe(true)
    await pulsar(boton('Guardar'))
    expect(testImghostConnection).toHaveBeenCalledWith('imgbb', 'kk')
    expect(updateSettings).toHaveBeenCalledWith({ image_host_keys: { imgbb: 'kk' } })
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
    expect(hasUnsavedChanges()).toBe(false)
  })

  it('si la clave del proveedor de imágenes no vale, no se guarda y se queda el modal', async () => {
    vi.mocked(testImghostConnection).mockResolvedValue({ ok: false, service: 'imghost', status: 'invalid_key', message: 'Clave inválida' })
    await montar()
    await pulsar(boton('API key'))
    await escribir(porPlaceholder('API key de imgbb'), 'mala')
    await pulsar(boton('Guardar'))
    expect(updateSettings).not.toHaveBeenCalled()
    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull()
  })

  it('cambiar de pestaña con cambios pregunta antes y solo cambia si se confirma', async () => {
    const preguntar = vi.fn()
    setLeavePrompt(preguntar)
    await montar()
    await escribir(campo('Tag'), 'Nuevo')
    await pulsar(boton('Notificaciones'))
    expect(preguntar).toHaveBeenCalledTimes(1)
    expect(texto()).not.toContain('Notificaciones UI')
    await act(async () => { preguntar.mock.calls[0][0]() })
    await esperar()
    expect(texto()).toContain('Notificaciones UI')
  })

  it('sin cambios, cambiar de pestaña es inmediato', async () => {
    const preguntar = vi.fn()
    setLeavePrompt(preguntar)
    await montar()
    await pulsar(boton('Notificaciones'))
    expect(preguntar).not.toHaveBeenCalled()
    expect(texto()).toContain('Notificaciones UI')
  })

  it('un fallo al guardar enseña el error y deja los cambios pendientes', async () => {
    vi.mocked(updateSettings).mockRejectedValueOnce(new Error('boom'))
    await montar()
    await escribir(campo('Tag'), 'Nuevo')
    await pulsar(boton('Guardar'))
    expect(texto()).toContain('✗ boom')
    expect(hayCambios()).toBe(true)
  })
})

describe('Configuración: índice, buscador, barra de guardado y Avanzado', () => {
  const seccion = (id: string) => document.querySelector<HTMLElement>(`[data-seccion="${id}"]`)!
  const visibles = () => [...document.querySelectorAll<HTMLElement>('[data-seccion]')].filter(e => !e.hidden).map(e => e.dataset.seccion)
  const enlace = (titulo: string) => [...document.querySelectorAll<HTMLButtonElement>('.aj-indice__enlace')].find(b => b.textContent === titulo)!
  const buscar = (q: string) => escribir(document.querySelector<HTMLInputElement>('input[aria-label="Buscar en Configuración"]')!, q)
  const cambios = () => document.querySelector('[role="status"].aj-guardado__cuenta')?.textContent
  const cabeceraAvanzado = () => document.querySelector<HTMLButtonElement>('.aj-avanzado__cabecera')!

  it('el índice enseña un enlace por cada tarjeta que hay, dentro de una nav con nombre', async () => {
    await montar()
    const nav = document.querySelector('nav[aria-label="Secciones de Configuración"]')!
    expect([...nav.querySelectorAll('button')].map(b => b.textContent)).toEqual([
      'eMuwarez', 'TMDb', 'qBittorrent', 'Proveedores de vídeo', 'Proveedores de imágenes', 'Otros',
      'Widget para Homepage', 'Cuenta', 'Sesiones abiertas', 'Avanzado',
    ])
    expect(nav.querySelectorAll('[aria-current]').length).toBe(1)
  })

  it('un enlace salta a su tarjeta, le da el foco y la resalta', async () => {
    const saltar = vi.fn()
    Element.prototype.scrollIntoView = saltar
    await montar()
    await pulsar(enlace('TMDb'))
    await act(async () => { await new Promise(r => requestAnimationFrame(() => r(null))) })
    expect(saltar).toHaveBeenCalled()
    expect(document.activeElement).toBe(seccion('tmdb'))
    expect(seccion('tmdb').className).toContain('aj-seccion--resaltada')
    expect(enlace('TMDb').getAttribute('aria-current')).toBe('true')
  })

  it('la sección activa sigue al desplazamiento y la última se activa en cuanto se ve entera', async () => {
    const avisos: ((e: Partial<IntersectionObserverEntry>[]) => void)[] = []
    vi.stubGlobal('IntersectionObserver', class {
      constructor(cb: (e: Partial<IntersectionObserverEntry>[]) => void) { avisos.push(cb) }
      observe() {}
      disconnect() {}
    })
    try {
      await montar()
      const [franja, final] = avisos
      expect(enlace('eMuwarez').getAttribute('aria-current')).toBe('true')
      await act(async () => { franja([{ target: seccion('qbittorrent'), isIntersecting: true }]) })
      expect(enlace('qBittorrent').getAttribute('aria-current')).toBe('true')
      expect(enlace('eMuwarez').getAttribute('aria-current')).toBeNull()
      await act(async () => { franja([{ target: seccion('qbittorrent'), isIntersecting: false }, { target: seccion('otros'), isIntersecting: true }]) })
      expect(enlace('Otros').getAttribute('aria-current')).toBe('true')
      await act(async () => { final([{ target: seccion('avanzado'), intersectionRatio: 1 }]) })
      expect(enlace('Avanzado').getAttribute('aria-current')).toBe('true')
      await act(async () => { final([{ target: seccion('avanzado'), intersectionRatio: 0.4 }]) })
      expect(enlace('Otros').getAttribute('aria-current')).toBe('true')
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('el buscador filtra por título y por etiqueta de campo, y avisa si no hay resultados', async () => {
    await montar()
    expect(visibles()).toHaveLength(10)
    await buscar('qbit')
    expect(visibles()).toEqual(['qbittorrent'])
    expect(document.querySelectorAll('.aj-indice__enlace')).toHaveLength(1)
    // etiqueta de un campo de la tarjeta de TMDb, sin acentos ni mayúsculas
    await buscar('REGION')
    expect(visibles()).toEqual(['tmdb'])
    await buscar('zzz')
    expect(visibles()).toEqual([])
    expect(texto()).toContain('Ninguna sección coincide con «zzz».')
    expect(texto()).toContain('Las notificaciones (Discord, Telegram)')
    await buscar('')
    expect(visibles()).toHaveLength(10)
    expect(texto()).not.toContain('Ninguna sección coincide')
  })

  it('el buscador también lee ayudas, botones y sinónimos: «clave», «token» e «imgbox» encuentran sus tarjetas', async () => {
    await montar()
    await buscar('clave')
    expect(visibles()).toEqual(expect.arrayContaining(['emuwarez', 'tmdb', 'proveedores-imagenes', 'widget']))
    await buscar('token')
    expect(visibles()).toEqual(expect.arrayContaining(['emuwarez', 'tmdb', 'widget']))
    // imgbox solo sale en el botón «Quitar imgbox» (una ✕) y en el nombre del proveedor
    await buscar('imgbox')
    expect(visibles()).toEqual(['proveedores-imagenes'])
    // una ayuda de campo: «Usada para leer el catálogo y las peticiones de eMuwarez»
    await buscar('catalogo')
    expect(visibles()).toContain('emuwarez')
  })

  it('el buscador marca el primer campo que coincide, y lo desmarca al cambiar o vaciar la búsqueda', async () => {
    await montar()
    await buscar('interfaz')
    const marcados = () => [...document.querySelectorAll('.aj-coincide')]
    expect(marcados()).toHaveLength(1)
    expect(marcados()[0].textContent).toContain('Tamaño de interfaz')
    await buscar('REGION')
    expect(marcados()).toHaveLength(1)
    expect(marcados()[0].closest('[data-seccion]')?.getAttribute('data-seccion')).toBe('tmdb')
    await buscar('')
    expect(marcados()).toHaveLength(0)
  })

  it('el filtrado no desmonta las tarjetas: lo escrito en una oculta se conserva', async () => {
    await montar()
    await escribir(campo('Tag'), 'Nuevo')
    await buscar('tmdb')
    await buscar('')
    expect(campo('Tag').value).toBe('Nuevo')
  })

  it('la barra de guardado cuenta los campos que han cambiado de verdad', async () => {
    await montar()
    expect(cambios()).toBeUndefined()
    await escribir(campo('Tag'), 'Nuevo')
    expect(cambios()).toBe('1 campo ha cambiado')
    await escribir(porPlaceholder('API key de TMDb'), 'k')
    await escribir(campo('URL del WebUI'), 'http://otro')
    expect(cambios()).toBe('3 campos han cambiado')
    // volver al valor cargado no cuenta
    await escribir(campo('Tag'), 'Subidas')
    expect(cambios()).toBe('2 campos han cambiado')
    await escribir(porPlaceholder('API key de TMDb'), '')
    await escribir(campo('URL del WebUI'), 'http://qbit:8080')
    expect(cambios()).toBeUndefined()
    expect(() => boton('Guardar')).toThrow()
  })

  it('guardar desde la barra envía el formulario y la barra desaparece; no hay un segundo botón en la cabecera', async () => {
    await montar()
    await escribir(campo('Tag'), 'Nuevo')
    expect([...document.querySelectorAll('button')].filter(b => b.textContent === 'Guardar')).toHaveLength(1)
    expect(() => boton('Guardar configuración')).toThrow()
    await pulsar(boton('Guardar'))
    expect(updateSettings).toHaveBeenCalledTimes(1)
    expect(cambios()).toBeUndefined()
  })

  it('Avanzado viene plegado, se despliega, guarda lo que se escribe dentro y no lo pierde al plegarlo', async () => {
    await montar()
    const cabecera = cabeceraAvanzado()
    expect(cabecera.getAttribute('aria-expanded')).toBe('false')
    const cuerpo = document.getElementById(cabecera.getAttribute('aria-controls')!)!
    expect(cuerpo.hidden).toBe(true)
    await pulsar(cabecera)
    expect(cabecera.getAttribute('aria-expanded')).toBe('true')
    expect(cuerpo.hidden).toBe(false)
    await escribir(campo('Rutas permitidas'), '/data, /media')
    expect(cambios()).toBe('1 campo ha cambiado')
    await pulsar(cabecera)
    expect(cuerpo.hidden).toBe(true)
    expect(cambios()).toBe('1 campo ha cambiado')
    await pulsar(boton('Guardar'))
    expect(vi.mocked(updateSettings).mock.calls[0][0].uploadrr_allowed_roots).toBe('/data, /media')
  })

  it('el salto del índice y una búsqueda que acierta en Avanzado lo abren', async () => {
    await montar()
    const cabecera = cabeceraAvanzado()
    await pulsar(enlace('Avanzado'))
    expect(cabecera.getAttribute('aria-expanded')).toBe('true')
    await pulsar(cabecera)
    expect(cabecera.getAttribute('aria-expanded')).toBe('false')
    await buscar('rutas permitidas')
    expect(visibles()).toEqual(['avanzado'])
    expect(cabecera.getAttribute('aria-expanded')).toBe('true')
  })

  it('«Descartar» vuelve a lo guardado: el campo recupera su valor y la barra desaparece', async () => {
    await montar()
    await escribir(campo('Tag'), 'Nuevo')
    await escribir(porPlaceholder('API key de TMDb'), 'k')
    expect(cambios()).toBe('2 campos han cambiado')
    await pulsar(boton('Descartar'))
    expect(campo('Tag').value).toBe('Subidas')
    expect(porPlaceholder('API key de TMDb').value).toBe('')
    expect(cambios()).toBeUndefined()
    expect(updateSettings).not.toHaveBeenCalled()
  })

  it('una URL mala se marca en su campo al salir de él, y se limpia al corregirla', async () => {
    await montar()
    const url = campo('URL del WebUI')
    expect(url.getAttribute('aria-invalid')).toBeNull()
    await escribir(url, 'qbit.local')
    expect(url.getAttribute('aria-invalid')).toBeNull()
    await act(async () => { url.dispatchEvent(new FocusEvent('focusout', { bubbles: true })) })
    expect(url.getAttribute('aria-invalid')).toBe('true')
    const error = document.getElementById(url.getAttribute('aria-describedby')!.split(' ')[0])!
    expect(error.getAttribute('role')).toBe('alert')
    expect(error.textContent).toContain('debe empezar por http://')
    await escribir(url, 'http://qbit:8080')
    expect(url.getAttribute('aria-invalid')).toBeNull()
  })

  it('las etiquetas de los campos están ligadas a su control', async () => {
    await montar()
    for (const texto of ['URL del WebUI', 'URL pública del WebUI', 'Tag', 'Rutas permitidas']) {
      const etiqueta = [...document.querySelectorAll('label')].find(l => l.textContent?.trim().startsWith(texto))!
      expect(document.getElementById(etiqueta.htmlFor)).toBe(campo(texto))
    }
  })
})

describe('Configuración: cuenta y sesiones', () => {
  it('cambiar el usuario pide la contraseña actual', async () => {
    vi.mocked(changeCredentials).mockResolvedValue({ username: 'nuevo', message: 'ok' })
    await montar()
    expect(boton('Guardar cambios').disabled).toBe(true)
    await escribir(campo('Nuevo usuario'), 'nuevo')
    expect(hasUnsavedChanges()).toBe(true)
    await pulsar(boton('Guardar cambios'))
    expect(changeCredentials).not.toHaveBeenCalled()
    expect(texto()).toContain('Introduce tu contraseña actual para confirmar el cambio.')
    await escribir(campo('Contraseña actual'), 'actual')
    await pulsar(boton('Guardar cambios'))
    expect(changeCredentials).toHaveBeenCalledWith({ current_password: 'actual', new_username: 'nuevo', new_password: undefined })
    expect(texto()).toContain('✓ Credenciales actualizadas correctamente.')
    expect(campo('Nuevo usuario').value).toBe('')
  })

  it('«Cerrar las demás» cierra las otras sesiones y recarga la lista', async () => {
    vi.mocked(closeOtherSessions).mockResolvedValue({ closed: 1 })
    await montar()
    expect(texto()).toContain('Esta sesión')
    await pulsar(boton('Cerrar las demás'))
    expect(closeOtherSessions).toHaveBeenCalledTimes(1)
    expect(getSessions).toHaveBeenCalledTimes(2)
    expect(texto()).toContain('✓ Se ha cerrado 1 sesión.')
  })

  it('si no se pueden leer las sesiones ni el usuario, lo dice y deja reintentar en vez de quedarse cargando', async () => {
    vi.mocked(getSessions).mockRejectedValueOnce(new Error('sin red'))
    vi.mocked(getMe).mockRejectedValueOnce(new Error('sin red'))
    await montar()
    expect(texto()).toContain('No se pudo cargar la lista de sesiones.')
    expect(texto()).toContain('No se pudo leer el usuario actual.')
    const reintentar = [...document.body.querySelectorAll('button')].filter(b => b.textContent === 'Reintentar')
    expect(reintentar).toHaveLength(2)
    for (const b of reintentar) await pulsar(b)
    expect(texto()).toContain('Esta sesión')
    expect(campo('Usuario actual').value).toBe('admin')
    expect(texto()).not.toContain('No se pudo')
  })

  it('«Nuevo usuario» no lleva el usuario actual de placeholder: parecía ya relleno', async () => {
    await montar()
    expect(campo('Nuevo usuario').placeholder).toBe('')
  })

  it('sin clave guardada, el campo se llama «API key» sin la nota de mantener la actual', async () => {
    vi.mocked(fetchSettings).mockImplementation(async () => ({ ...structuredClone(AJUSTES), emu_api_key_configured: false, emu_api_key_masked: null }))
    await montar()
    expect(porPlaceholder('API key de eMuwarez').labels?.[0]?.textContent).toBe('API key')
    expect(porPlaceholder('API key de TMDb').labels?.[0]?.textContent).toContain('Nueva API key (dejar vacío para mantener la actual)')
  })
})

describe('Configuración: widget para Homepage', () => {
  it('genera la clave, la enseña entera y no la vuelve a mostrar al recargar', async () => {
    vi.mocked(generateWidgetKey).mockResolvedValue({ clave: 'emuw_clave-de-prueba' })
    await montar()
    expect(document.querySelector('[data-seccion="widget"] .aj-estado--falta')?.textContent).toBe('Sin clave')
    await pulsar(boton('Generar clave'))
    expect(generateWidgetKey).toHaveBeenCalledTimes(1)
    expect((document.querySelector('input[aria-label="Clave del widget"]') as HTMLInputElement).value).toBe('emuw_clave-de-prueba')
    expect(texto()).toContain('no se vuelve a mostrar')
    expect(boton('Regenerar clave')).toBeTruthy()

    // Otra visita a Configuración: solo se sabe que hay clave.
    await act(async () => { raiz.unmount() })
    contenedor.remove()
    vi.mocked(getWidgetKeyStatus).mockResolvedValue({ configurada: true })
    await montar()
    expect(document.querySelector('input[aria-label="Clave del widget"]')).toBeNull()
    expect(texto()).toContain('Clave puesta')
    expect(texto()).not.toContain('emuw_clave-de-prueba')
  })

  it('si no se puede leer el estado de la clave, lo dice y deja reintentar', async () => {
    vi.mocked(getWidgetKeyStatus).mockRejectedValueOnce(new Error('sin red')).mockResolvedValue({ configurada: true })
    await montar()
    expect(texto()).toContain('No se pudo cargar el estado de la clave.')
    expect(texto()).not.toContain('Cargando…')
    await pulsar(boton('Reintentar'))
    expect(texto()).toContain('Clave puesta')
  })

  it('regenerar y quitar piden confirmación en un diálogo de la app, no con window.confirm', async () => {
    vi.mocked(getWidgetKeyStatus).mockResolvedValue({ configurada: true })
    vi.mocked(generateWidgetKey).mockResolvedValue({ clave: 'emuw_otra' })
    vi.mocked(removeWidgetKey).mockResolvedValue({ configurada: false })
    const confirmarNativo = vi.spyOn(window, 'confirm')
    await montar()
    const dialogo = () => document.body.querySelector<HTMLElement>('[role="dialog"]')
    const enDialogo = (t: string) => [...dialogo()!.querySelectorAll('button')].find(x => x.textContent?.trim() === t)!

    // Cancelar no toca la clave; el foco empieza en Cancelar.
    await pulsar(boton('Regenerar clave'))
    expect(dialogo()?.textContent).toContain('Homepage dejará de ver el widget')
    expect(document.activeElement?.textContent).toBe('Cancelar')
    await pulsar(enDialogo('Cancelar'))
    expect(dialogo()).toBeNull()
    await pulsar(boton('Quitar clave'))
    await pulsar(enDialogo('Cancelar'))
    expect(generateWidgetKey).not.toHaveBeenCalled()
    expect(removeWidgetKey).not.toHaveBeenCalled()

    await pulsar(boton('Regenerar clave'))
    await pulsar(enDialogo('Regenerar clave'))
    expect(generateWidgetKey).toHaveBeenCalledTimes(1)
    expect(dialogo()).toBeNull()
    await pulsar(boton('Quitar clave'))
    expect(dialogo()?.textContent).toContain('El widget dejará de responder')
    await pulsar(enDialogo('Quitar clave'))
    expect(removeWidgetKey).toHaveBeenCalledTimes(1)
    expect(document.querySelector('[data-seccion="widget"] .aj-estado--falta')?.textContent).toBe('Sin clave')
    expect(document.querySelector('input[aria-label="Clave del widget"]')).toBeNull()
    expect(confirmarNativo).not.toHaveBeenCalled()
    confirmarNativo.mockRestore()
  })

  it('generar la primera clave no pregunta, y un fallo sale en la propia tarjeta', async () => {
    vi.mocked(generateWidgetKey).mockRejectedValue(new Error('sin red'))
    await montar()
    await pulsar(boton('Generar clave'))
    expect(document.body.querySelector('[role="dialog"]')).toBeNull()
    expect(generateWidgetKey).toHaveBeenCalledTimes(1)
    expect(document.body.querySelector('.widget-aviso')?.textContent).toBe('sin red')
  })
})

describe('Configuración: pestaña de notificaciones', () => {
  it('enseña el webhook enmascarado y guardar no lo envía si no se toca', async () => {
    await montar()
    await pulsar(boton('Notificaciones'))
    expect(texto()).toContain('https://discord****abcd')
    expect(porPlaceholder('https://discord.com/api/webhooks/').value).toBe('')
    expect(texto()).not.toContain('Cambios sin guardar')

    await pulsar(boton('Quitar el webhook'))
    expect(texto()).toContain('Cambios sin guardar')
    await pulsar(boton('Guardar notificaciones'))
    const payload = vi.mocked(updateSettings).mock.calls[0][0]
    expect(payload.clear).toEqual(['notify_discord_webhook_url'])
    expect(payload).not.toHaveProperty('notify_discord_webhook_url')
    expect(payload).toMatchObject({ notify_ui_enabled: true, notify_ui_events: ['upload_done'], notify_discord_enabled: true })
    expect(texto()).toContain('✓ Notificaciones guardadas')
  })

  it('un webhook nuevo viaja recortado y la prueba usa lo escrito', async () => {
    vi.mocked(testDiscordNotification).mockResolvedValue({ ok: true, service: 'discord', status: 'ok', message: 'ok' })
    await montar()
    await pulsar(boton('Notificaciones'))
    await escribir(porPlaceholder('https://discord.com/api/webhooks/'), ' https://hook ')
    await pulsar(boton('Probar notificación'))
    expect(testDiscordNotification).toHaveBeenCalledWith({ webhook_url: 'https://hook' })
    expect(texto()).toContain('Discord: Notificación de prueba enviada')
    await pulsar(boton('Guardar notificaciones'))
    expect(vi.mocked(updateSettings).mock.calls[0][0].notify_discord_webhook_url).toBe('https://hook')
  })

  it('elegir «Una por lote» se guarda y marca el aviso del lote donde se avisaba de las subidas', async () => {
    vi.mocked(fetchSettings).mockImplementation(async () => ({
      ...structuredClone(AJUSTES),
      notify_event_types: [
        { code: 'upload_completed', label: 'Subida completada' },
        { code: 'upload_failed', label: 'Subida fallida' },
        { code: 'upload_batch_done', label: 'Lote de subidas terminado' },
      ],
      notify_ui_events: ['upload_completed', 'upload_failed', 'upload_batch_done'],
      notify_discord_events: ['upload_failed'],
      notify_telegram_events: [],
    }))
    await montar()
    await pulsar(boton('Notificaciones'))
    const selector = document.getElementById('aviso-lote') as HTMLSelectElement
    expect(selector.value).toBe('por_subida')
    expect([...selector.options].map(o => o.textContent)).toEqual(['Una por subida', 'Una por lote'])
    expect(texto()).not.toContain('Cambios sin guardar')

    await escribir(selector, 'por_lote')
    expect(texto()).toContain('Cambios sin guardar')
    expect(texto()).toContain('El aviso del lote sale por los canales que tengan marcado «Lote de subidas terminado».')
    await pulsar(boton('Guardar notificaciones'))
    const payload = vi.mocked(updateSettings).mock.calls[0][0]
    expect(payload.notify_lote_modo).toBe('por_lote')
    // Discord avisaba de las fallidas: ahora también del lote. Telegram no avisaba de ninguna subida: sigue igual.
    expect(payload.notify_discord_events).toEqual(['upload_failed', 'upload_batch_done'])
    expect(payload.notify_telegram_events).toEqual([])
    expect(payload.notify_ui_events).toEqual(['upload_completed', 'upload_failed', 'upload_batch_done'])
    expect(texto()).toContain('✓ Notificaciones guardadas')
    expect(texto()).not.toContain('Cambios sin guardar')
  })

  it('volver a «Una por subida» no toca los eventos', async () => {
    vi.mocked(fetchSettings).mockImplementation(async () => ({ ...structuredClone(AJUSTES), notify_lote_modo: 'por_lote' }))
    await montar()
    await pulsar(boton('Notificaciones'))
    const selector = document.getElementById('aviso-lote') as HTMLSelectElement
    expect(selector.value).toBe('por_lote')
    await escribir(selector, 'por_subida')
    await pulsar(boton('Guardar notificaciones'))
    const payload = vi.mocked(updateSettings).mock.calls[0][0]
    expect(payload.notify_lote_modo).toBe('por_subida')
    expect(payload.notify_ui_events).toEqual(['upload_done'])
    expect(payload.notify_discord_events).toEqual([])
  })

  it('marcar un evento cambia lo que se envía', async () => {
    await montar()
    await pulsar(boton('Notificaciones'))
    const casillas = [...document.body.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')]
    // campana (activar), evento de la campana, discord (activar), evento de discord, telegram (activar), evento de telegram
    await act(async () => { casillas[3].click() })
    await pulsar(boton('Guardar notificaciones'))
    expect(vi.mocked(updateSettings).mock.calls[0][0].notify_discord_events).toEqual(['upload_done'])
  })
})

describe('Configuración: pestaña de diagnóstico', () => {
  async function diagnostico() {
    await montar()
    await pulsar(boton('Diagnóstico'))
  }

  it('enseña la versión y los datos de la base de datos', async () => {
    await diagnostico()
    expect(texto()).toContain('0.14.0')
    expect(texto()).toContain('/config/app.db')
    expect(texto()).toContain('Estás en la última versión publicada')
  })

  it('el aviso permanente de versión se queda en Diagnóstico: no sigue en Backup y vuelve al regresar', async () => {
    vi.mocked(getVersionInfo).mockResolvedValue({ version: '0.14.0', estado: 'hay_novedad', ultima: { version: '0.15.0' } } as Awaited<ReturnType<typeof getVersionInfo>>)
    await diagnostico()
    const aviso = () => document.querySelector('.aj-mensaje')?.textContent ?? ''
    expect(aviso()).toContain('Hay una versión más nueva: v0.15.0')
    await pulsar(boton('Backup'))
    expect(aviso()).not.toContain('Hay una versión más nueva')
    await pulsar(boton('Diagnóstico'))
    expect(aviso()).toContain('Hay una versión más nueva')
  })

  it('VACUUM real exige escribir MANTENIMIENTO_DB; la previsualización no', async () => {
    vi.mocked(runVacuum).mockResolvedValue({ ok: true, message: 'Hecho' })
    await diagnostico()
    await pulsar(boton('Ejecutar VACUUM'))
    expect(runVacuum).not.toHaveBeenCalled()
    expect(texto()).toContain('Escribe MANTENIMIENTO_DB para confirmar')

    await pulsar(boton('Previsualizar VACUUM'))
    expect(runVacuum).toHaveBeenLastCalledWith({ dry_run: true, apply: false, confirmation: undefined })

    const confirmacion = document.body.querySelector<HTMLInputElement>('input[aria-label="Confirmación de VACUUM"]')!
    await escribir(confirmacion, 'MANTENIMIENTO_DB')
    await pulsar(boton('Ejecutar VACUUM'))
    expect(runVacuum).toHaveBeenLastCalledWith({ dry_run: false, apply: true, confirmation: 'MANTENIMIENTO_DB' })
    expect(texto()).toContain('✓ Hecho')
    // al terminar recarga el estado de mantenimiento
    expect(getMaintenanceStatus).toHaveBeenCalledTimes(2)
  })

  it('el mapeo de rutas se guarda por su cuenta, sin el botón global', async () => {
    await diagnostico()
    expect(boton('Guardar cambios').disabled).toBe(true)
    await pulsar(boton('+ Añadir regla'))
    expect(hasUnsavedChanges()).toBe(true)
    await escribir(porPlaceholder('Ruta de Radarr/Sonarr'), ' /data/media ')
    await escribir(porPlaceholder('Ruta local'), '/mnt/media')
    await pulsar(boton('Guardar cambios'))
    expect(updateSettings).toHaveBeenCalledWith({ path_mappings: [{ from: '/data/media', to: '/mnt/media' }] })
    expect(texto()).toContain('✓ Mapeo de rutas guardado')
    expect(hasUnsavedChanges()).toBe(false)
  })
})

describe('Configuración: pestaña de backup', () => {
  async function backup() {
    await montar()
    await pulsar(boton('Backup'))
  }

  it('lista los backups existentes', async () => {
    await backup()
    expect(texto()).toContain('Backups existentes (1)')
    expect(texto()).toContain('copia-1.tar.gz')
    // Tamaño y fecha con los formatos de toda la app; la tabla va en una caja que se desplaza en el móvil.
    expect(texto()).toContain('2,0 KB')
    expect(texto()).toContain(formatDate(COPIA.created_at))
    expect(document.querySelector('.aj-desborde-x > table')).not.toBeNull()
  })

  it('restaurar exige elegir backup y escribir RESTAURAR_CONFIG; previsualizar solo lo primero', async () => {
    vi.mocked(restoreBackup).mockResolvedValue({ ok: true, message: 'Restaurado' })
    await backup()
    await pulsar(boton('Restaurar'))
    expect(restoreBackup).not.toHaveBeenCalled()
    expect(texto()).toContain('Elige un backup')

    const selector = document.body.querySelector('select')!
    await escribir(selector, 'copia-1.tar.gz')
    await pulsar(boton('Restaurar'))
    expect(restoreBackup).not.toHaveBeenCalled()
    expect(texto()).toContain('Escribe RESTAURAR_CONFIG para confirmar')

    await pulsar(boton('Previsualizar'))
    expect(restoreBackup).toHaveBeenLastCalledWith('copia-1.tar.gz', { dry_run: true, apply: false, confirmation: undefined })

    await escribir(porPlaceholder('Confirmación: RESTAURAR_CONFIG'), 'RESTAURAR_CONFIG')
    await pulsar(boton('Restaurar'))
    expect(restoreBackup).toHaveBeenLastCalledWith('copia-1.tar.gz', { dry_run: false, apply: true, confirmation: 'RESTAURAR_CONFIG' })
    expect(texto()).toContain('✓ Restaurado')
  })
})

describe('Configuración: no guardar sin haber cargado ni pisar lo editado durante el guardado', () => {
  it('si falla la carga no se puede guardar los valores por defecto encima de los ajustes reales', async () => {
    vi.mocked(fetchSettings).mockRejectedValueOnce(new Error('sin conexión'))
    await montar()
    expect(texto()).toContain('sin conexión')
    expect(() => boton('Guardar')).toThrow()
    expect(updateSettings).not.toHaveBeenCalled()

    // «Reintentar» vuelve a cargar y, ya con los ajustes reales, se puede guardar
    await pulsar(boton('Reintentar'))
    expect(fetchSettings).toHaveBeenCalledTimes(2)
    expect(campo('Tag').value).toBe('Subidas')
    await escribir(campo('Tag'), 'Nuevo')
    await pulsar(boton('Guardar'))
    expect(vi.mocked(updateSettings).mock.calls[0][0]).toMatchObject({ upload_tags: ['GRUPO', 'OTRO'], qbit_tag: 'Nuevo' })
  })

  it('si una carga buena va seguida de una que falla, tampoco se puede guardar lo de la primera', async () => {
    // StrictMode ejecuta la carga dos veces: la primera sale bien y la segunda falla.
    vi.mocked(fetchSettings).mockResolvedValueOnce(structuredClone(AJUSTES))
    vi.mocked(fetchSettings).mockRejectedValueOnce(new Error('sin conexión'))
    await montar(true)
    expect(texto()).toContain('sin conexión')
    expect(() => boton('Guardar')).toThrow()
    expect(updateSettings).not.toHaveBeenCalled()
  })

  it('un error sin mensaje cuenta igual como fallo de carga', async () => {
    vi.mocked(fetchSettings).mockRejectedValueOnce(new Error(''))
    await montar()
    expect(texto()).toContain('No se pudo cargar la configuración')
    expect(() => boton('Guardar')).toThrow()
  })

  describe('mapeo de rutas', () => {
    const REGLA = { from: '/data/media', to: '/mnt/media' }

    async function diagnostico() {
      // La pestaña Configuración carga bien; la tarjeta de rutas, la segunda lectura, falla.
      vi.mocked(fetchSettings).mockResolvedValueOnce(structuredClone(AJUSTES))
      vi.mocked(fetchSettings).mockRejectedValueOnce(new Error('sin conexión'))
      await montar()
      await pulsar(boton('Diagnóstico'))
    }

    it('si falla la carga no enseña «No hay reglas», bloquea el editor y reintenta', async () => {
      await diagnostico()
      expect(texto()).toContain('sin conexión')
      expect(texto()).not.toContain('No hay reglas')
      expect(() => boton('+ Añadir regla')).toThrow()
      expect(() => boton('Guardar cambios')).toThrow()

      vi.mocked(fetchSettings).mockResolvedValueOnce({ ...structuredClone(AJUSTES), path_mappings: [REGLA] })
      await pulsar(boton('Reintentar'))
      expect(porPlaceholder('Ruta de Radarr/Sonarr').value).toBe('/data/media')
      await pulsar(boton('+ Añadir regla'))
      const [, desde] = document.body.querySelectorAll<HTMLInputElement>('input[placeholder^="Ruta de Radarr/Sonarr"]')
      const [, hasta] = document.body.querySelectorAll<HTMLInputElement>('input[placeholder^="Ruta local"]')
      await escribir(desde, '/data/series')
      await escribir(hasta, '/mnt/series')
      await pulsar(boton('Guardar cambios'))
      // la regla que ya existía viaja con la nueva: no se sustituye por una lista incompleta
      expect(updateSettings).toHaveBeenCalledWith({ path_mappings: [REGLA, { from: '/data/series', to: '/mnt/series' }] })
    })

    it('un error sin mensaje tampoco deja el editor vacío', async () => {
      vi.mocked(fetchSettings).mockResolvedValueOnce(structuredClone(AJUSTES))
      vi.mocked(fetchSettings).mockRejectedValueOnce(new Error(''))
      await montar()
      await pulsar(boton('Diagnóstico'))
      expect(texto()).toContain('No se pudieron cargar las reglas')
      expect(() => boton('+ Añadir regla')).toThrow()
    })

    it('mientras se guarda no se puede editar, así la respuesta no borra lo escrito entretanto', async () => {
      vi.mocked(fetchSettings).mockResolvedValueOnce(structuredClone(AJUSTES))
      vi.mocked(fetchSettings).mockResolvedValueOnce({ ...structuredClone(AJUSTES), path_mappings: [REGLA] })
      let terminar!: (s: SettingsData) => void
      vi.mocked(updateSettings).mockReturnValueOnce(new Promise<SettingsData>(r => { terminar = r }))
      await montar()
      await pulsar(boton('Diagnóstico'))
      await escribir(porPlaceholder('Ruta de Radarr/Sonarr'), '/data/otra')
      await pulsar(boton('Guardar cambios'))
      expect(boton('Guardando…').disabled).toBe(true)
      expect(porPlaceholder('Ruta de Radarr/Sonarr').disabled).toBe(true)
      expect(porPlaceholder('Ruta local').disabled).toBe(true)
      expect(boton('+ Añadir regla').disabled).toBe(true)
      expect(document.querySelector<HTMLButtonElement>('button[aria-label="Quitar regla"]')!.disabled).toBe(true)

      await act(async () => { terminar({ ...structuredClone(AJUSTES), path_mappings: [{ from: '/data/otra', to: '/mnt/media' }] }) })
      await esperar()
      expect(porPlaceholder('Ruta de Radarr/Sonarr').disabled).toBe(false)
      expect(porPlaceholder('Ruta de Radarr/Sonarr').value).toBe('/data/otra')
    })
  })
})
