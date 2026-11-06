import { useState, useEffect, useCallback, useRef } from 'react'
import { useUnsavedGuard } from '../../utils/unsavedGuard'
import { fetchSettings, updateSettings, type SettingsData } from '../../api/settings'
import { type IntegrationTestResult } from '../../api/integrationTests'
import { testDiscordNotification, testTelegramNotification } from '../../api/notifications'
import { ServiceIcon } from '../../components/ServiceIcon'
import { InfoIcon } from '../../components/InfoIcon'
import { MODOS_AVISO_LOTE, MODO_AVISO_LOTE_POR_DEFECTO, conAvisoDeLote, type ModoAvisoLote } from '../../utils/lote'
import { useSettingsMessageAdapter } from './mensajes'
import { Campo, EstadoSecreto, Interruptor } from './Campo'
import { CabeceraTarjeta } from './CabeceraTarjeta'
import type { SaveExpose } from './tipos'

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
    <fieldset className={disabled ? 'aj-grupo-eventos aj-desactivado' : 'aj-grupo-eventos'} disabled={disabled}>
      <legend className="aj-titulo-grupo">{title}</legend>
      <div className="aj-col-6">
        {eventTypes.map(ev => (
          <label key={ev.code} className="checkbox-label aj-fs-13">
            <input
              type="checkbox"
              checked={selected.includes(ev.code)}
              disabled={disabled}
              onChange={e => onToggle(ev.code, e.target.checked)}
            /> {ev.label}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function notifSignature(v: {
  uiEnabled: boolean; uiEvents: string[]
  discordEnabled: boolean; discordWebhook?: string; telegramEnabled: boolean
  telegramToken?: string; telegramChatId: string; discordEvents: string[]; telegramEvents: string[]
  quitarDiscord?: boolean; quitarTelegram?: boolean; loteModo: ModoAvisoLote
}): string {
  return JSON.stringify([
    v.uiEnabled, v.uiEvents,
    v.discordEnabled, v.discordWebhook ?? '', v.telegramEnabled, v.telegramToken ?? '',
    v.telegramChatId, v.discordEvents, v.telegramEvents,
    v.quitarDiscord ?? false, v.quitarTelegram ?? false, v.loteModo,
  ])
}

// ---------- Notifications tab ----------
export function NotificationsTab({ onExposeSave }: { onExposeSave: (a: SaveExpose | null) => void }) {
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
  // Las subidas de un lote: una notificación por subida o una sola cuando termina el lote.
  const [loteModo, setLoteModo] = useState<ModoAvisoLote>(MODO_AVISO_LOTE_POR_DEFECTO)

  const [baseline, setBaseline] = useState('')
  const currentSig = notifSignature({
    uiEnabled, uiEvents,
    discordEnabled, discordWebhook, telegramEnabled, telegramToken, telegramChatId, discordEvents, telegramEvents,
    quitarDiscord, quitarTelegram, loteModo,
  })
  const dirty = baseline !== '' && currentSig !== baseline
  useUnsavedGuard('notificaciones', dirty)

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
        setLoteModo(s.notify_lote_modo ?? MODO_AVISO_LOTE_POR_DEFECTO)
        setBaseline(notifSignature({
          uiEnabled: s.notify_ui_enabled, uiEvents: s.notify_ui_events ?? [],
          discordEnabled: s.notify_discord_enabled, telegramEnabled: s.notify_telegram_enabled,
          telegramChatId: s.notify_telegram_chat_id ?? '', discordEvents: s.notify_discord_events ?? [],
          telegramEvents: s.notify_telegram_events ?? [],
          loteModo: s.notify_lote_modo ?? MODO_AVISO_LOTE_POR_DEFECTO,
        }))
      })
      .catch(() => setMsg({ ok: false, text: 'Error cargando configuración' }))
      .finally(() => setLoading(false))
  }, [setMsg])

  function toggleEvent(setter: React.Dispatch<React.SetStateAction<string[]>>, code: string, checked: boolean) {
    setter(prev => (checked ? [...new Set([...prev, code])] : prev.filter(c => c !== code)))
  }

  // Al pasar a «Una por lote», cada canal que avisaba de las subidas avisa también del lote: si no, uno que guardó su
  // selección antes de existir ese aviso se quedaría sin ninguno de las subidas de un lote.
  function cambiarModoLote(modo: ModoAvisoLote) {
    setLoteModo(modo)
    if (modo !== 'por_lote') return
    setUiEvents(conAvisoDeLote)
    setDiscordEvents(conAvisoDeLote)
    setTelegramEvents(conAvisoDeLote)
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
        notify_lote_modo: loteModo,
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
      setLoteModo(updated.notify_lote_modo ?? MODO_AVISO_LOTE_POR_DEFECTO)
      setDiscordWebhook('')
      setTelegramToken('')
      setQuitarDiscord(false)
      setQuitarTelegram(false)
      setBaseline(notifSignature({
        uiEnabled: updated.notify_ui_enabled, uiEvents: updated.notify_ui_events ?? [],
        discordEnabled: updated.notify_discord_enabled, telegramEnabled: updated.notify_telegram_enabled,
        telegramChatId: updated.notify_telegram_chat_id ?? '', discordEvents: updated.notify_discord_events ?? [],
        telegramEvents: updated.notify_telegram_events ?? [],
        loteModo: updated.notify_lote_modo ?? MODO_AVISO_LOTE_POR_DEFECTO,
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

  if (loading) return <p className="aj-cargando">Cargando…</p>

  const estadoWebhook = settings?.notify_discord_webhook_configured
  const estadoToken = settings?.notify_telegram_bot_token_configured

  return (
    <div className="aj-col-16">
      <div className="aj-rejilla-4">
      <div className="placeholder-card">
        <CabeceraTarjeta
          icono={<ServiceIcon type="emu" size={20} />}
          titulo="Notificaciones UI"
          descripcion="Avisos dentro de la propia app (icono de la campana en la barra superior)."
        />
        <Interruptor etiqueta="Mostrar avisos en la campana" marcado={uiEnabled} onCambio={setUiEnabled} />
        <EventPicker
          title="Qué mostrar en la campana"
          eventTypes={eventTypes}
          selected={uiEvents}
          disabled={!uiEnabled}
          onToggle={(code, checked) => toggleEvent(setUiEvents, code, checked)}
        />
      </div>

      <div className="placeholder-card">
        <CabeceraTarjeta
          icono={<ServiceIcon type="discord" size={20} />}
          titulo="Discord"
          lateral={<EstadoSecreto configurado={estadoWebhook} genero="m" />}
        />
        <Interruptor etiqueta="Activar notificaciones por Discord" marcado={discordEnabled} onCambio={setDiscordEnabled} />
        <Campo
          etiqueta="Webhook URL"
          ayuda={estadoWebhook && settings?.notify_discord_webhook_masked ? <>Guardado: <code>{settings.notify_discord_webhook_masked}</code></> : undefined}
        >
          {c => (
            <>
              <input
                {...c}
                type="password"
                className="form-input"
                value={discordWebhook}
                onChange={e => { setDiscordWebhook(e.target.value); setQuitarDiscord(false) }}
                placeholder={quitarDiscord ? 'Se quitará al guardar' : 'https://discord.com/api/webhooks/… (dejar vacío para mantener el actual)'}
                autoComplete="new-password"
              />
              {estadoWebhook && !discordWebhook && (
                <button type="button" className="btn btn-secondary btn-sm aj-self-start" onClick={() => setQuitarDiscord(q => !q)}>
                  {quitarDiscord ? 'No quitarlo' : 'Quitar el webhook'}
                </button>
              )}
            </>
          )}
        </Campo>
        <div className="aj-acciones">
          <button className="btn btn-secondary btn-sm" onClick={handleTestDiscord} disabled={testingDiscord} type="button">
            {testingDiscord ? 'Enviando…' : 'Probar notificación'}
          </button>
        </div>
        <EventPicker
          title="Qué notificar por Discord"
          eventTypes={eventTypes}
          selected={discordEvents}
          disabled={!discordEnabled}
          onToggle={(code, checked) => toggleEvent(setDiscordEvents, code, checked)}
        />
      </div>

      <div className="placeholder-card">
        <CabeceraTarjeta
          icono={<ServiceIcon type="telegram" size={20} />}
          titulo="Telegram"
          lateral={<EstadoSecreto configurado={estadoToken} genero="m" />}
        />
        <Interruptor etiqueta="Activar notificaciones por Telegram" marcado={telegramEnabled} onCambio={setTelegramEnabled} />
        <Campo
          etiqueta="Bot token"
          ayuda={estadoToken && settings?.notify_telegram_bot_token_masked ? <>Guardado: <code>{settings.notify_telegram_bot_token_masked}</code></> : undefined}
        >
          {c => (
            <>
              <input
                {...c}
                type="password"
                className="form-input"
                value={telegramToken}
                onChange={e => { setTelegramToken(e.target.value); setQuitarTelegram(false) }}
                placeholder={quitarTelegram ? 'Se quitará al guardar' : '123456:ABC-DEF… (dejar vacío para mantener el actual)'}
                autoComplete="new-password"
              />
              {estadoToken && !telegramToken && (
                <button type="button" className="btn btn-secondary btn-sm aj-self-start" onClick={() => setQuitarTelegram(q => !q)}>
                  {quitarTelegram ? 'No quitarlo' : 'Quitar el token'}
                </button>
              )}
            </>
          )}
        </Campo>
        <Campo etiqueta="Chat ID">
          {c => <input {...c} className="form-input" value={telegramChatId} onChange={e => setTelegramChatId(e.target.value)} placeholder="-100123456789" autoComplete="off" />}
        </Campo>
        <div className="aj-acciones">
          <button className="btn btn-secondary btn-sm" onClick={handleTestTelegram} disabled={testingTelegram} type="button">
            {testingTelegram ? 'Enviando…' : 'Probar notificación'}
          </button>
        </div>
        <EventPicker
          title="Qué notificar por Telegram"
          eventTypes={eventTypes}
          selected={telegramEvents}
          disabled={!telegramEnabled}
          onToggle={(code, checked) => toggleEvent(setTelegramEvents, code, checked)}
        />
      </div>

      <div className="placeholder-card">
        <CabeceraTarjeta
          icono={(
            <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M12 3 3 7.5l9 4.5 9-4.5L12 3z" /><path d="m3 12 9 4.5 9-4.5" /><path d="m3 16.5 9 4.5 9-4.5" />
            </svg>
          )}
          titulo="Subidas por lotes"
        />
        <Campo
          id="aviso-lote"
          etiqueta="Notificaciones de un lote"
          info={<InfoIcon text="Cómo avisan las subidas lanzadas juntas (un lote o una tanda del asistente). Una por subida: cada una avisa al completarse o fallar, como una suelta. Una por lote: no avisa ninguna por separado y, cuando termina la última, llega un solo aviso con el resumen (cuántas se completaron, fallaron o se cancelaron). Si luego reintentas las fallidas, al terminar los reintentos llega otro resumen. Las subidas sueltas avisan siempre una a una." />}
          ayuda={loteModo === 'por_lote'
            ? 'El aviso del lote sale por los canales que tengan marcado «Lote de subidas terminado».'
            : 'Cada subida de un lote avisa por su cuenta, con «Subida completada» o «Subida fallida».'}
        >
          {c => (
            <select {...c} className="form-input form-select" value={loteModo}
                    onChange={e => cambiarModoLote(e.target.value as ModoAvisoLote)}>
              {MODOS_AVISO_LOTE.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          )}
        </Campo>
      </div>
      </div>
    </div>
  )
}
