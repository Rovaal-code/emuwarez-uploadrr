import { useState, useEffect } from 'react'
import { useUnsavedGuard } from '../../../utils/unsavedGuard'
import { fetchSettings, updateSettings, type SettingsData } from '../../../api/settings'
import { usePerfilEmu } from '../../../context/PerfilEmuContext'
import { isValidHttpUrl } from '../../../utils/validation'
import { MODO_PISTAS_POR_DEFECTO, normalizarModo, type ModoPistas } from '../../../utils/modoPistas'
import { useSettingsMessageAdapter } from '../mensajes'
import { enfocarPrimerError } from '../Campo'

// El estado del formulario de la pestaña Configuración, compartido por todas sus tarjetas: se carga, se
// compara con lo cargado para saber cuántos campos han cambiado y se guarda de una vez desde la barra de
// guardado. Lo que solo toca una tarjeta (pruebas de conexión, el modal de claves) vive en esa tarjeta.

// Los valores del formulario, uno por campo, serializados para comparar el estado actual con el cargado.
function configSignature(v: {
  tags: string[]; providerOrder: string[]; region: string
  emuUsername: string; ignoreSpecials: boolean; sourceEngine: boolean; addLogo: boolean; capturasPorCapitulo: boolean; modoDePistas: ModoPistas; sinCopiasReflink: boolean; sincronizarAlVolver: boolean
  recentLimit: number; uploadMaxConcurrent: number; qbitUrl: string; qbitTag: string; qbitUser: string
  imgEnabled: string[]; allowedRoots: string
  newKey?: string; newEmuKey?: string; qbitPass?: string; qbitQui?: string; quitarQui?: boolean; quitarQbitPass?: boolean
}): Record<string, string> {
  const campos: Record<string, unknown> = {
    tags: v.tags, providerOrder: v.providerOrder, region: v.region, emuUsername: v.emuUsername,
    ignoreSpecials: v.ignoreSpecials, sourceEngine: v.sourceEngine, addLogo: v.addLogo, capturasPorCapitulo: v.capturasPorCapitulo, modoDePistas: v.modoDePistas, sinCopiasReflink: v.sinCopiasReflink, sincronizarAlVolver: v.sincronizarAlVolver, recentLimit: v.recentLimit, uploadMaxConcurrent: v.uploadMaxConcurrent, qbitUrl: v.qbitUrl, qbitTag: v.qbitTag, qbitUser: v.qbitUser, imgEnabled: v.imgEnabled, allowedRoots: v.allowedRoots,
    newKey: v.newKey ?? '', newEmuKey: v.newEmuKey ?? '', qbitPass: v.qbitPass ?? '', qbitQui: v.qbitQui ?? '', quitarQui: v.quitarQui ?? false, quitarQbitPass: v.quitarQbitPass ?? false,
  }
  return Object.fromEntries(Object.entries(campos).map(([k, x]) => [k, JSON.stringify(x)]))
}

const ERROR_URL_QBIT = 'La URL de qBittorrent debe empezar por http:// o https:// e incluir un host válido'
const ERROR_URL_QUI = 'La URL del proxy de qui debe empezar por http:// o https:// e incluir un host válido'

// Cuántos campos difieren de lo cargado.
function contarCambios(base: Record<string, string>, actual: Record<string, string>): number {
  return Object.keys(actual).filter(k => actual[k] !== base[k]).length
}

export function useConfigForm() {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  // Si la carga falla no se guarda: el formulario tiene valores por defecto, no los ajustes reales.
  const [errorCarga, setErrorCarga] = useState<string | null>(null)
  const [intento, setIntento] = useState(0)
  const [saving, setSaving] = useState(false)
  const setMsg = useSettingsMessageAdapter()
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
  // Internal Source Tool: apagada por defecto, sigue en desarrollo.
  const [sourceEngine, setSourceEngine] = useState(false)
  // El logo del contenido en la descripción: se sube por defecto.
  const [addLogo, setAddLogo] = useState(true)
  // Capturas de un pack: solo del primer capítulo por defecto.
  const [capturasPorCapitulo, setCapturasPorCapitulo] = useState(false)
  // Reordenar pistas: apagado por defecto, reescribe el contenedor entero.
  const [modoDePistas, setModoDePistas] = useState<ModoPistas>(MODO_PISTAS_POR_DEFECTO)
  // Copias por reflink de un archivo compartido: se hacen por defecto.
  const [sinCopiasReflink, setSinCopiasReflink] = useState(false)
  // Sincronizar una instancia en cuanto vuelve a responder: activado por defecto.
  const [sincronizarAlVolver, setSincronizarAlVolver] = useState(true)
  const [recentLimit, setRecentLimit] = useState(100)
  const [uploadMaxConcurrent, setUploadMaxConcurrent] = useState(1)
  const [qbitUrl, setQbitUrl] = useState('')
  const [qbitTag, setQbitTag] = useState('')
  const [qbitUser, setQbitUser] = useState('')
  const [qbitPass, setQbitPass] = useState('')
  const [quitarQbitPass, setQuitarQbitPass] = useState(false)
  // El proxy de qui es un secreto como la contraseña: no se carga, y quitarlo se pide aparte.
  const [qbitQui, setQbitQui] = useState('')
  const [quitarQui, setQuitarQui] = useState(false)
  // Image hosts
  const [imgEnabled, setImgEnabled] = useState<string[]>([])
  // Uploadrr sandboxing: folder(s) where THIS container reaches the media,
  // comma-separated. Empty means real uploads fail closed until it's set.
  const [allowedRoots, setAllowedRoots] = useState('')

  // Unsaved-changes tracking: compare current form values to the loaded ones.
  const [baseline, setBaseline] = useState<Record<string, string> | null>(null)
  // Un grupo escrito sin pulsar «Añadir» también se guarda.
  const borrador = nuevoTag.trim()
  const tagsAGuardar = borrador && !tags.includes(borrador) ? [...tags, borrador] : tags
  const currentSig = configSignature({
    tags: tagsAGuardar, providerOrder, region, emuUsername,
    ignoreSpecials, sourceEngine, addLogo, capturasPorCapitulo, modoDePistas, sinCopiasReflink, sincronizarAlVolver, recentLimit, uploadMaxConcurrent, qbitUrl, qbitTag, qbitUser, imgEnabled, allowedRoots,
    newKey, newEmuKey, qbitPass, qbitQui, quitarQui, quitarQbitPass,
  })
  const cambios = baseline ? contarCambios(baseline, currentSig) : 0
  // Validación en el sitio: un campo con una URL mal escrita lo dice al salir de él o al intentar guardar.
  const [tocados, setTocados] = useState<ReadonlySet<'qbitUrl' | 'qbitQui'>>(new Set())
  const marcarTocado = (campo: 'qbitUrl' | 'qbitQui') => setTocados(t => (t.has(campo) ? t : new Set(t).add(campo)))
  const errores = {
    qbitUrl: tocados.has('qbitUrl') && qbitUrl.trim() && !isValidHttpUrl(qbitUrl) ? ERROR_URL_QBIT : null,
    qbitQui: tocados.has('qbitQui') && qbitQui.trim() && !isValidHttpUrl(qbitQui) ? ERROR_URL_QUI : null,
  }
  const dirty = cambios > 0
  useUnsavedGuard('config', dirty)

  useEffect(() => {
    let activo = true
    fetchSettings()
      .then(s => {
        if (!activo) return
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
        setSinCopiasReflink(s.remux_no_reflink_copies ?? false)
        setSincronizarAlVolver(s.sincronizar_al_volver_instancia ?? true)
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
          ignoreSpecials: s.series_ignore_specials ?? true, sourceEngine: s.source_engine_enabled ?? false, addLogo: s.emu_add_logo ?? true, capturasPorCapitulo: s.emu_per_episode_screens ?? false, modoDePistas: normalizarModo(s.remux_track_mode), sinCopiasReflink: s.remux_no_reflink_copies ?? false, sincronizarAlVolver: s.sincronizar_al_volver_instancia ?? true,
          recentLimit: s.recent_activity_limit ?? 100,
          uploadMaxConcurrent: s.upload_max_concurrent ?? 1,
          qbitUrl: s.qbit_url ?? '', qbitTag: s.qbit_tag ?? '', qbitUser: s.qbit_username ?? '',
          imgEnabled: s.image_hosts_enabled ?? [],
          allowedRoots: (s.uploadrr_allowed_roots ?? []).join(', '),
        }))
      })
      .catch((e: unknown) => {
        if (!activo) return
        // Una carga anterior buena no se queda: Guardar enviaría valores que ya no son los del servidor.
        setSettings(null)
        setErrorCarga((e instanceof Error ? e.message : String(e)) || 'error desconocido')
      })
      .finally(() => { if (activo) setLoading(false) })
    // Una lectura que llega tarde no pisa a la más reciente.
    return () => { activo = false }
  }, [intento])

  // Vuelve a lo guardado: se lee otra vez, sin pasar por la pantalla de carga para no desmontar el formulario.
  function descartar() {
    setTocados(new Set())
    setNuevoTag('')
    setNewKey('')
    setNewEmuKey('')
    setQbitPass('')
    setQuitarQbitPass(false)
    setQbitQui('')
    setQuitarQui(false)
    setIntento(n => n + 1)
  }

  function reintentar() {
    setErrorCarga(null)
    setLoading(true)
    setIntento(n => n + 1)
  }

  async function handleSave() {
    if (!settings) return
    const urlMala = qbitUrl.trim() && !isValidHttpUrl(qbitUrl)
    const quiMala = qbitQui.trim() && !isValidHttpUrl(qbitQui)
    if (urlMala || quiMala) {
      setTocados(new Set(['qbitUrl', 'qbitQui']))
      setMsg({ ok: false, text: urlMala ? ERROR_URL_QBIT : ERROR_URL_QUI })
      enfocarPrimerError('.aj-config')
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
        remux_no_reflink_copies: sinCopiasReflink,
        sincronizar_al_volver_instancia: sincronizarAlVolver,
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
        ignoreSpecials: updated.series_ignore_specials ?? true, sourceEngine: updated.source_engine_enabled ?? false, addLogo: updated.emu_add_logo ?? true, capturasPorCapitulo: updated.emu_per_episode_screens ?? false, modoDePistas: normalizarModo(updated.remux_track_mode), sinCopiasReflink: updated.remux_no_reflink_copies ?? false, sincronizarAlVolver: updated.sincronizar_al_volver_instancia ?? true,
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
  return {
    settings, setSettings, loading, errorCarga, reintentar, descartar, saving, handleSave, cambios, errores, marcarTocado,
    tags, setTags, nuevoTag, setNuevoTag, borrador,
    providerOrder, setProviderOrder, region, setRegion,
    newKey, setNewKey, newEmuKey, setNewEmuKey, emuUsername, setEmuUsername,
    ignoreSpecials, setIgnoreSpecials, sourceEngine, setSourceEngine, addLogo, setAddLogo,
    capturasPorCapitulo, setCapturasPorCapitulo, modoDePistas, setModoDePistas,
    sinCopiasReflink, setSinCopiasReflink, sincronizarAlVolver, setSincronizarAlVolver, recentLimit, setRecentLimit,
    uploadMaxConcurrent, setUploadMaxConcurrent,
    qbitUrl, setQbitUrl, qbitTag, setQbitTag, qbitUser, setQbitUser, qbitPass, setQbitPass,
    quitarQbitPass, setQuitarQbitPass, qbitQui, setQbitQui, quitarQui, setQuitarQui,
    imgEnabled, setImgEnabled, allowedRoots, setAllowedRoots,
  }
}

export type ConfigForm = ReturnType<typeof useConfigForm>
