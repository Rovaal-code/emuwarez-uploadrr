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
import { BarraGuardado } from './ajustes/config/BarraGuardado'

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
  const listaPestanas = useRef<HTMLDivElement>(null)

  function elegirPestana(key: Tab) {
    if (key !== tab) guardedLeave(() => { setTab(key); setMsgPasajero(null) })
  }

  // Flechas, Inicio y Fin mueven el foco entre las pestañas; activar una es Intro o Espacio, como cualquier botón
  // (cambiar con cambios sin guardar abre una pregunta, así que no se activa al pasar).
  function alTeclearPestana(e: React.KeyboardEvent<HTMLDivElement>) {
    const botones = [...(listaPestanas.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]') ?? [])]
    const actual = botones.indexOf(document.activeElement as HTMLButtonElement)
    if (actual < 0) return
    const destino = e.key === 'ArrowRight' ? (actual + 1) % botones.length
      : e.key === 'ArrowLeft' ? (actual - 1 + botones.length) % botones.length
      : e.key === 'Home' ? 0
      : e.key === 'End' ? botones.length - 1
      : -1
    if (destino < 0) return
    e.preventDefault()
    botones[destino].focus()
  }

  return (
    // Llena el alto de la página y no más: la cabecera y las pestañas se
    // quedan fijas arriba, y el contenido de la pestaña activa se desplaza
    // por dentro (el div de más abajo) cuando no cabe entero — las cuatro
    // pestañas se comportan igual, Configuración incluida.
    <div className="aj-marco" data-tour="settings-content">
      <div className="page-header aj-no-encoge">
        <div>
          <div className="page-title">Configuración</div>
          <div className="page-subtitle">Ajustes, diagnóstico y backup</div>
        </div>
      </div>

      <div className="aj-tabs">
        <div className="aj-tabs__lista" role="tablist" aria-label="Secciones de Configuración" ref={listaPestanas} onKeyDown={alTeclearPestana}>
          {tabs.map(t => (
            <button
              key={t.key}
              id={`aj-pestana-${t.key}`}
              type="button"
              role="tab"
              aria-selected={tab === t.key}
              aria-controls="aj-panel"
              tabIndex={tab === t.key ? 0 : -1}
              className={`aj-tab${tab === t.key ? ' active' : ''}`}
              onClick={() => elegirPestana(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <SettingsMessageSlot
          msg={msg ?? (loadError
            ? { text: `No se pudo cargar el estado de mantenimiento: ${loadError}`, tono: 'error' }
            : null)}
        />
      </div>

      {/* overflowY auto y no hidden: todas las pestañas pueden crecer más
          que la pantalla y necesitan poder desplazarse por dentro. */}
      <div className="aj-cuerpo" id="aj-panel" role="tabpanel" aria-labelledby={`aj-pestana-${tab}`} tabIndex={-1}>
        <SettingsMessageContext.Provider key={reinicio} value={showMessage}>
          {tab === 'config' && <ConfigTab />}
          {tab === 'notifications' && <NotificationsTab onExposeSave={setSaveAction} />}
          {tab === 'diagnostics' && <DiagnosticsTab status={status} onRefresh={loadStatus} />}
          {tab === 'backup' && <BackupTab status={status} onRefresh={loadStatus} />}
        </SettingsMessageContext.Provider>
      </div>

      {saveAction && (saveAction.dirty || saveAction.saving) && (
        <BarraGuardado
          resumen="Cambios sin guardar"
          etiqueta={saveAction.label}
          guardando={saveAction.saving}
          deshabilitado={saveAction.deshabilitado}
          onGuardar={saveAction.onSave}
        />
      )}
    </div>
  )
}
