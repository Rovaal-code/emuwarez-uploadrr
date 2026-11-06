import { useState } from 'react'
import { useUnsavedGuard } from '../../../utils/unsavedGuard'
import { updateSettings } from '../../../api/settings'
import { testImghostConnection, type IntegrationTestResult } from '../../../api/integrationTests'
import { ServiceIcon } from '../../../components/ServiceIcon'
import { IconoCerrar } from '../../../components/Iconos'
import { Favicon, domainOf } from '../../../components/Favicon'
import { SortableList, DragHandleIcon, PistaReordenar, type DragHandleProps } from '../../../components/SortableList'
import { useTooltip, HoverTitle } from '../../../components/Tooltip'
import { Modal } from '../../../components/Modal'
import { ResultadoPrueba } from '../Campo'
import { CabeceraTarjeta } from '../CabeceraTarjeta'
import type { ConfigForm } from './useConfigForm'

function RemoveImgHostButton({ onClick, nombre }: { onClick: () => void; nombre: string }) {
  const { triggerProps, tooltipNode } = useTooltip('Quitar')
  return (
    <button className="btn btn-ghost btn-sm aj-ghost-muted" aria-label={`Quitar ${nombre}`}
      onClick={onClick} type="button" {...triggerProps}><IconoCerrar size={14} />{tooltipNode}</button>
  )
}

export function ProveedoresImagenesCard({ form }: { form: ConfigForm }) {
  const { settings, setSettings, imgEnabled, setImgEnabled } = form
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
  // La clave de un proveedor de imágenes escrita en su modal y sin guardar.
  useUnsavedGuard('config-clave-imagenes', keyModalHost !== null && keyDraft.trim() !== '')

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

  return (
    <div className="placeholder-card provider-card">
      <CabeceraTarjeta
        icono={<ServiceIcon type="imghost" size={18} />}
        titulo="Proveedores de imágenes"
        descripcion={<>Para las capturas que Uploadrr sube junto al torrent. Se prueban por orden de prioridad; <PistaReordenar raton="arrastra para reordenar, o usa las flechas desde el asa de cada fila." dedo="reordénalos con las flechas de cada fila." /> Cualquiera se puede quitar; sin ninguno, la subida no arranca.</>}
      />
      <span className="form-label">Prioridad de proveedores</span>
      {(() => {
        const avail = settings?.image_hosts_available ?? []
        const configuredIds = imgEnabled.filter(id => avail.some(h => h.id === id))
        const notConfigured = avail.filter(h => !configuredIds.includes(h.id))
        const metaOf = (id: string) => avail.find(h => h.id === id)
        const fila = (id: string, idx: number, asa?: { dragging: boolean; handleProps: DragHandleProps; botones: React.ReactNode }) => {
          const h = metaOf(id); if (!h) return null
          const dragging = !!asa?.dragging
          const t = imgTest[id]
          return (
            <div className={dragging ? 'aj-pill-fila aj-pill-fila-arrastre' : 'aj-pill-fila'}>
              <div className="aj-flex-c-8">
                <span className="aj-idx">{idx + 1}</span>
                {asa ? (
                  <HoverTitle
                    as="span"
                    tip="Arrastra para reordenar, o usa las flechas del teclado"
                    {...asa.handleProps}
                    className="drag-handle aj-asa-handle"
                  ><DragHandleIcon /></HoverTitle>
                ) : <span className="aj-asa-hueco" />}
                {asa?.botones}
                <a href={h.url} target="_blank" rel="noreferrer" title={`Abrir ${h.label}`}
                  onClick={e => e.stopPropagation()} onMouseDown={e => e.stopPropagation()}
                  className="aj-inline-flex">
                  <Favicon domain={domainOf(h.url)} size={15} background="var(--overlay-light)" fallback={<ServiceIcon type="imghost" size={15} />} />
                </a>
                <span className="aj-ellipsis-nowrap-13">{h.label}</span>
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
                      className={`badge aj-badge-key ${guardada ? 'status-available' : 'nom-na badge-blink'}`}
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
                <div className="aj-flex-c-8 aj-ml-auto">
                  {!h.needs_key && (
                    <button className="btn btn-secondary btn-sm aj-btn-mini"
                      onClick={() => handleTestImghost(id)} disabled={imgTesting === id} type="button">
                      {imgTesting === id ? 'Probando…' : 'Probar'}
                    </button>
                  )}
                  <RemoveImgHostButton onClick={() => toggleImgHost(id)} nombre={h.label} />
                </div>
              </div>
              {/* Solo para los que no tienen tarjeta: los demás ya lo
                  enseñan ahí y salía dos veces. */}
              {!h.needs_key && t && <div className="aj-res-11"><ResultadoPrueba resultado={t} /></div>}
            </div>
          )
        }
        return (
          <>
          <div className="provider-card__body">
            <div className="provider-card__list">
              <div className="aj-col-8">
                <SortableList etiqueta={id => metaOf(id)?.label ?? id} ids={configuredIds} onChange={setImgEnabled} gap={8} renderRow={fila} />
                {configuredIds.length === 0 && (
                  <p className="aj-muted-13" role="status">Sin proveedores: añade al menos uno o las subidas no podrán arrancar.</p>
                )}
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
                <Modal titulo={<>API key de {host?.label ?? keyModalHost}</>} onClose={() => { if (!keySaving) setKeyModalHost(null) }} className="aj-modal-480">
                  <div className="modal-body">
                    <div className="aj-flex-8 aj-stretch">
                      <input
                        type="password" className="form-input aj-flex-1" autoComplete="new-password"
                        aria-label={`API key de ${host?.label ?? keyModalHost}`}
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
                    {t && <div className="aj-res-modal"><ResultadoPrueba resultado={t} /></div>}
                    {keyError && <div className="text-error aj-fs-12 aj-mt-8" role="alert">✗ {keyError}</div>}
                    <p className="aj-nota-115">
                      La clave se comprueba contra el proveedor, sin subir ninguna imagen. Guardar la
                      comprueba también: si no vale, no se guarda.
                    </p>
                    <div className="aj-acciones-modal">
                      {guardada && (
                        <button className="btn btn-secondary aj-mr-auto" type="button" onClick={quitar} disabled={keySaving}>
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
              <Modal titulo="Añadir proveedor de imágenes" onClose={() => setShowAddImg(false)} className="aj-modal-480">
                <div className="modal-body">
                  {notConfigured.length === 0 ? (
                    <p className="aj-muted-13">Ya están todos añadidos.</p>
                  ) : (
                    <div className="aj-rejilla-add">
                      {notConfigured.map(h => (
                        <button key={h.id} className="btn btn-ghost btn-sm aj-add-btn" type="button"
                          onClick={() => toggleImgHost(h.id)}>
                          <Favicon domain={domainOf(h.url)} size={16} background="var(--overlay-light)" fallback={<ServiceIcon type="imghost" size={16} />} /> {h.label} {h.needs_key && <span className="badge nom-na">API key</span>}
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
  )
}
