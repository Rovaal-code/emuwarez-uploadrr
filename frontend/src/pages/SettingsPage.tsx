import { useState, useEffect, useCallback, useRef, createContext, useContext } from 'react'
import { setUnsavedGuard, guardedLeave } from '../utils/unsavedGuard'
import {
  getMaintenanceStatus,
  createBackup,
  listBackups,
  restoreBackup,
  runIntegrityCheck,
  runVacuum,
  type MaintenanceStatus,
  type BackupInfo,
  getVersionInfo,
  type VersionInfo,
} from '../api/maintenance'
import { fetchSettings, updateSettings, type SettingsData } from '../api/settings'
import { testTmdbConnection, testEmuwarezConnection, testQbitConnection, testImghostConnection, type IntegrationTestResult } from '../api/integrationTests'
import { useCooldown } from '../hooks/useCooldown'
import { usePerfilEmu } from '../context/PerfilEmuContext'
import { testDiscordNotification, testTelegramNotification } from '../api/notifications'
import { ProviderPriorityPicker } from '../components/ProviderPriorityPicker'
import { ServiceIcon } from '../components/ServiceIcon'
import { InfoIcon } from '../components/InfoIcon'
import { Favicon, domainOf } from '../components/Favicon'
import { SortableList, DragHandleIcon, type DragHandleProps } from '../components/SortableList'
import { REGION_OPTIONS } from '../constants/regionLanguage'
import { CheckStatusIcon } from '../components/DetailCard'
import { testResultLabel, testResultColor, emuTestCooldownSeconds } from '../utils/integrationResult'
import { getMe, changeCredentials, getSessions, closeOtherSessions, type SesionAbierta } from '../api/auth'
import { useTooltip, HoverTitle } from '../components/Tooltip'
import { TAMANOS, TAMANO_POR_DEFECTO, tamanoUi, guardarTamano } from '../utils/uiScale'
import { isValidHttpUrl } from '../utils/validation'
import { getUploadConcurrencyEstimate, type UploadConcurrencyEstimate } from '../api/system'
import { MODOS_PISTAS, MODO_PISTAS_POR_DEFECTO, normalizarModo, type ModoPistas } from '../utils/modoPistas'
import { formatNumero, timeAgo, formatDate } from '../utils/format'
import { descripcionDeSesion } from '../utils/sesiones'
import { useAlEntrar } from '../context/SeccionVisible'
import { Modal } from '../components/Modal'
import { IconoUsuario } from '../components/Iconos'

type Tab = 'config' | 'notifications' | 'diagnostics' | 'backup'

// A tab exposes its save action so the page-header (top-right) can render the
// button, like the sync buttons in Biblioteca/Peticiones.
export interface SaveExpose {
  dirty: boolean
  saving: boolean
  onSave: () => void
  label: string
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${formatNumero(n / 1024, 1)} KB`
  return `${formatNumero(n / 1024 / 1024, 2)} MB`
}

// Serialize the Config form's values so we can compare current vs. loaded and
// know whether there are unsaved changes. Array order is fixed on purpose.
function configSignature(v: {
  tags: string[]; providerOrder: string[]; region: string
  emuUsername: string; ignoreSpecials: boolean; sourceEngine: boolean; addLogo: boolean; capturasPorCapitulo: boolean; modoDePistas: ModoPistas
  recentLimit: number; uploadMaxConcurrent: number; qbitUrl: string; qbitTag: string; qbitUser: string
  imgEnabled: string[]; allowedRoots: string
  newKey?: string; newEmuKey?: string; qbitPass?: string; qbitQui?: string; quitarQui?: boolean; quitarQbitPass?: boolean
}): string {
  return JSON.stringify([
    v.tags, v.providerOrder, v.region, v.emuUsername,
    v.ignoreSpecials, v.sourceEngine, v.addLogo, v.capturasPorCapitulo, v.modoDePistas, v.recentLimit, v.uploadMaxConcurrent, v.qbitUrl, v.qbitTag, v.qbitUser, v.imgEnabled, v.allowedRoots,
    v.newKey ?? '', v.newEmuKey ?? '', v.qbitPass ?? '', v.qbitQui ?? '', v.quitarQui ?? false, v.quitarQbitPass ?? false,
  ])
}

function RemoveImgHostButton({ onClick }: { onClick: () => void }) {
  const { triggerProps, tooltipNode } = useTooltip('Quitar')
  return (
    <button className="btn btn-ghost btn-sm" style={{ fontSize: 13, padding: '2px 6px', color: 'var(--text-muted)' }}
      onClick={onClick} type="button" {...triggerProps}>✕{tooltipNode}</button>
  )
}

function RemoveMappingRuleButton({ onClick }: { onClick: () => void }) {
  const { triggerProps, tooltipNode } = useTooltip('Quitar regla')
  return (
    <button className="btn btn-ghost btn-sm" type="button" onClick={onClick} {...triggerProps}>✕{tooltipNode}</button>
  )
}

// ---------- Config tab ----------
type TonoMensaje = 'ok' | 'error' | 'aviso'

type SettingsMsg = {
  text: string
  tono: TonoMensaje
  // Un mensaje permanente describe un ESTADO que sigue siendo cierto (hay una
  // versión nueva), no algo que acaba de pasar. No se borra solo; si mientras
  // tanto ocurre algo (guardas, creas un backup), ese aviso pasa por delante
  // unos segundos y luego vuelve el permanente.
  permanente?: boolean
} | null

// Todos los avisos de esta página (guardado, backups, mantenimiento, errores)
// salen en la misma fila que las pestañas, a la derecha. Antes cada pestaña
// pintaba su propio bloque arriba del todo, que empujaba las tarjetas hacia
// abajo al aparecer y las devolvía a su sitio al irse: el contenido daba un
// salto justo cuando acabas de pulsar un botón. Desde la fila de pestañas no
// mueve nada.
interface OpcionesMensaje {
  tono?: TonoMensaje
  permanente?: boolean
  // Borra el permanente que hubiera. Lo usa la comprobación de versión cuando
  // pasa a "al día": sin esto, el aviso de versión nueva de la comprobación
  // anterior seguía debajo y reaparecía al caducar el pasajero, diciendo que
  // hay novedad cuando ya no la hay.
  borrarPermanente?: boolean
}

const SettingsMessageContext = createContext<
  (ok: boolean, text: string, opciones?: OpcionesMensaje) => void
>(() => {})

export function useSettingsMessage() {
  return useContext(SettingsMessageContext)
}

// Misma firma que el useState que sustituye (`setMsg({ ok, text })` y
// `setMsg(null)`), para no tocar los sitios que ya avisaban: lo único que
// cambia es dónde sale el aviso.
function useSettingsMessageAdapter() {
  const show = useSettingsMessage()
  return useCallback(
    (m: { ok: boolean; text: string } | null) => { if (m) show(m.ok, m.text) },
    [show],
  )
}

// El aviso ocupa el hueco que sobra a la derecha de las pestañas y se recorta
// con puntos suspensivos: un error de backup puede ser una frase larga y no
// puede desmontar la fila. El texto completo sale al pasar el ratón.
function SettingsMessageSlot({ msg }: { msg: SettingsMsg }) {
  const ref = useRef<HTMLSpanElement>(null)
  const [recortado, setRecortado] = useState(false)
  // El tooltip solo tiene sentido si falta texto por ver: repetir un aviso que
  // ya se lee entero solo estorba.
  useEffect(() => {
    const el = ref.current
    setRecortado(!!el && el.scrollWidth > el.clientWidth)
  }, [msg?.text])
  const { triggerProps, tooltipNode } = useTooltip(recortado ? msg?.text ?? null : null)
  if (!msg) return null
  const colores: Record<TonoMensaje, { texto: string; fondo: string; borde: string }> = {
    ok: { texto: 'var(--color-available)', fondo: 'color-mix(in srgb, var(--color-available) 10%, transparent)', borde: 'color-mix(in srgb, var(--color-available) 30%, transparent)' },
    error: { texto: 'var(--color-error)', fondo: 'color-mix(in srgb, var(--color-error) 10%, transparent)', borde: 'color-mix(in srgb, var(--color-error) 30%, transparent)' },
    aviso: { texto: 'var(--color-warning)', fondo: 'color-mix(in srgb, var(--color-warning) 10%, transparent)', borde: 'color-mix(in srgb, var(--color-warning) 30%, transparent)' },
  }
  const c = colores[msg.tono]
  return (
    <span
      ref={ref}
      style={{
        marginLeft: 'auto', alignSelf: 'center', minWidth: 0,
        padding: '4px 10px', marginBottom: 6, borderRadius: 6,
        background: c.fondo, border: `1px solid ${c.borde}`, color: c.texto,
        fontSize: 12.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
      }}
      {...triggerProps}
    >
      {msg.text}
      {tooltipNode}
    </span>
  )
}

function ConfigTab({ onExposeSave }: { onExposeSave: (a: SaveExpose | null) => void }) {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const setMsg = useSettingsMessageAdapter()
  const [testingTmdb, setTestingTmdb] = useState(false)
  const [tmdbTestResult, setTmdbTestResult] = useState<IntegrationTestResult | null>(null)
  const [testingEmu, setTestingEmu] = useState(false)
  const [emuTestResult, setEmuTestResult] = useState<IntegrationTestResult | null>(null)
  const emuCooldown = useCooldown()
  const { actualizar: actualizarPerfilEmu } = usePerfilEmu()

  // Form state
  // Grupos de subida: el primero es el que sale por defecto al subir.
  const [tags, setTags] = useState<string[]>([])
  const [nuevoTag, setNuevoTag] = useState('')
  const [providerOrder, setProviderOrder] = useState<string[]>([])
  const [region, setRegion] = useState('')
  const [newKey, setNewKey] = useState('')
  const [newEmuKey, setNewEmuKey] = useState('')
  const [emuUsername, setEmuUsername] = useState('')
  const [ignoreSpecials, setIgnoreSpecials] = useState(true)
  // Tamaño de interfaz. Arranca de lo que ya está aplicado (utils/uiScale lo
  // puso al cargar la página desde localStorage), no de un valor por defecto:
  // si no, el desplegable diría 100% mientras la interfaz está al 130%.
  const [tamanoInterfaz, setTamanoInterfaz] = useState(tamanoUi)
  // Internal Source Tool: apagada por defecto, sigue en desarrollo.
  const [sourceEngine, setSourceEngine] = useState(false)
  // El logo del contenido en la descripción: se sube por defecto.
  const [addLogo, setAddLogo] = useState(true)
  // Capturas de un pack: solo del primer capítulo por defecto.
  const [capturasPorCapitulo, setCapturasPorCapitulo] = useState(false)
  // Reordenar pistas: apagado por defecto, reescribe el contenedor entero.
  const [modoDePistas, setModoDePistas] = useState<ModoPistas>(MODO_PISTAS_POR_DEFECTO)
  const [recentLimit, setRecentLimit] = useState(100)
  const [uploadMaxConcurrent, setUploadMaxConcurrent] = useState(1)
  const [testingConcurrency, setTestingConcurrency] = useState(false)
  const [concurrencyEstimate, setConcurrencyEstimate] = useState<UploadConcurrencyEstimate | null>(null)
  const [qbitUrl, setQbitUrl] = useState('')
  const [qbitTag, setQbitTag] = useState('')
  const [qbitUser, setQbitUser] = useState('')
  const [qbitPass, setQbitPass] = useState('')
  const [quitarQbitPass, setQuitarQbitPass] = useState(false)
  // El proxy de qui es un secreto como la contraseña: no se carga, y quitarlo se pide aparte.
  const [qbitQui, setQbitQui] = useState('')
  const [quitarQui, setQuitarQui] = useState(false)
  const [testingQbit, setTestingQbit] = useState(false)
  const [qbitTestResult, setQbitTestResult] = useState<IntegrationTestResult | null>(null)
  const [showQbitUser, setShowQbitUser] = useState(false)
  const qbitUserEyeTip = useTooltip(showQbitUser ? 'Ocultar usuario' : 'Mostrar usuario')
  // Image hosts
  const [imgEnabled, setImgEnabled] = useState<string[]>([])
  // La API key de un proveedor se mete en su propia tarjeta, no en un campo
  // colgando debajo de la fila: son cinco proveedores y el formulario se
  // llenaba de campos de contraseña abiertos.
  const [keyModalHost, setKeyModalHost] = useState<string | null>(null)
  const [keyDraft, setKeyDraft] = useState('')
  const [keySaving, setKeySaving] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)
  const [imgTest, setImgTest] = useState<Record<string, IntegrationTestResult>>({})
  const [imgTesting, setImgTesting] = useState<string | null>(null)
  const [showAddImg, setShowAddImg] = useState(false)
  // Uploadrr sandboxing: folder(s) where THIS container reaches the media,
  // comma-separated. Empty means real uploads fail closed until it's set.
  const [allowedRoots, setAllowedRoots] = useState('')

  // Unsaved-changes tracking: compare current form values to the loaded ones.
  const [baseline, setBaseline] = useState('')
  // Un grupo escrito sin pulsar «Añadir» también se guarda.
  const borrador = nuevoTag.trim()
  const tagsAGuardar = borrador && !tags.includes(borrador) ? [...tags, borrador] : tags
  const currentSig = configSignature({
    tags: tagsAGuardar, providerOrder, region, emuUsername,
    ignoreSpecials, sourceEngine, addLogo, capturasPorCapitulo, modoDePistas, recentLimit, uploadMaxConcurrent, qbitUrl, qbitTag, qbitUser, imgEnabled, allowedRoots,
    newKey, newEmuKey, qbitPass, qbitQui, quitarQui, quitarQbitPass,
  })
  const dirty = baseline !== '' && currentSig !== baseline
  const dirtyRef = useRef(false)
  dirtyRef.current = dirty
  useEffect(() => {
    setUnsavedGuard(() => dirtyRef.current)
    return () => setUnsavedGuard(null)
  }, [])

  // Expose the save action to the page-header (top-right button). onSave goes
  // through a ref so it always runs with the latest form values.
  const saveRef = useRef<() => void>(() => {})
  saveRef.current = () => { void handleSave() }
  const stableSave = useRef(() => saveRef.current()).current
  useEffect(() => {
    onExposeSave({ dirty, saving, onSave: stableSave, label: 'Guardar configuración' })
  }, [dirty, saving, onExposeSave, stableSave])
  useEffect(() => () => onExposeSave(null), [onExposeSave])

  async function handleTestImghost(hostId: string) {
    setImgTesting(hostId)
    try {
      // Con la tarjeta abierta se prueba lo que hay escrito AHORA; desde el
      // botón Probar de la fila, lo que ya esté guardado (undefined deja que
      // el backend lea el ajuste). Probar antes de guardar es justo para lo
      // que existe la tarjeta.
      const pending = keyModalHost === hostId ? keyDraft.trim() : ''
      const r = await testImghostConnection(hostId, pending || undefined)
      setImgTest(p => ({ ...p, [hostId]: r }))
    } catch {
      setImgTest(p => ({ ...p, [hostId]: { ok: false, service: 'imghost', status: 'connection_error', message: 'Error al contactar con el servidor' } }))
    } finally { setImgTesting(null) }
  }

  function toggleImgHost(hostId: string) {
    // Newly-enabled host goes FIRST in priority — same reasoning as
    // ProviderPriorityPicker.enable(): it's presumably being added because
    // it should now be preferred, not appended where fallback_order() would
    // rarely if ever actually pick it.
    setImgEnabled(p => p.includes(hostId) ? p.filter(x => x !== hostId) : [hostId, ...p])
  }

  useEffect(() => {
    fetchSettings()
      .then(s => {
        setSettings(s)
        setTags(s.upload_tags?.length ? s.upload_tags : [s.default_release_tag])
        setProviderOrder(s.provider_priority_order)
        setRegion(s.tmdb_watch_region)
        setEmuUsername(s.emu_username ?? '')
        setIgnoreSpecials(s.series_ignore_specials ?? true)
        setSourceEngine(s.source_engine_enabled ?? false)
        setAddLogo(s.emu_add_logo ?? true)
        setCapturasPorCapitulo(s.emu_per_episode_screens ?? false)
        setModoDePistas(normalizarModo(s.remux_track_mode))
        setRecentLimit(s.recent_activity_limit ?? 100)
        setUploadMaxConcurrent(s.upload_max_concurrent ?? 1)
        setQbitUrl(s.qbit_url ?? '')
        setQbitTag(s.qbit_tag ?? '')
        setQbitUser(s.qbit_username ?? '')
        setImgEnabled(s.image_hosts_enabled ?? [])
        setAllowedRoots((s.uploadrr_allowed_roots ?? []).join(', '))
        setBaseline(configSignature({
          tags: s.upload_tags?.length ? s.upload_tags : [s.default_release_tag], providerOrder: s.provider_priority_order,
          region: s.tmdb_watch_region,
          emuUsername: s.emu_username ?? '',
          ignoreSpecials: s.series_ignore_specials ?? true, sourceEngine: s.source_engine_enabled ?? false, addLogo: s.emu_add_logo ?? true, capturasPorCapitulo: s.emu_per_episode_screens ?? false, modoDePistas: normalizarModo(s.remux_track_mode),
          recentLimit: s.recent_activity_limit ?? 100,
          uploadMaxConcurrent: s.upload_max_concurrent ?? 1,
          qbitUrl: s.qbit_url ?? '', qbitTag: s.qbit_tag ?? '', qbitUser: s.qbit_username ?? '',
          imgEnabled: s.image_hosts_enabled ?? [],
          allowedRoots: (s.uploadrr_allowed_roots ?? []).join(', '),
        }))
      })
      .catch(() => setMsg({ ok: false, text: 'Error cargando configuración' }))
      .finally(() => setLoading(false))
  }, [])

  async function handleTestConcurrency() {
    setTestingConcurrency(true)
    setConcurrencyEstimate(null)
    try {
      const r = await getUploadConcurrencyEstimate()
      setConcurrencyEstimate(r)
    } catch {
      // Silently give up — the button itself just goes back to idle, same
      // as any other "Probar…" button here when the request fails.
    } finally {
      setTestingConcurrency(false)
    }
  }

  async function handleTestTmdb() {
    setTestingTmdb(true)
    setTmdbTestResult(null)
    try {
      const params: { api_key?: string; region?: string } = {}
      if (newKey.trim()) params.api_key = newKey.trim()
      if (region.trim()) params.region = region.trim()
      const r = await testTmdbConnection(params)
      setTmdbTestResult(r)
    } catch {
      setTmdbTestResult({ ok: false, service: 'tmdb', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setTestingTmdb(false)
    }
  }

  async function handleTestEmu() {
    if (emuCooldown.active) return
    setTestingEmu(true)
    setEmuTestResult(null)
    try {
      const params: { api_key?: string } = {}
      if (newEmuKey.trim()) params.api_key = newEmuKey.trim()
      const r = await testEmuwarezConnection(params)
      setEmuTestResult(r)
      emuCooldown.start(emuTestCooldownSeconds(r))
    } catch {
      setEmuTestResult({ ok: false, service: 'emuwarez', status: 'connection_error', message: 'Error al contactar con el servidor' })
      emuCooldown.start(60)
    } finally {
      setTestingEmu(false)
    }
  }

  async function handleTestQbit() {
    setTestingQbit(true)
    setQbitTestResult(null)
    try {
      const r = await testQbitConnection({
        url: qbitUrl.trim() || undefined,
        username: qbitUser.trim() || undefined,
        password: qbitPass.trim() || undefined,
        qui_proxy_url: quitarQui ? '' : (qbitQui.trim() || undefined),
      })
      setQbitTestResult(r)
    } catch {
      setQbitTestResult({ ok: false, service: 'qbittorrent', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setTestingQbit(false)
    }
  }

  function anadirTag() {
    const t = nuevoTag.trim()
    if (t && !tags.includes(t)) setTags([...tags, t])
    setNuevoTag('')
  }

  async function handleSave() {
    if (qbitUrl.trim() && !isValidHttpUrl(qbitUrl)) {
      setMsg({ ok: false, text: 'La URL de qBittorrent debe empezar por http:// o https:// e incluir un host válido' })
      return
    }
    if (qbitQui.trim() && !isValidHttpUrl(qbitQui)) {
      setMsg({ ok: false, text: 'La URL del proxy de qui debe empezar por http:// o https:// e incluir un host válido' })
      return
    }
    setSaving(true)
    setMsg(null)
    try {
      const enviado = borrador
      const payload: Parameters<typeof updateSettings>[0] = {
        default_release_tag: tags[0],
        upload_tags: tagsAGuardar,
        provider_priority_order: providerOrder,
        tmdb_watch_region: region.trim(),
        // No longer a user-facing toggle — always on.
        tmdb_localize_series_titles: true,
        emu_username: emuUsername.trim(),
        series_ignore_specials: ignoreSpecials,
        source_engine_enabled: sourceEngine,
        emu_add_logo: addLogo,
        emu_per_episode_screens: capturasPorCapitulo,
        remux_track_mode: modoDePistas,
        recent_activity_limit: recentLimit,
        upload_max_concurrent: uploadMaxConcurrent,
        qbit_url: qbitUrl.trim(),
        qbit_tag: qbitTag.trim(),
        qbit_username: qbitUser.trim(),
        image_hosts_enabled: imgEnabled,
        uploadrr_allowed_roots: allowedRoots,
      }
      if (newKey.trim()) payload.tmdb_api_key = newKey.trim()
      if (newEmuKey.trim()) payload.emu_api_key = newEmuKey.trim()
      if (qbitPass.trim()) payload.qbit_password = qbitPass.trim()
      else if (quitarQbitPass) payload.clear = ['qbit_password']
      if (quitarQui) payload.qbit_qui_proxy_clear = true
      else if (qbitQui.trim()) payload.qbit_qui_proxy_url = qbitQui.trim()
      // Las API keys de imágenes ya NO viajan aquí: cada una se guarda desde
      // su propia tarjeta, en el momento, sin depender del Guardar global.
      const updated = await updateSettings(payload)
      // Con otra clave, el servidor descarta el perfil guardado y lo pide ya: el Panel no espera a la hora.
      if (payload.emu_api_key) actualizarPerfilEmu().catch(() => { /* lo intenta la próxima lectura */ })
      setSettings(updated)
      setTags(updated.upload_tags?.length ? updated.upload_tags : [updated.default_release_tag])
      // Solo el borrador que se envió: lo escrito mientras guardaba se queda.
      setNuevoTag(n => (n.trim() === enviado ? '' : n))
      setProviderOrder(updated.provider_priority_order)
      setRegion(updated.tmdb_watch_region)
      setEmuUsername(updated.emu_username ?? '')
      setIgnoreSpecials(updated.series_ignore_specials ?? true)
      setRecentLimit(updated.recent_activity_limit ?? 100)
      setUploadMaxConcurrent(updated.upload_max_concurrent ?? 1)
      setQbitUrl(updated.qbit_url ?? '')
      setQbitTag(updated.qbit_tag ?? '')
      setQbitUser(updated.qbit_username ?? '')
      setQbitPass('')
      setQuitarQbitPass(false)
      setQbitQui('')
      setQuitarQui(false)
      setImgEnabled(updated.image_hosts_enabled ?? [])
      setNewKey('')
      setNewEmuKey('')
      setAllowedRoots((updated.uploadrr_allowed_roots ?? []).join(', '))
      setBaseline(configSignature({
        tags: updated.upload_tags?.length ? updated.upload_tags : [updated.default_release_tag], providerOrder: updated.provider_priority_order,
        region: updated.tmdb_watch_region,
        emuUsername: updated.emu_username ?? '',
        ignoreSpecials: updated.series_ignore_specials ?? true, sourceEngine: updated.source_engine_enabled ?? false, addLogo: updated.emu_add_logo ?? true, capturasPorCapitulo: updated.emu_per_episode_screens ?? false, modoDePistas: normalizarModo(updated.remux_track_mode),
        recentLimit: updated.recent_activity_limit ?? 100,
        uploadMaxConcurrent: updated.upload_max_concurrent ?? 1,
        qbitUrl: updated.qbit_url ?? '', qbitTag: updated.qbit_tag ?? '', qbitUser: updated.qbit_username ?? '',
        imgEnabled: updated.image_hosts_enabled ?? [],
        allowedRoots: (updated.uploadrr_allowed_roots ?? []).join(', '),
      }))
      setMsg({ ok: true, text: '✓ Configuración guardada' })
    } catch (e: unknown) {
      setMsg({ ok: false, text: `✗ ${e instanceof Error ? e.message : String(e)}` })
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p style={{ padding: 20, color: 'var(--text-muted)', fontSize: 13 }}>Cargando…</p>

  return (
    <div data-tour="settings-content" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Ocho tarjetas en cuatro columnas de ancho: cada una con el alto que
          le pida su contenido (ver settings-config-grid en dashboard.css). La
          página entera se desplaza si no caben todas, no cada tarjeta por
          separado. */}
      <div className="settings-config-grid">
      <AccountCard />
      <SessionsCard />

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="emu" size={18} /> eMuwarez
        </h3>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Estado de la API key</label>
          <div style={{ fontSize: 13 }}>
            {settings?.emu_api_key_configured
              ? <><span style={{ color: 'var(--color-available)', display: 'inline-flex', alignItems: 'center', gap: 5 }}><CheckStatusIcon status="ok" /> Configurada</span>{settings.emu_api_key_masked && <code style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)' }}>{settings.emu_api_key_masked}</code>}</>
              : <span style={{ color: 'var(--color-error)' }}>✗ No configurada</span>}
          </div>
        </div>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Nueva API key <span className="form-hint">(dejar vacío para mantener la actual)</span></label>
          <input
            type="password"
            className="form-input"
            value={newEmuKey}
            onChange={e => setNewEmuKey(e.target.value)}
            placeholder="API key de eMuwarez"
            autoComplete="new-password"
          />
          <span className="form-hint">Usada para leer el catálogo y las peticiones de eMuwarez.</span>
        </div>
        <div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleTestEmu}
            disabled={testingEmu || emuCooldown.active}
            type="button"
          >
            {testingEmu ? 'Probando…' : emuCooldown.active ? `Espera ${emuCooldown.remaining}s` : 'Probar conexión'}
          </button>
          {emuTestResult && (
            <span style={{ marginLeft: 10, fontSize: 12, color: testResultColor(emuTestResult) }}>
              {testResultLabel(emuTestResult)}
            </span>
          )}
        </div>
        <div className="form-group" style={{ marginTop: 14 }}>
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Mi usuario de eMuwarez
            <InfoIcon text="Tu nombre de usuario en eMuwarez. Se usa para reconocer cuáles de todas las peticiones descargadas las has creado tú, y así poder mostrártelas en 'Mis peticiones'." />
          </label>
          <input
            className="form-input"
            value={emuUsername}
            onChange={e => setEmuUsername(e.target.value)}
            placeholder="Tu nombre de usuario en eMuwarez"
          />
        </div>
        <div className="form-group" style={{ marginTop: 14 }}>
          <label className="form-label" htmlFor="nuevo-grupo-de-subida" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Grupos de subida
            <InfoIcon text="El tag que va tras el último «-» en el nombre del torrent (tu grupo/usuario). El primero es el que sale por defecto al subir; los demás se eligen en el asistente." />
          </label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 8 }}>
            {tags.map((t, i) => (
              <div key={t} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 13, fontWeight: 500 }}>{t}</span>
                {i === 0
                  ? <span className="badge status-available">por defecto</span>
                  : <button type="button" className="btn-icon" title="Usar por defecto" aria-label={`Usar ${t} por defecto`}
                      onClick={() => setTags([t, ...tags.filter(x => x !== t)])}>☆</button>}
                {tags.length > 1 && (
                  <button type="button" className="btn-icon" aria-label={`Quitar ${t}`}
                    onClick={() => { setTags(tags.filter(x => x !== t)); if (borrador === t) setNuevoTag('') }}>✕</button>
                )}
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input id="nuevo-grupo-de-subida" className="form-input" value={nuevoTag} onChange={e => setNuevoTag(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); anadirTag() } }}
              placeholder="Añadir otro grupo" />
            <button type="button" className="btn btn-secondary" onClick={anadirTag} disabled={!nuevoTag.trim()}>Añadir</button>
          </div>
        </div>
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="tmdb" size={18} /> TMDb
        </h3>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Estado de la API key</label>
          <div style={{ fontSize: 13 }}>
            {settings?.tmdb_api_key_configured
              ? <><span style={{ color: 'var(--color-available)', display: 'inline-flex', alignItems: 'center', gap: 5 }}><CheckStatusIcon status="ok" /> Configurada</span>{settings.tmdb_api_key_masked && <code style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)' }}>{settings.tmdb_api_key_masked}</code>}</>
              : <span style={{ color: 'var(--color-error)' }}>✗ No configurada</span>}
          </div>
        </div>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Nueva API key <span className="form-hint">(dejar vacío para mantener la actual)</span></label>
          <input
            type="password"
            className="form-input"
            value={newKey}
            onChange={e => setNewKey(e.target.value)}
            placeholder="API key de TMDb"
            autoComplete="new-password"
          />
          <span className="form-hint">Usada para marcar proveedores disponibles en TMDb y para traducir los títulos de las series al español (eMuwarez exige el título siempre en español).</span>
        </div>
        <div style={{ marginBottom: 12 }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleTestTmdb}
            disabled={testingTmdb}
            type="button"
          >
            {testingTmdb ? 'Probando…' : 'Probar conexión'}
          </button>
          {tmdbTestResult && (
            <span style={{ marginLeft: 10, fontSize: 12, color: testResultColor(tmdbTestResult) }}>
              {testResultLabel(tmdbTestResult)}
            </span>
          )}
        </div>
        <div className="form-group">
          <label className="form-label">Región</label>
          <select className="form-input form-select" value={region} onChange={e => setRegion(e.target.value)}>
            {REGION_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label} ({o.value})</option>)}
          </select>
          <span className="form-hint">País para filtrar proveedores.</span>
        </div>
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="qbittorrent" size={18} /> qBittorrent
        </h3>
        <div className="form-group" style={{ marginBottom: 10 }}>
          <label className="form-label">URL del WebUI</label>
          <input className="form-input" value={qbitUrl} onChange={e => setQbitUrl(e.target.value)} placeholder="http://127.0.0.1" />
        </div>
        <div className="form-group" style={{ marginBottom: 10 }}>
          <label className="form-label">Tag</label>
          <input className="form-input" value={qbitTag} onChange={e => setQbitTag(e.target.value)} placeholder="Subidas" />
        </div>
        <div className="form-group" style={{ marginBottom: 10 }}>
          <label className="form-label">Usuario</label>
          <div style={{ position: 'relative' }}>
            <input
              className="form-input"
              type={showQbitUser ? 'text' : 'password'}
              value={qbitUser}
              onChange={e => setQbitUser(e.target.value)}
              placeholder="admin"
              autoComplete="off"
              style={{ paddingRight: 38 }}
            />
            <button
              type="button"
              onClick={() => setShowQbitUser(s => !s)}
              aria-label={showQbitUser ? 'Ocultar usuario' : 'Mostrar usuario'}
              style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', padding: 2 }}
              {...qbitUserEyeTip.triggerProps}
            >
              {qbitUserEyeTip.tooltipNode}
              {showQbitUser ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                  <line x1="1" y1="1" x2="23" y2="23" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
            </button>
          </div>
        </div>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Contraseña <span className="form-hint">(dejar vacío para mantener la actual)</span></label>
          <input type="password" className="form-input" value={qbitPass} onChange={e => { setQbitPass(e.target.value); setQuitarQbitPass(false) }} placeholder={quitarQbitPass ? 'Se quitará al guardar' : settings?.qbit_password_configured ? '••••••••' : 'Contraseña del WebUI'} autoComplete="new-password" />
          {settings?.qbit_password_configured && !qbitPass && (
            <button type="button" className="btn btn-secondary btn-sm" style={{ marginTop: 6, alignSelf: 'flex-start' }} onClick={() => setQuitarQbitPass(q => !q)}>
              {quitarQbitPass ? 'No quitarla' : 'Quitar la contraseña'}
            </button>
          )}
        </div>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label" htmlFor="qbit-qui-proxy">
            Proxy de <a href="https://getqui.com/docs/features/reverse-proxy" target="_blank" rel="noreferrer">qui</a>{' '}
            <span className="form-hint">(opcional; con él no hacen falta usuario ni contraseña)</span>
          </label>
          <input
            id="qbit-qui-proxy"
            type="password"
            className="form-input"
            value={qbitQui}
            onChange={e => { setQbitQui(e.target.value); setQuitarQui(false) }}
            placeholder={quitarQui ? 'Se quitará al guardar' : settings?.qbit_qui_configured ? '••••••••' : 'http://qui:7476/proxy/<clave>'}
            autoComplete="off"
          />
          {settings?.qbit_qui_configured && !qbitQui && (
            <button type="button" className="btn btn-secondary btn-sm" style={{ marginTop: 6, alignSelf: 'flex-start' }} onClick={() => setQuitarQui(q => !q)}>
              {quitarQui ? 'No quitarlo' : 'Quitar el proxy de qui'}
            </button>
          )}
        </div>
        <div>
          <button className="btn btn-secondary btn-sm" onClick={handleTestQbit} disabled={testingQbit} type="button">
            {testingQbit ? 'Probando…' : 'Probar conexión'}
          </button>
          {qbitTestResult && (
            <span style={{ marginLeft: 10, fontSize: 12, color: testResultColor(qbitTestResult) }}>
              {testResultLabel(qbitTestResult)}
            </span>
          )}
        </div>
      </div>

      <div className="placeholder-card provider-card">
        <h3 style={{ marginTop: 0, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" aria-hidden>
            <rect x="2.5" y="5" width="19" height="14" rx="2.5" stroke="#8b5cf6" strokeWidth="1.6" />
            <path d="M10 9.2v5.6l4.5-2.8z" fill="#8b5cf6" />
          </svg>
          Proveedores de vídeo
        </h3>
        <span className="form-hint" style={{ display: 'block', marginBottom: 6 }}>
          Se usa para elegir automáticamente el proveedor cuando TMDb devuelve varios. Arrastra para reordenar, o usa las flechas desde el asa de cada fila. El icono de cada uno enlaza a su web oficial.
        </span>
        <div className="form-group provider-card__body">
          <label className="form-label">Prioridad de proveedores</label>
          <ProviderPriorityPicker order={providerOrder} onChange={setProviderOrder} />
        </div>
      </div>

      <div className="placeholder-card provider-card">
        <h3 style={{ marginTop: 0, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="imghost" size={18} /> Proveedores de imágenes
        </h3>
        <span className="form-hint" style={{ display: 'block', marginBottom: 12 }}>
          Para las capturas que Uploadrr sube junto al torrent. Se prueban por orden de prioridad; arrastra para reordenar, o usa las flechas desde el asa de cada fila. <strong>imgbox</strong>, sin API key, va siempre el último.
        </span>
        <label className="form-label" style={{ display: 'block', marginBottom: 8 }}>Prioridad de proveedores</label>
        {(() => {
          const avail = settings?.image_hosts_available ?? []
          // imgbox no se ordena: la subida siempre lo prueba el último (fallback_order).
          const configuredIds = imgEnabled.filter(id => id !== 'imgbox')
          const notConfigured = avail.filter(h => h.id !== 'imgbox' && !configuredIds.includes(h.id))
          const metaOf = (id: string) => avail.find(h => h.id === id)
          const fila = (id: string, idx: number, asa?: { dragging: boolean; handleProps: DragHandleProps }) => {
            const h = metaOf(id); if (!h) return null
            const isDefault = id === 'imgbox'
            const dragging = !!asa?.dragging
            const t = imgTest[id]
            return (
              <div style={{
                padding: '8px 10px', borderRadius: 8,
                background: dragging ? 'color-mix(in srgb, var(--color-primary) 15%, transparent)' : 'color-mix(in srgb, var(--color-uploading) 6%, transparent)',
                border: `1px solid ${dragging ? 'var(--text-accent)' : 'var(--border)'}`,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ color: 'var(--text-muted)', fontSize: 11, width: 16, textAlign: 'center' }}>{idx + 1}</span>
                  {asa ? (
                    <HoverTitle
                      as="span"
                      tip="Arrastra para reordenar, o usa las flechas del teclado"
                      {...asa.handleProps}
                      className="drag-handle"
                      style={{ ...asa.handleProps.style, color: 'var(--text-accent)', width: 16, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', marginLeft: 8, marginRight: 8 }}
                    ><DragHandleIcon /></HoverTitle>
                  ) : <span style={{ width: 16, marginLeft: 8, marginRight: 8 }} />}
                  <a href={h.url} target="_blank" rel="noreferrer" title={`Abrir ${h.label}`}
                    onClick={e => e.stopPropagation()} onMouseDown={e => e.stopPropagation()}
                    style={{ display: 'inline-flex' }}>
                    <Favicon domain={domainOf(h.url)} src={h.favicon} size={15} background="var(--overlay-light)" fallback={<ServiceIcon type="imghost" size={15} />} />
                  </a>
                  <span style={{ fontSize: 13, fontWeight: 500, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{h.label}</span>
                  {isDefault && <span className="badge status-available">por defecto</span>}
                  {h.needs_key && (() => {
                    // Verde cuando hay clave guardada; gris parpadeando
                    // mientras no la haya, para que un proveedor recién
                    // añadido pida lo que le falta en vez de quedarse
                    // callado y fallar luego en plena subida.
                    const guardada = !!settings?.image_host_keys_configured?.includes(id)
                    return (
                      <button
                        type="button"
                        title={guardada ? 'API key comprobada. Pulsa para cambiarla' : 'Falta la API key. Pulsa para añadirla'}
                        className={`badge ${guardada ? 'status-available' : 'nom-na badge-blink'}`}
                        // Sin border:none — .badge lleva su propio borde
                        // y quitarlo era lo que lo hacía distinto del
                        // "por defecto" de al lado. El resto neutraliza
                        // lo que el navegador le añade a un <button>:
                        // su tipografía, su interlineado y su margen.
                        style={{
                          fontSize: 10, cursor: 'pointer', appearance: 'none',
                          fontFamily: 'inherit', lineHeight: 'inherit', margin: 0,
                        }}
                        onClick={e => { e.stopPropagation(); setKeyModalHost(id); setKeyDraft(''); setKeyError(null) }}
                        onMouseDown={e => e.stopPropagation()}
                      >API key</button>
                    )
                  })()}
                  {/* Los que llevan API key se prueban DENTRO de su
                      tarjeta, que es donde está la clave. Aquí el botón
                      dejaría su resultado donde ya no se enseña. */}
                  {/* Los controles van juntos a la derecha, con la X al
                      final. El empuje vive en el contenedor y no en el
                      botón Probar: ese botón solo existe para los
                      proveedores sin API key (los demás se prueban en su
                      tarjeta), así que colgar de él la alineación dejaba
                      la X pegada a las insignias en el resto. */}
                  <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
                    {!h.needs_key && (
                      <button className="btn btn-secondary btn-sm" style={{ fontSize: 11, padding: '2px 8px' }}
                        onClick={() => handleTestImghost(id)} disabled={imgTesting === id} type="button">
                        {imgTesting === id ? 'Probando…' : 'Probar'}
                      </button>
                    )}
                    {!isDefault && (
                      <RemoveImgHostButton onClick={() => toggleImgHost(id)} />
                    )}
                  </div>
                </div>
                {/* Solo para los que no tienen tarjeta: los demás ya lo
                    enseñan ahí y salía dos veces. */}
                {!h.needs_key && t && <div style={{ fontSize: 11, marginTop: 4, color: testResultColor(t) }}>{testResultLabel(t)}</div>}
              </div>
            )
          }
          return (
            <>
            <div className="provider-card__body">
              <div className="provider-card__list">
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <SortableList etiqueta={id => metaOf(id)?.label ?? id} ids={configuredIds} onChange={setImgEnabled} gap={8} renderRow={fila} />
                  {fila('imgbox', configuredIds.length)}
                </div>
              </div>
              {notConfigured.length > 0 && (
                <button className="btn btn-secondary btn-sm provider-card__add-btn" onClick={() => setShowAddImg(true)} type="button">
                  + Añadir proveedor ({notConfigured.length})
                </button>
              )}
            </div>
              {keyModalHost && (() => {
                const host = (settings?.image_hosts_available ?? []).find((x: { id: string }) => x.id === keyModalHost)
                const guardada = !!settings?.image_host_keys_configured?.includes(keyModalHost)
                const t = imgTest[keyModalHost]
                // Guardar comprueba la clave ANTES: así una clave guardada es
                // una clave que funciona, y la insignia verde no miente. Es lo
                // que faltaba cuando imgbb daba "conectado" en Ajustes y
                // fallaba en cada subida.
                const guardar = async () => {
                  if (!keyDraft.trim()) return
                  setKeySaving(true); setKeyError(null)
                  try {
                    const check = await testImghostConnection(keyModalHost, keyDraft.trim())
                    setImgTest(p => ({ ...p, [keyModalHost]: check }))
                    if (!check.ok) return          // el motivo ya se enseña debajo
                    const updated = await updateSettings({ image_host_keys: { [keyModalHost]: keyDraft.trim() } })
                    setSettings(updated)
                    setKeyModalHost(null)
                    setKeyDraft('')
                  } catch (e: unknown) { setKeyError(e instanceof Error ? e.message : String(e)) }
                  finally { setKeySaving(false) }
                }
                const quitar = async () => {
                  setKeySaving(true); setKeyError(null)
                  try {
                    setSettings(await updateSettings({ clear: [`image_host_key:${keyModalHost}`] }))
                    setKeyModalHost(null)
                    setKeyDraft('')
                  } catch (e: unknown) { setKeyError(e instanceof Error ? e.message : String(e)) }
                  finally { setKeySaving(false) }
                }
                return (
                  <Modal titulo={<>API key de {host?.label ?? keyModalHost}</>} onClose={() => { if (!keySaving) setKeyModalHost(null) }} style={{ maxWidth: 480 }}>
                    <div className="modal-body">
                      <div style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
                        <input
                          type="password" className="form-input" style={{ flex: 1 }} autoComplete="new-password"
                          value={keyDraft} onChange={e => setKeyDraft(e.target.value)}
                          placeholder={guardada ? '•••••••• (hay una guardada)' : `API key de ${host?.label ?? ''}`}
                          autoFocus
                        />
                        <button
                          className="btn btn-secondary" type="button"
                          onClick={() => handleTestImghost(keyModalHost)}
                          disabled={imgTesting === keyModalHost || !keyDraft.trim()}
                        >
                          {imgTesting === keyModalHost ? 'Probando…' : 'Probar'}
                        </button>
                      </div>
                      {t && <div style={{ fontSize: 12, marginTop: 8, color: testResultColor(t) }}>{testResultLabel(t)}</div>}
                      {keyError && <div className="text-error" style={{ fontSize: 12, marginTop: 8 }}>✗ {keyError}</div>}
                      <p style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 10, marginBottom: 0 }}>
                        La clave se comprueba contra el proveedor, sin subir ninguna imagen. Guardar la
                        comprueba también: si no vale, no se guarda.
                      </p>
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
                        {guardada && (
                          <button className="btn btn-secondary" type="button" style={{ marginRight: 'auto' }} onClick={quitar} disabled={keySaving}>
                            Quitar la clave
                          </button>
                        )}
                        <button className="btn btn-secondary" type="button" onClick={() => setKeyModalHost(null)} disabled={keySaving}>Cancelar</button>
                        <button className="btn btn-primary" type="button" onClick={guardar} disabled={!keyDraft.trim() || keySaving}>
                          {keySaving ? 'Comprobando…' : 'Guardar'}
                        </button>
                      </div>
                    </div>
                  </Modal>
                )
              })()}

              {showAddImg && (
                <Modal titulo="Añadir proveedor de imágenes" onClose={() => setShowAddImg(false)} style={{ maxWidth: 480 }}>
                  <div className="modal-body">
                    {notConfigured.length === 0 ? (
                      <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>Ya están todos añadidos.</p>
                    ) : (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 6, maxHeight: 'calc(var(--vh100) * 0.55)', overflowY: 'auto' }}>
                        {notConfigured.map(h => (
                          <button key={h.id} className="btn btn-ghost btn-sm" type="button"
                            style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-start', justifySelf: 'start', fontSize: 12 }}
                            onClick={() => toggleImgHost(h.id)}>
                            <Favicon domain={domainOf(h.url)} src={h.favicon} size={16} background="var(--overlay-light)" fallback={<ServiceIcon type="imghost" size={16} />} /> {h.label} {h.needs_key && <span className="badge nom-na">API key</span>}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </Modal>
              )}
            </>
          )
        })()}
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="1.75" aria-hidden>
            <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
          </svg>
          Acceso a la biblioteca
          <InfoIcon text="Antes de subir un archivo, la app comprueba que su ruta está dentro de una de estas carpetas: una red de seguridad para que nunca se toque un archivo fuera de donde debería. Si la dejas vacía, las subidas reales se bloquearán hasta que la rellenes." />
        </h3>
        <p className="form-hint" style={{ marginTop: 0, marginBottom: 12 }}>
          La carpeta donde este contenedor accede a tu biblioteca (el punto de montaje del volumen, no necesariamente
          el mismo que reportan Radarr/Sonarr). Por ejemplo: <code>/data</code> si lo montas igual que Radarr/Sonarr.
          Varias rutas separadas por comas.
        </p>
        <div className="form-group">
          <label className="form-label">Rutas permitidas</label>
          <input
            className="form-input"
            value={allowedRoots}
            onChange={e => setAllowedRoots(e.target.value)}
            placeholder="/data"
          />
        </div>
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="1.75" aria-hidden>
            <line x1="4" y1="21" x2="4" y2="14" /><line x1="4" y1="10" x2="4" y2="3" />
            <line x1="12" y1="21" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="3" />
            <line x1="20" y1="21" x2="20" y2="16" /><line x1="20" y1="12" x2="20" y2="3" />
            <line x1="1" y1="14" x2="7" y2="14" /><line x1="9" y1="8" x2="15" y2="8" /><line x1="17" y1="16" x2="23" y2="16" />
          </svg>
          Otros
        </h3>
        <div className="form-group">
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Renombrar/Ordenar pistas
            <InfoIcon text="Qué se le hace a las pistas de audio y subtítulos antes de subir. Renombrar les pone nombre siguiendo las reglas de eMuwarez y cambia solo la cabecera del archivo: es casi instantáneo por grande que sea. Reordenar las coloca en orden (Español, Català, Inglés, resto) y obliga a reescribir el contenedor entero, y tarda en proporción al tamaño. Si el archivo lo comparte un torrent (un hardlink), no se escribe en él: renombrar se hace en una copia por reflink en la carpeta de subidas y reordenar se omite. Con Ninguno el archivo se sube tal cual, sin tocar tampoco el título interno. En los tres primeros se marca la pista predeterminada, que es lo que decide qué audio suena al abrirlo." />
          </label>
          <select className="form-input form-select" value={modoDePistas}
                  onChange={e => setModoDePistas(normalizarModo(e.target.value))}>
            {MODOS_PISTAS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </div>        {/* El único ajuste de esta pestaña que NO se guarda con el botón: es
            de este navegador, no de la instalación, y se aplica y se recuerda
            al elegirlo. Ver utils/uiScale.ts. */}
        <div className="form-group">
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Tamaño de interfaz
            <InfoIcon text="Agranda o encoge la interfaz entera, para ajustarla a tu pantalla. La misma resolución se ve muy distinta según el tamaño del monitor y a la distancia que lo tengas, así que aquí no se adivina nada: lo eliges tú y se aplica al momento. Se guarda solo en este navegador, así que puedes tener un tamaño en el sobremesa y otro en el portátil, y no entra en el backup de configuración." />
          </label>
          <select className="form-input form-select" value={tamanoInterfaz}
                  onChange={e => setTamanoInterfaz(guardarTamano(Number(e.target.value)))}>
            {TAMANOS.map(t => (
              <option key={t} value={t}>{t}%{t === TAMANO_POR_DEFECTO ? ' (por defecto)' : ''}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Internal Source Tool
            <InfoIcon text="Herramienta interna que deduce el source analizando el archivo real con MediaInfo, FFprobe y MKVToolNix, sin mirar el nombre. Todavía está en desarrollo y puede ser inexacta, por eso viene desactivada. Activada, añade su columna a la comparación de Source y participa en el aviso de discrepancia. Desactivada, esa columna sale vacía y el aviso compara solo el nombre del archivo con Radarr/Sonarr; el source final no cambia salvo en archivos donde ni el nombre ni Radarr/Sonarr dicen nada, que siguen usando la estimación por bitrate de siempre." />
          </label>
          <select className="form-input form-select" value={sourceEngine ? 'true' : 'false'} onChange={e => setSourceEngine(e.target.value === 'true')}>
            <option value="false">Desactivada</option>
            <option value="true">Activada</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Subir el logo del contenido
            <InfoIcon text="Incrusta el logo del contenido al principio de la descripción del torrent, en español cuando TMDb lo tiene en ese idioma. Desactivado, la descripción se sube sin logo; el resto (capturas, ficha técnica y tráiler) no cambia." />
          </label>
          <select className="form-input form-select" value={addLogo ? 'true' : 'false'} onChange={e => setAddLogo(e.target.value === 'true')}>
            <option value="true">Sí</option>
            <option value="false">No</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="capturas-de-los-packs" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Capturas de los packs
            <InfoIcon text="En un pack de temporada o de serie completa, de qué capítulos genera y sube capturas Uploadrr. Por defecto, solo del primero (el de número más bajo, sin contar los especiales si el pack trae otra temporada). Con todos los capítulos, cada uno lleva además las suyas en un desplegable de la descripción, y con muchos capítulos la subida tarda bastante más." />
          </label>
          <select id="capturas-de-los-packs" className="form-input form-select" value={capturasPorCapitulo ? 'true' : 'false'} onChange={e => setCapturasPorCapitulo(e.target.value === 'true')}>
            <option value="false">Solo del primer capítulo</option>
            <option value="true">De todos los capítulos</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Máximo de Subidas en Paralelo
            <InfoIcon text="Cuántas subidas pueden estar en curso a la vez, de principio a fin (verificación previa, nomenclatura, remux, hasheo del torrent y transferencia a eMuwarez). No es solo una cola visual: las demás no dan ni un paso hasta que se libera un hueco. Sin límite las deja correr todas a la vez. El botón «Ver Máximo» estima cuántas puede aguantar este equipo según su RAM y CPU disponibles." />
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <select className="form-input form-select" style={{ flex: 1 }} value={uploadMaxConcurrent} onChange={e => setUploadMaxConcurrent(Number(e.target.value))}>
              <option value={0}>Sin límite</option>
              {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => <option key={n} value={n}>{n}</option>)}
            </select>
            <button
              className="btn btn-secondary btn-sm"
              type="button"
              onClick={handleTestConcurrency}
              disabled={testingConcurrency}
            >
              {testingConcurrency ? 'Consultando…' : 'Ver Máximo'}
            </button>
          </div>
          {concurrencyEstimate && (
            <Modal titulo="Máximo de subidas en paralelo" onClose={() => setConcurrencyEstimate(null)} style={{ maxWidth: 860 }}>
              <div className="modal-body">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Recurso</th>
                      <th>Disponible</th>
                      <th>Uso estimado por 1 subida</th>
                      <th>Qué lo consume</th>
                      <th>Subidas soportadas</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>RAM</td>
                      <td>{concurrencyEstimate.available_ram_gb} GB</td>
                      <td>{concurrencyEstimate.assumed_ram_gb_per_slot} GB</td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        Capturas con FFmpeg: extraer y escalar fotogramas. Es casi todo el gasto.
                      </td>
                      <td>{concurrencyEstimate.ram_limited_to}</td>
                    </tr>
                    <tr>
                      <td>CPU</td>
                      <td>{concurrencyEstimate.cpu_cores} núcleos</td>
                      <td>1 núcleo</td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        Hasheo del torrent con torf: satura un núcleo entero. Y las capturas con FFmpeg.
                      </td>
                      <td>{concurrencyEstimate.cpu_limited_to}</td>
                    </tr>
                  </tbody>
                </table>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginTop: 14 }}>
                  <span className="form-hint">
                    Estimación orientativa, no tiene en cuenta la velocidad del disco o de la red.
                    El trabajo sobre las pistas no entra en estos números, ni activando «Reordenar
                    pistas»: reordenar con mkvmerge copia los flujos sin recodificar, así que tarda
                    lo que tarde el disco pero apenas gasta RAM ni CPU. Y solo renombrar es aún más
                    barato: mkvpropedit toca la cabecera en el sitio, sin releer el archivo.
                  </span>
                  <button
                    className="btn btn-secondary btn-sm"
                    type="button"
                    style={{ flexShrink: 0 }}
                    onClick={() => { setUploadMaxConcurrent(concurrencyEstimate.recommended); setConcurrencyEstimate(null) }}
                  >
                    Establecer {concurrencyEstimate.recommended}
                  </button>
                </div>
              </div>
            </Modal>
          )}
        </div>
        <div className="form-group">
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Ignorar Temporadas especiales
            <InfoIcon text="Excluye la temporada especial (temporada 0) del estado global de una serie. Si tienes todas las temporadas y capítulos salvo los especiales, la serie aparece como completa en las columnas Estado y eMuwarez de la Biblioteca. Sus atributos consolidados (resolución, source, códecs, audio y subtítulos) se calculan ignorando los especiales, y en el Panel sus capítulos faltantes no cuentan como faltantes." />
          </label>
          <select className="form-input form-select" value={ignoreSpecials ? 'true' : 'false'} onChange={e => setIgnoreSpecials(e.target.value === 'true')}>
            <option value="true">Sí</option>
            <option value="false">No</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Máximo de Elementos en Recomendaciones
            <InfoIcon text="Cuántos elementos como máximo se muestran en Recomendaciones. Sin límite los muestra todos." />
          </label>
          <select className="form-input form-select" value={recentLimit} onChange={e => setRecentLimit(Number(e.target.value))}>
            <option value={0}>Sin límite</option>
            {[50, 100, 150, 200, 250, 300].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>

      </div>
      </div>
    </div>
  )
}

// ---------- Account (username/password) card ----------
// Self-contained: its own "Guardar" instead of joining ConfigTab's shared
// save button — changing credentials always needs the current password
// re-entered, so it can't silently ride along with the rest of the form.
function AccountCard() {
  const [username, setUsername] = useState('')
  const [newUsername, setNewUsername] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const setMsg = useSettingsMessageAdapter()

  useEffect(() => { getMe().then(u => setUsername(u.username)).catch(() => {}) }, [])

  const dirty = newUsername.trim() !== '' || newPassword !== ''

  async function handleSave() {
    setMsg(null)
    if (!currentPassword) { setMsg({ ok: false, text: 'Introduce tu contraseña actual para confirmar el cambio.' }); return }
    if (!dirty) { setMsg({ ok: false, text: 'No hay ningún cambio que guardar.' }); return }
    setSaving(true)
    try {
      const resp = await changeCredentials({
        current_password: currentPassword,
        new_username: newUsername.trim() || undefined,
        new_password: newPassword || undefined,
      })
      setUsername(resp.username)
      setNewUsername('')
      setNewPassword('')
      setCurrentPassword('')
      setMsg({ ok: true, text: '✓ Credenciales actualizadas correctamente.' })
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="placeholder-card">
      <h3 style={{ marginTop: 0, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
        <IconoUsuario size={18} style={{ color: 'var(--text-accent)' }} /> Cuenta
      </h3>
      <p className="form-hint" style={{ marginTop: 0, marginBottom: 14 }}>
        Cambia el usuario y/o la contraseña con la que inicias sesión en esta aplicación.
      </p>
      <div className="form-group" style={{ marginBottom: 12 }}>
        <label className="form-label">Usuario actual</label>
        <input className="form-input" value={username || '…'} disabled />
      </div>
      <div className="form-group" style={{ marginBottom: 12 }}>
        <label className="form-label">Nuevo usuario <span className="form-hint">(dejar vacío para no cambiarlo)</span></label>
        <input className="form-input" value={newUsername} onChange={e => setNewUsername(e.target.value)} placeholder={username} autoComplete="off" />
      </div>
      <div className="form-group" style={{ marginBottom: 12 }}>
        <label className="form-label">Nueva contraseña <span className="form-hint">(dejar vacío para no cambiarla)</span></label>
        <input type="password" className="form-input" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Nueva contraseña" autoComplete="new-password" />
      </div>
      <div className="form-group" style={{ marginBottom: 14 }}>
        <label className="form-label">Contraseña actual <span className="form-hint">(obligatoria para confirmar)</span></label>
        <input type="password" className="form-input" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} placeholder="Tu contraseña actual" autoComplete="current-password" />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving || !dirty}>
          {saving ? 'Guardando…' : 'Guardar cambios'}
        </button>
      </div>
    </div>
  )
}

// ---------- Sesiones abiertas ----------
// Caducan a los 30 días sin usarse. «Cerrar las demás» deja solo esta: sirve tras un
// dispositivo perdido o una contraseña que se ha visto de más.
function SessionsCard() {
  const [datos, setDatos] = useState<{ sessions: SesionAbierta[]; inactive_days: number } | null>(null)
  const [cerrando, setCerrando] = useState(false)
  const setMsg = useSettingsMessageAdapter()

  const cargar = useCallback(async () => {
    try { setDatos(await getSessions()) } catch { /* sin lista: la tarjeta queda cargando */ }
  }, [])
  useAlEntrar(() => { void cargar() })

  async function handleCerrarLasDemas() {
    setCerrando(true)
    try {
      const { closed } = await closeOtherSessions()
      setMsg({ ok: true, text: closed === 1 ? '✓ Se ha cerrado 1 sesión.' : `✓ Se han cerrado ${closed} sesiones.` })
      await cargar()
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setCerrando(false)
    }
  }

  return (
    <div className="placeholder-card">
      <h3>Sesiones abiertas</h3>
      {datos === null ? (
        <p className="form-hint">Cargando…</p>
      ) : (
        <>
          <p className="form-hint sesiones-nota">
            Los navegadores donde has iniciado sesión. Una sesión se cierra sola a los {datos.inactive_days} días sin usarse.
          </p>
          <div className="sesiones-lista">
            {datos.sessions.map(s => (
              <div key={s.id}>
                <div className="sesiones-lista__nombre">
                  <span title={s.user_agent ?? undefined}>{descripcionDeSesion(s.user_agent)}</span>
                  {s.current && <span className="badge status-available">Esta sesión</span>}
                </div>
                <div className="form-hint">
                  {s.ip_address ?? 'IP desconocida'} · {s.current ? 'activa ahora' : `última actividad ${timeAgo(s.last_used_at)}`} · abierta el {formatDate(s.created_at)}
                </div>
              </div>
            ))}
          </div>
          <button className="btn btn-secondary btn-sm" type="button" onClick={handleCerrarLasDemas} disabled={cerrando || datos.sessions.length < 2}>
            {cerrando ? 'Cerrando…' : 'Cerrar las demás'}
          </button>
        </>
      )}
    </div>
  )
}

// ---------- Path mappings card (library.path_mappings only) ----------
// Self-contained like AccountCard: its own load/save, untouched by
// ConfigTab's dirty-tracking or "Guardar configuración" button. PUT /settings
// only writes fields it's given, so saving here never touches anything else.
function PathMappingsCard() {
  const [mappings, setMappings] = useState<{ from: string; to: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const setMsg = useSettingsMessageAdapter()
  const [baseline, setBaseline] = useState('[]')

  useEffect(() => {
    fetchSettings()
      .then(s => {
        const m = s.path_mappings ?? []
        setMappings(m)
        setBaseline(JSON.stringify(m))
      })
      .finally(() => setLoading(false))
  }, [])

  const dirty = JSON.stringify(mappings) !== baseline

  async function handleSave() {
    setSaving(true)
    setMsg(null)
    try {
      const cleaned = mappings.map(m => ({ from: m.from.trim(), to: m.to.trim() })).filter(m => m.from && m.to)
      const updated = await updateSettings({ path_mappings: cleaned })
      const m = updated.path_mappings ?? []
      setMappings(m)
      setBaseline(JSON.stringify(m))
      setMsg({ ok: true, text: '✓ Mapeo de rutas guardado' })
    } catch (e: unknown) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="placeholder-card">
      <h3 style={{ marginTop: 0, marginBottom: 6 }}>Mapeo de rutas (biblioteca remota)</h3>
      <p className="form-hint" style={{ marginTop: 0, marginBottom: 12 }}>
        Traduce la ruta que reporta Radarr/Sonarr a la ruta donde la app alcanza el archivo
        (monta la biblioteca por SSHFS/NFS/SMB donde quieras). Se aplica al leer MediaInfo,
        verificar y subir. Sin reglas, no cambia nada.
      </p>
      {loading ? (
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Cargando…</p>
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {mappings.length === 0 && (
              <span className="form-hint">No hay reglas. Añade una para acceder a una biblioteca remota.</span>
            )}
            {mappings.map((m, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <input
                  className="form-input" style={{ flex: 1, minWidth: 200 }}
                  value={m.from} placeholder="Ruta de Radarr/Sonarr: /data/media"
                  onChange={e => setMappings(p => p.map((x, j) => j === i ? { ...x, from: e.target.value } : x))}
                />
                <span style={{ color: 'var(--text-muted)' }}>→</span>
                <input
                  className="form-input" style={{ flex: 1, minWidth: 200 }}
                  value={m.to} placeholder="Ruta local: /home/alvaro/mnt/emu-media"
                  onChange={e => setMappings(p => p.map((x, j) => j === i ? { ...x, to: e.target.value } : x))}
                />
                <RemoveMappingRuleButton onClick={() => setMappings(p => p.filter((_, j) => j !== i))} />
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
            <button className="btn btn-secondary btn-sm" type="button"
              onClick={() => setMappings(p => [...p, { from: '', to: '' }])}>+ Añadir regla</button>
            <button className="btn btn-primary btn-sm" type="button" onClick={handleSave} disabled={saving || !dirty}>
              {saving ? 'Guardando…' : 'Guardar cambios'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ---------- Diagnostics tab ----------
function VersionCard() {
  const [info, setInfo] = useState<VersionInfo | null>(null)
  const [comprobando, setComprobando] = useState(false)
  const mensaje = useSettingsMessage()

  const cargar = useCallback(async (refrescar = false) => {
    setComprobando(refrescar)
    try {
      const datos = await getVersionInfo(refrescar)
      setInfo(datos)
      // Al hueco de la fila de pestañas, como el resto de mensajes.
      //
      // Permanente solo cuando queda algo por hacer: hay versión nueva, o no
      // se ha podido comprobar. "Estás al día" es una confirmación de que la
      // comprobación se hizo, así que se comporta como los demás y desaparece
      // a los cinco segundos; dejarlo fijo era ruido en todas las pestañas.
      if (datos.estado === 'hay_novedad') {
        mensaje(false, `Hay una versión más nueva${datos.ultima.version ? `: v${datos.ultima.version}` : ''}`,
                { tono: 'aviso', permanente: true })
      } else if (datos.estado === 'al_dia') {
        mensaje(true, 'Estás en la última versión publicada', { borrarPermanente: true })
      } else {
        mensaje(false, datos.motivo || 'No se ha podido comprobar si hay una versión más nueva',
                { tono: 'aviso', permanente: true })
      }
    } catch (e: unknown) {
      mensaje(false, e instanceof Error ? e.message : String(e), { permanente: true })
    } finally {
      setComprobando(false)
    }
  }, [mensaje])

  useEffect(() => { cargar() }, [cargar])

  const fila = (etiqueta: string, valor: React.ReactNode) => (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      <td style={{ padding: '6px 8px', color: 'var(--text-secondary)', width: 150 }}>{etiqueta}</td>
      <td style={{ padding: '6px 8px', wordBreak: 'break-all' }}>{valor}</td>
    </tr>
  )

  // El digest es largo y no aporta leído entero: se enseña recortado y entero
  // al pasar el ratón, como el resto de identificadores de la aplicación.
  const digest = (valor?: string | null) => {
    if (!valor) return <span style={{ color: 'var(--text-muted)' }}>—</span>
    const corto = valor.startsWith('sha256:') ? valor.slice(0, 19) + '…' : valor.slice(0, 12) + '…'
    return <HoverTitle tip={valor}><code style={{ fontSize: 12 }}>{corto}</code></HoverTitle>
  }

  return (
    <div className="placeholder-card">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <h3 style={{ margin: 0 }}>Versión</h3>
        <button className="btn btn-secondary btn-sm" type="button"
                onClick={() => cargar(true)} disabled={comprobando}>
          {comprobando ? 'Comprobando…' : 'Comprobar ahora'}
        </button>
      </div>
      {!info && <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Cargando…</p>}
      {info && (
        <>
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <tbody>
              {fila('Versión', info.version)}
              {fila('Commit', info.commit_corto
                ? <HoverTitle tip={info.commit!}><code style={{ fontSize: 12 }}>{info.commit_corto}</code></HoverTitle>
                : <span style={{ color: 'var(--text-muted)' }}>sin sellar</span>)}
              {fila('Construida', info.construida || <span style={{ color: 'var(--text-muted)' }}>—</span>)}
              {fila('Digest', digest(info.digest))}
              {info.estado === 'hay_novedad' && fila('Última publicada',
                <>
                  {info.ultima.commit_corto
                    ? <HoverTitle tip={info.ultima.commit!}><code style={{ fontSize: 12 }}>{info.ultima.commit_corto}</code></HoverTitle>
                    : '—'}
                  {info.ultima.publicada ? <span style={{ color: 'var(--text-muted)' }}> · {info.ultima.publicada}</span> : null}
                </>)}
              {info.estado === 'hay_novedad' && fila('Digest publicado', digest(info.ultima.digest))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

// Integridad y VACUUM, dentro de la tarjeta "Base de datos" de Diagnóstico.
function DatabaseActions({ onRefresh }: { onRefresh: () => void }) {
  const [busy, setBusy] = useState(false)
  const [vacuumConfirm, setVacuumConfirm] = useState('')
  const showMessage = useSettingsMessage()

  async function handleIntegrity() {
    setBusy(true)
    try {
      const r = await runIntegrityCheck()
      showMessage(r.ok, r.ok ? `✓ ${r.message}` : `✗ ${r.message || r.error}`)
    } catch (e: unknown) {
      showMessage(false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally { setBusy(false) }
  }

  async function handleVacuum(dry: boolean) {
    if (!dry && vacuumConfirm !== 'MANTENIMIENTO_DB') {
      showMessage(false, 'Escribe MANTENIMIENTO_DB para confirmar'); return
    }
    setBusy(true)
    try {
      const r = await runVacuum({ dry_run: dry, apply: !dry, confirmation: dry ? undefined : vacuumConfirm })
      showMessage(r.ok ?? false, r.ok ? `✓ ${r.message}` : `✗ ${r.error}`)
      if (r.ok && !dry) onRefresh()
    } catch (e: unknown) {
      showMessage(false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally { setBusy(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 14 }}>
      <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: 0 }}>
        <strong>Verificar integridad</strong> ejecuta <code>PRAGMA integrity_check</code> (solo lectura).{' '}
        <strong>VACUUM</strong> compacta la BD y libera las páginas libres; escribe <code>MANTENIMIENTO_DB</code> para ejecutarlo.
      </p>
      <input
        type="text"
        placeholder="Confirmación: MANTENIMIENTO_DB"
        aria-label="Confirmación de VACUUM"
        value={vacuumConfirm}
        onChange={e => setVacuumConfirm(e.target.value)}
        style={{ width: '100%', padding: '6px 10px', fontSize: 13, boxSizing: 'border-box' }}
      />
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button className="btn btn-secondary" onClick={handleIntegrity} disabled={busy}>Verificar integridad</button>
        <button className="btn btn-secondary" onClick={() => handleVacuum(true)} disabled={busy}>Previsualizar VACUUM</button>
        <button className="btn btn-danger" onClick={() => handleVacuum(false)} disabled={busy}>Ejecutar VACUUM</button>
      </div>
    </div>
  )
}

function DiagnosticsTab({ status, onRefresh }: { status: MaintenanceStatus | null; onRefresh: () => void }) {
  const db = status?.database
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <VersionCard />
      <div className="placeholder-card">
        <h3>Base de datos</h3>
        {!db ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Cargando…</p>
        ) : !db.ok ? (
          <p style={{ color: 'var(--color-error)', fontSize: 13 }}>✗ {db.error}</p>
        ) : (
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <tbody>
              {[
                ['Ruta', db.db_path],
                ['Tamaño', formatBytes(db.size_bytes ?? 0)],
                ['Páginas', db.page_count],
                ['Freelist', db.freelist_count],
                ['Fragmentación', `${db.fragmentation_pct ?? 0} %`],
              ].map(([k, v]) => (
                <tr key={String(k)} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '6px 8px', color: 'var(--text-secondary)', width: 130 }}>{k}</td>
                  <td style={{ padding: '6px 8px' }}>{String(v ?? '—')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <DatabaseActions onRefresh={onRefresh} />
      </div>
      <div className="placeholder-card">
        <h3>Inventario de configuración</h3>
        {!status ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Cargando…</p>
        ) : (
          <>
            <p style={{ fontSize: 13, margin: '0 0 8px' }}>
              Directorio: <code>{status.config_inventory.config_dir}</code><br />
              Archivos: {status.config_inventory.files.length} &nbsp;·&nbsp;
              Tamaño: {formatBytes(status.config_inventory.total_size_bytes)}
            </p>
          </>
        )}
      </div>
      <PathMappingsCard />
    </div>
  )
}

// ---------- Backup tab ----------
function BackupTab({ status, onRefresh }: { status: MaintenanceStatus | null; onRefresh: () => void }) {
  const [backups, setBackups] = useState<BackupInfo[]>([])
  const [backupDir, setBackupDir] = useState('')
  const [busy, setBusy] = useState(false)
  const [restoreName, setRestoreName] = useState('')
  const [restoreConfirm, setRestoreConfirm] = useState('')

  const showMessage = useSettingsMessage()

  const loadBackups = useCallback(async () => {
    try {
      const r = await listBackups()
      setBackups(r.backups)
      setBackupDir(r.backup_dir)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { loadBackups() }, [loadBackups])

  async function handleBackup() {
    setBusy(true)
    try {
      const r = await createBackup()
      showMessage(r.ok, r.ok ? `✓ Backup creado: ${r.archive_name} (${formatBytes(r.size_bytes ?? 0)})` : `✗ ${r.error}`)
      if (r.ok) { loadBackups(); onRefresh() }
    } catch (e: unknown) {
      showMessage(false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleRestore(dry: boolean) {
    if (!restoreName) { showMessage(false, 'Elige un backup'); return }
    if (!dry && restoreConfirm !== 'RESTAURAR_CONFIG') {
      showMessage(false, 'Escribe RESTAURAR_CONFIG para confirmar'); return
    }
    setBusy(true)
    try {
      const r = await restoreBackup(restoreName, {
        dry_run: dry,
        apply: !dry,
        confirmation: dry ? undefined : restoreConfirm,
      })
      showMessage(r.ok, r.ok ? `✓ ${r.message}` : `✗ ${r.error}`)
    } catch (e: unknown) {
      showMessage(false, `✗ ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="placeholder-card">
        <h3>Crear backup</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 12px' }}>
          Crea un archivo <code>.tar.gz</code> del directorio de configuración, sin las claves: las API keys, la
          contraseña de qBittorrent, el webhook de Discord y el token de Telegram van vacíos, y no entran
          el <code>config.yaml</code> ni las cookies de Uploadrr-EMU.
        </p>
        <button className="btn btn-primary" onClick={handleBackup} disabled={busy}>
          {busy ? 'Creando…' : 'Crear backup ahora'}
        </button>
      </div>

      <div className="placeholder-card">
        <h3>Backups existentes ({status?.backups_count ?? backups.length})</h3>
        {backupDir && (
          <p style={{ color: 'var(--text-secondary)', fontSize: 12, margin: '0 0 10px' }}>
            Ubicación: <code>{backupDir}</code>
          </p>
        )}
        {backups.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No hay backups.</p>
        ) : (
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Nombre', 'Tamaño', 'Fecha'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '4px 8px', borderBottom: '1px solid var(--border)', color: 'var(--text-secondary)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {backups.map(b => (
                <tr key={b.path} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '5px 8px' }}>{b.name}</td>
                  <td style={{ padding: '5px 8px' }}>{formatBytes(b.size_bytes)}</td>
                  <td style={{ padding: '5px 8px' }}>{b.created_at.slice(0, 16).replace('T', ' ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="placeholder-card">
        <h3>Restaurar backup</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: '0 0 10px' }}>
          Elige uno de los backups existentes en <code>{backupDir || '…'}</code>. Las claves que el backup no
          lleve se quedan como las tienes ahora.
        </p>
        <select
          className="form-input form-select"
          value={restoreName}
          onChange={e => setRestoreName(e.target.value)}
          style={{ width: '100%', marginBottom: 8 }}
        >
          <option value="">Selecciona un backup…</option>
          {backups.map(b => (
            <option key={b.path} value={b.name}>{b.name} ({formatBytes(b.size_bytes)})</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Confirmación: RESTAURAR_CONFIG (solo para restauración real)"
          value={restoreConfirm}
          onChange={e => setRestoreConfirm(e.target.value)}
          style={{ width: '100%', marginBottom: 10, padding: '6px 10px', fontSize: 13, boxSizing: 'border-box' }}
        />
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary" onClick={() => handleRestore(true)} disabled={busy}>Previsualizar</button>
          <button className="btn btn-danger" onClick={() => handleRestore(false)} disabled={busy}>Restaurar</button>
        </div>
      </div>
    </div>
  )
}

// Per-channel checkbox list: which event types this channel forwards.
function EventPicker({ title, eventTypes, selected, disabled, onToggle }: {
  title: string
  eventTypes: { code: string; label: string }[]
  selected: string[]
  disabled: boolean
  onToggle: (code: string, checked: boolean) => void
}) {
  if (eventTypes.length === 0) return null
  return (
    <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--border)', opacity: disabled ? 0.5 : 1 }}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>{title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {eventTypes.map(ev => (
          <label key={ev.code} className="checkbox-label" style={{ fontSize: 13 }}>
            <input
              type="checkbox"
              checked={selected.includes(ev.code)}
              disabled={disabled}
              onChange={e => onToggle(ev.code, e.target.checked)}
            /> {ev.label}
          </label>
        ))}
      </div>
    </div>
  )
}

function notifSignature(v: {
  uiEnabled: boolean; uiEvents: string[]
  discordEnabled: boolean; discordWebhook?: string; telegramEnabled: boolean
  telegramToken?: string; telegramChatId: string; discordEvents: string[]; telegramEvents: string[]
  quitarDiscord?: boolean; quitarTelegram?: boolean
}): string {
  return JSON.stringify([
    v.uiEnabled, v.uiEvents,
    v.discordEnabled, v.discordWebhook ?? '', v.telegramEnabled, v.telegramToken ?? '',
    v.telegramChatId, v.discordEvents, v.telegramEvents,
    v.quitarDiscord ?? false, v.quitarTelegram ?? false,
  ])
}

// ---------- Notifications tab ----------
function NotificationsTab({ onExposeSave }: { onExposeSave: (a: SaveExpose | null) => void }) {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const setMsg = useSettingsMessageAdapter()

  const [discordEnabled, setDiscordEnabled] = useState(false)
  const [discordWebhook, setDiscordWebhook] = useState('')
  const [quitarDiscord, setQuitarDiscord] = useState(false)
  const [testingDiscord, setTestingDiscord] = useState(false)

  const [telegramEnabled, setTelegramEnabled] = useState(false)
  const [telegramToken, setTelegramToken] = useState('')
  const [quitarTelegram, setQuitarTelegram] = useState(false)
  const [telegramChatId, setTelegramChatId] = useState('')
  const [testingTelegram, setTestingTelegram] = useState(false)

  // In-app bell ("UI" card): a configurable channel like Discord/Telegram, but
  // on by default and without credentials.
  const [uiEnabled, setUiEnabled] = useState(true)
  const [uiEvents, setUiEvents] = useState<string[]>([])

  const [eventTypes, setEventTypes] = useState<{ code: string; label: string }[]>([])
  const [discordEvents, setDiscordEvents] = useState<string[]>([])
  const [telegramEvents, setTelegramEvents] = useState<string[]>([])

  const [baseline, setBaseline] = useState('')
  const currentSig = notifSignature({
    uiEnabled, uiEvents,
    discordEnabled, discordWebhook, telegramEnabled, telegramToken, telegramChatId, discordEvents, telegramEvents,
    quitarDiscord, quitarTelegram,
  })
  const dirty = baseline !== '' && currentSig !== baseline
  const dirtyRef = useRef(false)
  dirtyRef.current = dirty
  useEffect(() => {
    setUnsavedGuard(() => dirtyRef.current)
    return () => setUnsavedGuard(null)
  }, [])

  const saveRef = useRef<() => void>(() => {})
  saveRef.current = () => { void handleSave() }
  const stableSave = useRef(() => saveRef.current()).current
  useEffect(() => {
    onExposeSave({ dirty, saving, onSave: stableSave, label: 'Guardar notificaciones' })
  }, [dirty, saving, onExposeSave, stableSave])
  useEffect(() => () => onExposeSave(null), [onExposeSave])

  useEffect(() => {
    fetchSettings()
      .then(s => {
        setSettings(s)
        setUiEnabled(s.notify_ui_enabled)
        setUiEvents(s.notify_ui_events ?? [])
        setDiscordEnabled(s.notify_discord_enabled)
        setTelegramEnabled(s.notify_telegram_enabled)
        setTelegramChatId(s.notify_telegram_chat_id ?? '')
        setEventTypes(s.notify_event_types ?? [])
        setDiscordEvents(s.notify_discord_events ?? [])
        setTelegramEvents(s.notify_telegram_events ?? [])
        setBaseline(notifSignature({
          uiEnabled: s.notify_ui_enabled, uiEvents: s.notify_ui_events ?? [],
          discordEnabled: s.notify_discord_enabled, telegramEnabled: s.notify_telegram_enabled,
          telegramChatId: s.notify_telegram_chat_id ?? '', discordEvents: s.notify_discord_events ?? [],
          telegramEvents: s.notify_telegram_events ?? [],
        }))
      })
      .catch(() => setMsg({ ok: false, text: 'Error cargando configuración' }))
      .finally(() => setLoading(false))
  }, [])

  function toggleEvent(setter: React.Dispatch<React.SetStateAction<string[]>>, code: string, checked: boolean) {
    setter(prev => (checked ? [...new Set([...prev, code])] : prev.filter(c => c !== code)))
  }

  async function handleSave() {
    setSaving(true)
    setMsg(null)
    try {
      const payload: Parameters<typeof updateSettings>[0] = {
        notify_ui_enabled: uiEnabled,
        notify_ui_events: uiEvents,
        notify_discord_enabled: discordEnabled,
        notify_telegram_enabled: telegramEnabled,
        notify_telegram_chat_id: telegramChatId.trim(),
        notify_discord_events: discordEvents,
        notify_telegram_events: telegramEvents,
      }
      if (discordWebhook.trim()) payload.notify_discord_webhook_url = discordWebhook.trim()
      else if (quitarDiscord) payload.clear = ['notify_discord_webhook_url']
      if (telegramToken.trim()) payload.notify_telegram_bot_token = telegramToken.trim()
      else if (quitarTelegram) payload.clear = [...(payload.clear ?? []), 'notify_telegram_bot_token']
      const updated = await updateSettings(payload)
      setSettings(updated)
      setUiEvents(updated.notify_ui_events ?? [])
      setDiscordEvents(updated.notify_discord_events ?? [])
      setTelegramEvents(updated.notify_telegram_events ?? [])
      setDiscordWebhook('')
      setTelegramToken('')
      setQuitarDiscord(false)
      setQuitarTelegram(false)
      setBaseline(notifSignature({
        uiEnabled: updated.notify_ui_enabled, uiEvents: updated.notify_ui_events ?? [],
        discordEnabled: updated.notify_discord_enabled, telegramEnabled: updated.notify_telegram_enabled,
        telegramChatId: updated.notify_telegram_chat_id ?? '', discordEvents: updated.notify_discord_events ?? [],
        telegramEvents: updated.notify_telegram_events ?? [],
      }))
      setMsg({ ok: true, text: '✓ Notificaciones guardadas' })
    } catch (e: unknown) {
      setMsg({ ok: false, text: `✗ ${e instanceof Error ? e.message : String(e)}` })
    } finally {
      setSaving(false)
    }
  }

  async function handleTestDiscord() {
    setTestingDiscord(true)
    try {
      const params: { webhook_url?: string } = {}
      if (discordWebhook.trim()) params.webhook_url = discordWebhook.trim()
      anunciarResultado(await testDiscordNotification(params))
    } catch {
      anunciarResultado({ ok: false, service: 'discord', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setTestingDiscord(false)
    }
  }

  async function handleTestTelegram() {
    setTestingTelegram(true)
    try {
      const params: { bot_token?: string; chat_id?: string } = {}
      if (telegramToken.trim()) params.bot_token = telegramToken.trim()
      if (telegramChatId.trim()) params.chat_id = telegramChatId.trim()
      anunciarResultado(await testTelegramNotification(params))
    } catch {
      anunciarResultado({ ok: false, service: 'telegram', status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setTestingTelegram(false)
    }
  }

  // El resultado de la prueba va al hueco de la fila de pestañas, como el
  // resto de mensajes de esta pantalla, en vez de aparecer junto al botón.
  const textoResultado = (result: IntegrationTestResult): string =>
    result.ok ? 'Notificación de prueba enviada'
      : result.status === 'not_configured' ? 'Sin configurar'
      : result.status === 'invalid_key' ? 'Credenciales inválidas'
      : result.status === 'invalid_chat_id' ? 'Chat ID inválido'
      : result.status === 'timeout' ? 'Se agotó el tiempo de espera'
      : result.message

  const anunciarResultado = useCallback((result: IntegrationTestResult | null) => {
    if (!result) return
    setMsg({
      ok: result.ok,
      text: `${result.service === 'telegram' ? 'Telegram' : 'Discord'}: ${textoResultado(result)}`,
    })
  }, [setMsg])

  if (loading) return <p style={{ padding: 20, color: 'var(--text-muted)', fontSize: 13 }}>Cargando…</p>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 16, alignItems: 'stretch' }}>
      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="emu" size={20} /> Notificaciones UI
        </h3>
        <label className="checkbox-label" style={{ marginBottom: 12 }}>
          <input type="checkbox" checked={uiEnabled} onChange={e => setUiEnabled(e.target.checked)} /> Mostrar avisos en la campana
        </label>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 0 }}>
          Avisos dentro de la propia app (icono de la campana en la barra superior).
        </p>
        <EventPicker
          title="Qué mostrar en la campana"
          eventTypes={eventTypes}
          selected={uiEvents}
          disabled={!uiEnabled}
          onToggle={(code, checked) => toggleEvent(setUiEvents, code, checked)}
        />
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="discord" size={20} /> Discord
        </h3>
        <label className="checkbox-label" style={{ marginBottom: 12, display: 'block' }}>
          <input type="checkbox" checked={discordEnabled} onChange={e => setDiscordEnabled(e.target.checked)} /> Activar notificaciones por Discord
        </label>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Webhook URL</label>
          <div style={{ fontSize: 13, marginBottom: 6 }}>
            {settings?.notify_discord_webhook_configured
              ? <><span style={{ color: 'var(--color-available)', display: 'inline-flex', alignItems: 'center', gap: 5 }}><CheckStatusIcon status="ok" /> Configurado</span>{settings.notify_discord_webhook_masked && <code style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)' }}>{settings.notify_discord_webhook_masked}</code>}</>
              : <span style={{ color: 'var(--color-error)' }}>✗ No configurado</span>}
          </div>
          <input
            type="password"
            className="form-input"
            value={discordWebhook}
            onChange={e => { setDiscordWebhook(e.target.value); setQuitarDiscord(false) }}
            placeholder={quitarDiscord ? 'Se quitará al guardar' : 'https://discord.com/api/webhooks/… (dejar vacío para mantener el actual)'}
            autoComplete="new-password"
          />
          {settings?.notify_discord_webhook_configured && !discordWebhook && (
            <button type="button" className="btn btn-secondary btn-sm" style={{ marginTop: 6 }} onClick={() => setQuitarDiscord(q => !q)}>
              {quitarDiscord ? 'No quitarlo' : 'Quitar el webhook'}
            </button>
          )}
        </div>
        <button className="btn btn-secondary btn-sm" onClick={handleTestDiscord} disabled={testingDiscord} type="button">
          {testingDiscord ? 'Enviando…' : 'Probar notificación'}
        </button>
        
        <EventPicker
          title="Qué notificar por Discord"
          eventTypes={eventTypes}
          selected={discordEvents}
          disabled={!discordEnabled}
          onToggle={(code, checked) => toggleEvent(setDiscordEvents, code, checked)}
        />
      </div>

      <div className="placeholder-card">
        <h3 style={{ marginTop: 0, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ServiceIcon type="telegram" size={20} /> Telegram
        </h3>
        <label className="checkbox-label" style={{ marginBottom: 12, display: 'block' }}>
          <input type="checkbox" checked={telegramEnabled} onChange={e => setTelegramEnabled(e.target.checked)} /> Activar notificaciones por Telegram
        </label>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Bot token</label>
          <div style={{ fontSize: 13, marginBottom: 6 }}>
            {settings?.notify_telegram_bot_token_configured
              ? <><span style={{ color: 'var(--color-available)', display: 'inline-flex', alignItems: 'center', gap: 5 }}><CheckStatusIcon status="ok" /> Configurado</span>{settings.notify_telegram_bot_token_masked && <code style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-muted)' }}>{settings.notify_telegram_bot_token_masked}</code>}</>
              : <span style={{ color: 'var(--color-error)' }}>✗ No configurado</span>}
          </div>
          <input
            type="password"
            className="form-input"
            value={telegramToken}
            onChange={e => { setTelegramToken(e.target.value); setQuitarTelegram(false) }}
            placeholder={quitarTelegram ? 'Se quitará al guardar' : '123456:ABC-DEF… (dejar vacío para mantener el actual)'}
            autoComplete="new-password"
          />
          {settings?.notify_telegram_bot_token_configured && !telegramToken && (
            <button type="button" className="btn btn-secondary btn-sm" style={{ marginTop: 6 }} onClick={() => setQuitarTelegram(q => !q)}>
              {quitarTelegram ? 'No quitarlo' : 'Quitar el token'}
            </button>
          )}
        </div>
        <div className="form-group" style={{ marginBottom: 12 }}>
          <label className="form-label">Chat ID</label>
          <input className="form-input" value={telegramChatId} onChange={e => setTelegramChatId(e.target.value)} placeholder="-100123456789" />
        </div>
        <button className="btn btn-secondary btn-sm" onClick={handleTestTelegram} disabled={testingTelegram} type="button">
          {testingTelegram ? 'Enviando…' : 'Probar notificación'}
        </button>
        
        <EventPicker
          title="Qué notificar por Telegram"
          eventTypes={eventTypes}
          selected={telegramEvents}
          disabled={!telegramEnabled}
          onToggle={(code, checked) => toggleEvent(setTelegramEvents, code, checked)}
        />
      </div>
      </div>
    </div>
  )
}

// ---------- Main page ----------
export function SettingsPage() {
  const [tab, setTab] = useState<Tab>('config')
  const [status, setStatus] = useState<MaintenanceStatus | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveAction, setSaveAction] = useState<SaveExpose | null>(null)

  const loadStatus = useCallback(async () => {
    try {
      const s = await getMaintenanceStatus()
      setStatus(s)
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => { loadStatus() }, [loadStatus])

  // Dos mensajes a la vez, no uno: el permanente describe un estado que sigue
  // siendo cierto (hay una versión nueva) y el pasajero, algo que acaba de
  // ocurrir (has guardado). El pasajero se pone delante unos segundos y luego
  // vuelve a verse el permanente, en vez de borrarlo para siempre.
  const [msgPermanente, setMsgPermanente] = useState<SettingsMsg>(null)
  const [msgPasajero, setMsgPasajero] = useState<SettingsMsg>(null)
  const msgTimer = useRef<number | null>(null)

  const showMessage = useCallback((ok: boolean, text: string, opciones?: OpcionesMensaje) => {
    const tono: TonoMensaje = opciones?.tono ?? (ok ? 'ok' : 'error')
    if (opciones?.permanente) {
      setMsgPermanente({ text, tono, permanente: true })
      return
    }
    if (opciones?.borrarPermanente) setMsgPermanente(null)
    // El temporizador anterior se cancela: dos avisos seguidos no pueden dejar
    // que el primero apague al segundo.
    if (msgTimer.current) window.clearTimeout(msgTimer.current)
    setMsgPasajero({ text, tono })
    msgTimer.current = window.setTimeout(() => setMsgPasajero(null), 5000)
  }, [])
  useEffect(() => () => { if (msgTimer.current) window.clearTimeout(msgTimer.current) }, [])
  const msg = msgPasajero ?? msgPermanente

  const tabs: { key: Tab; label: string }[] = [
    { key: 'config', label: 'Configuración' },
    { key: 'notifications', label: 'Notificaciones' },
    { key: 'diagnostics', label: 'Diagnóstico' },
    { key: 'backup', label: 'Backup' },
  ]

  return (
    // Llena el alto de la página y no más: la cabecera y las pestañas se
    // quedan fijas arriba, y el contenido de la pestaña activa se desplaza
    // por dentro (el div de más abajo) cuando no cabe entero — las cuatro
    // pestañas se comportan igual, Configuración incluida.
    <div style={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div className="page-header" style={{ flexShrink: 0 }}>
        <div>
          <div className="page-title">Configuración</div>
          <div className="page-subtitle">Ajustes, diagnóstico y backup</div>
        </div>
        {saveAction && (
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            {saveAction.dirty && <span style={{ fontSize: 12, color: 'var(--color-warning)' }}>Cambios sin guardar</span>}
            <button
              className={`btn btn-primary btn-sm${saveAction.dirty ? ' btn-unsaved' : ''}`}
              onClick={saveAction.onSave}
              disabled={saveAction.saving}
            >
              {saveAction.saving ? 'Guardando…' : saveAction.label}
            </button>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 2, marginBottom: 20, borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        {tabs.map(t => (
          <button
            key={t.key}
            className={`settings-tab${tab === t.key ? ' active' : ''}`}
            onClick={() => { if (t.key !== tab) guardedLeave(() => { setTab(t.key); setMsgPasajero(null) }) }}
          >
            {t.label}
          </button>
        ))}
        <SettingsMessageSlot
          msg={msg ?? (loadError
            ? { text: `No se pudo cargar el estado de mantenimiento: ${loadError}`, tono: 'error' }
            : null)}
        />
      </div>

      {/* overflowY auto y no hidden: todas las pestañas pueden crecer más
          que la pantalla y necesitan poder desplazarse por dentro. */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        <SettingsMessageContext.Provider value={showMessage}>
          {tab === 'config' && <ConfigTab onExposeSave={setSaveAction} />}
          {tab === 'notifications' && <NotificationsTab onExposeSave={setSaveAction} />}
          {tab === 'diagnostics' && <DiagnosticsTab status={status} onRefresh={loadStatus} />}
          {tab === 'backup' && <BackupTab status={status} onRefresh={loadStatus} />}
        </SettingsMessageContext.Provider>
      </div>
    </div>
  )
}
