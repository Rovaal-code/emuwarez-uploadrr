import { useState } from 'react'
import { useUnsavedGuard } from '../../../utils/unsavedGuard'
import { updateSettings } from '../../../api/settings'
import { testImghostConnection, type IntegrationTestResult } from '../../../api/integrationTests'
import { ServiceIcon } from '../../../components/ServiceIcon'
import { Favicon, domainOf } from '../../../components/Favicon'
import { SortableList, DragHandleIcon, type DragHandleProps } from '../../../components/SortableList'
import { useTooltip, HoverTitle } from '../../../components/Tooltip'
import { Modal } from '../../../components/Modal'
import { testResultLabel, testResultColor } from '../../../utils/integrationResult'
import type { ConfigForm } from './useConfigForm'

function RemoveImgHostButton({ onClick }: { onClick: () => void }) {
  const { triggerProps, tooltipNode } = useTooltip('Quitar')
  return (
    <button className="btn btn-ghost btn-sm" style={{ fontSize: 13, padding: '2px 6px', color: 'var(--text-muted)' }}
      onClick={onClick} type="button" {...triggerProps}>✕{tooltipNode}</button>
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
  )
}
