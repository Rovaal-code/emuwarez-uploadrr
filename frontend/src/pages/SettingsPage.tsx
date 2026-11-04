import { useState, useEffect, useCallback, useRef } from 'react'
import { guardedLeave } from '../utils/unsavedGuard'
import { getMaintenanceStatus, type MaintenanceStatus } from '../api/maintenance'
import { useAlSalir } from '../context/SeccionVisible'
import {
  SettingsMessageContext, SettingsMessageSlot,
  type SettingsMsg, type TonoMensaje, type OpcionesMensaje,
} from './ajustes/mensajes'
import type { SaveExpose } from './ajustes/tipos'
import { ConfigTab } from './ajustes/ConfigTab'
import { NotificationsTab } from './ajustes/NotificationsTab'
import { DiagnosticsTab } from './ajustes/DiagnosticsTab'
import { BackupTab } from './ajustes/BackupTab'

type Tab = 'config' | 'notifications' | 'diagnostics' | 'backup'

// ---------- Main page ----------
export function SettingsPage() {
  const [tab, setTab] = useState<Tab>('config')
  const [status, setStatus] = useState<MaintenanceStatus | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveAction, setSaveAction] = useState<SaveExpose | null>(null)
  // Al salir de la sección se descartan los formularios: ya se ha confirmado, y la página sigue montada,
  // así que sin esto seguirían con cambios y preguntarían al navegar desde cualquier otra sección.
  const [reinicio, setReinicio] = useState(0)
  useAlSalir(() => setReinicio(n => n + 1))

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
    <div className="aj-marco">
      <div className="page-header aj-no-encoge">
        <div>
          <div className="page-title">Configuración</div>
          <div className="page-subtitle">Ajustes, diagnóstico y backup</div>
        </div>
        {saveAction && (
          <div className="aj-flex-c-12 aj-wrap">
            {saveAction.dirty && <span className="aj-aviso-cambios">Cambios sin guardar</span>}
            <button
              className={`btn btn-primary btn-sm${saveAction.dirty ? ' btn-unsaved' : ''}`}
              onClick={saveAction.onSave}
              disabled={saveAction.saving || saveAction.deshabilitado}
            >
              {saveAction.saving ? 'Guardando…' : saveAction.label}
            </button>
          </div>
        )}
      </div>

      <div className="aj-tabs">
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
      <div className="aj-cuerpo">
        <SettingsMessageContext.Provider key={reinicio} value={showMessage}>
          {tab === 'config' && <ConfigTab />}
          {tab === 'notifications' && <NotificationsTab onExposeSave={setSaveAction} />}
          {tab === 'diagnostics' && <DiagnosticsTab status={status} onRefresh={loadStatus} />}
          {tab === 'backup' && <BackupTab status={status} onRefresh={loadStatus} />}
        </SettingsMessageContext.Provider>
      </div>
    </div>
  )
}
