import { useState, useEffect, useCallback, useRef } from 'react'
import { getInstances, addInstance, updateInstance, testInstance, syncInstance, deleteInstance } from '../api/instances'
import { getDashboardSummary } from '../api/dashboard'
import { testArrConnection, type IntegrationTestResult } from '../api/integrationTests'
import type { InstanceSafeResponse } from '../types/api'
import { ServiceIcon } from '../components/ServiceIcon'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { Modal } from '../components/Modal'
import { ApiClientError } from '../api/client'
import { formatDate } from '../utils/format'
import { isValidHttpUrl } from '../utils/validation'
import { estadoDeInstancia, type CaidaDeInstancia } from '../utils/instancias'
import { useRefrescoPorAvisos } from '../hooks/useRefrescoPorAvisos'
import { IconoEnchufe } from '../components/Iconos'
import { Campo, ResultadoPrueba, enfocarPrimerError } from './ajustes/Campo'

type InstanceKind = 'radarr' | 'sonarr'

interface AddForm {
  type: InstanceKind
  name: string
  url: string
  api_key: string
  is_4k: boolean
  is_anime: boolean
}

function defaultForm(): AddForm {
  return { type: 'radarr', name: '', url: '', api_key: '', is_4k: false, is_anime: false }
}

interface EditForm {
  name: string
  url: string
  api_key: string
  is_4k: boolean
  is_anime: boolean
  enabled: boolean
}

function editFormFrom(inst: InstanceSafeResponse): EditForm {
  return { name: inst.name, url: inst.url, api_key: '', is_4k: inst.is_4k, is_anime: inst.is_anime, enabled: inst.enabled }
}

// Errores de campo de un formulario de instancia; vacío si todo está bien.
interface ErroresDeCampo { name?: string; url?: string; api_key?: string }

function validar(f: { name: string; url: string; api_key: string }, exigirClave: boolean): ErroresDeCampo {
  const e: ErroresDeCampo = {}
  if (!f.name.trim()) e.name = 'Escribe un nombre.'
  if (!f.url.trim()) e.url = 'Escribe la URL de la instancia.'
  else if (!isValidHttpUrl(f.url)) e.url = 'La URL debe empezar por http:// o https:// e incluir un host válido.'
  if (exigirClave && !f.api_key.trim()) e.api_key = 'Pega la API key de la instancia.'
  return e
}

// Lo que se enseña bajo una instancia tras probarla o sincronizarla.
interface Resultado { tono: 'ok' | 'error' | 'aviso' | 'neutro'; texto: string }

// Pregunta antes de borrar: es lo único de esta pantalla que no se deshace.
function ConfirmarEliminar({ instancia, onCancelar, onConfirmar }: {
  instancia: InstanceSafeResponse
  onCancelar: () => void
  onConfirmar: () => Promise<string | null>
}) {
  const [borrando, setBorrando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function confirmar() {
    setBorrando(true)
    setError(null)
    const fallo = await onConfirmar()
    if (fallo) { setError(fallo); setBorrando(false) }
  }
  return (
    <Modal titulo={<>Eliminar «{instancia.name}»</>} onClose={() => { if (!borrando) onCancelar() }} className="inst-modal-borrar">
      <div className="modal-body">
        <p className="inst-modal-texto">
          Su contenido sincronizado se quitará de la biblioteca. Las subidas se quedan en el historial.
        </p>
        {error && <p className="inst-modal-error" role="alert">{error}</p>}
        <div className="inst-modal-acciones">
          <button className="btn btn-secondary" type="button" onClick={onCancelar} disabled={borrando} autoFocus>Cancelar</button>
          <button className="btn btn-danger" type="button" onClick={confirmar} disabled={borrando}>
            {borrando ? 'Eliminando…' : 'Eliminar instancia'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

export function InstancesPage() {
  const [instances, setInstances] = useState<InstanceSafeResponse[]>([])
  const [caidas, setCaidas] = useState<CaidaDeInstancia[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState<AddForm>(defaultForm())
  const [addError, setAddError] = useState<string | null>(null)
  const [addErrores, setAddErrores] = useState<ErroresDeCampo>({})
  const [adding, setAdding] = useState(false)
  const [addTestResult, setAddTestResult] = useState<IntegrationTestResult | null>(null)
  const [addTesting, setAddTesting] = useState(false)
  const [testResults, setTestResults] = useState<Record<number, Resultado>>({})
  const [testingId, setTestingId] = useState<number | null>(null)
  const [syncingId, setSyncingId] = useState<number | null>(null)
  const [syncResults, setSyncResults] = useState<Record<number, Resultado>>({})
  const [aEliminar, setAEliminar] = useState<InstanceSafeResponse | null>(null)
  const botonAnadir = useRef<HTMLButtonElement>(null)

  // Phase 11B — edit instance
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<EditForm | null>(null)
  const [editSaving, setEditSaving] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [editErrores, setEditErrores] = useState<ErroresDeCampo>({})
  const [editTestResult, setEditTestResult] = useState<IntegrationTestResult | null>(null)
  const [editTesting, setEditTesting] = useState(false)

  // Con `silencioso` no se vuelve a la pantalla de carga: solo se refrescan los datos (y la salud de cada instancia).
  const load = useCallback(async (silencioso = false) => {
    if (!silencioso) { setLoading(true); setError(null) }
    try {
      setInstances(await getInstances())
      setError(null)
    } catch {
      // Una recarga en segundo plano que falla deja la lista que ya había, sin tapar las tarjetas con un error.
      if (!silencioso) setError('Error al cargar las instancias')
    } finally {
      setLoading(false)
    }
  }, [])

  // Qué instancias no respondieron en la última mirada de la vigilancia. Sin vigilancia no se afirma nada (lista vacía).
  const cargarSalud = useCallback(async () => {
    try {
      setCaidas((await getDashboardSummary()).instancias_caidas ?? [])
    } catch { /* sin dato de salud: la tarjeta enseña solo lo que ya sabía */ }
  }, [])

  useEffect(() => { load() }, [load])
  // La vigilancia corre cada pocos minutos y avisa al terminar; entre avisos, una red de seguridad lenta.
  useRefrescoPorAvisos(['tarea-terminada'], () => { void cargarSalud(); void load(true) }, {
    cadaSinCanal: 60_000,
    cadaConCanal: 300_000,
  })
  useEffect(() => { void cargarSalud() }, [cargarSalud])

  // Tras pintar: el foco entra al primer campo del formulario que se abre, o vuelve al botón que lo abrió al cerrarlo.
  function enfocar(selector: string) {
    requestAnimationFrame(() => document.querySelector<HTMLElement>(selector)?.focus())
  }

  function abrirAlta() {
    setShowAdd(true)
    enfocar('#inst-nueva select, #inst-nueva input')
  }

  function cerrarAlta() {
    setShowAdd(false)
    setAddError(null)
    setAddErrores({})
    setAddTestResult(null)
    requestAnimationFrame(() => botonAnadir.current?.focus())
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    setAddError(null)
    const errores = validar(form, true)
    setAddErrores(errores)
    if (Object.keys(errores).length > 0) { enfocarPrimerError('#inst-nueva'); return }
    setAdding(true)
    try {
      await addInstance({
        type: form.type, name: form.name.trim(), url: form.url.trim(), api_key: form.api_key.trim(),
        is_4k: form.is_4k,
        is_anime: form.is_anime,
      })
      setForm(defaultForm())
      cerrarAlta()
      await load(true)
      void cargarSalud()
    } catch (err) {
      setAddError(err instanceof ApiClientError ? err.message : 'Error al añadir instancia')
    } finally {
      setAdding(false)
    }
  }

  async function handleAddTest() {
    if (!form.url.trim() || !form.api_key.trim()) {
      setAddTestResult({ ok: false, service: form.type, status: 'not_configured', message: 'Introduce URL y API key antes de probar' })
      return
    }
    setAddTesting(true)
    setAddTestResult(null)
    try {
      const r = await testArrConnection({ kind: form.type, base_url: form.url.trim(), api_key: form.api_key.trim() })
      setAddTestResult(r)
    } catch {
      setAddTestResult({ ok: false, service: form.type, status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setAddTesting(false)
    }
  }

  async function handleTest(inst: InstanceSafeResponse) {
    setTestingId(inst.id)
    setTestResults(p => ({ ...p, [inst.id]: { tono: 'neutro', texto: 'Probando…' } }))
    try {
      const res = await testInstance(inst.id)
      const extra = res.username ? ` (${res.username})` : ''
      setTestResults(p => ({
        ...p,
        [inst.id]: res.ok
          ? { tono: 'ok', texto: `Responde: v${res.version ?? '?'}${extra}` }
          : { tono: 'error', texto: `No responde: ${res.error ?? 'error desconocido'}` },
      }))
      void load(true)
    } catch {
      setTestResults(p => ({ ...p, [inst.id]: { tono: 'error', texto: 'No se pudo contactar con el servidor' } }))
    } finally {
      setTestingId(null)
    }
  }

  async function handleSync(id: number) {
    setSyncingId(id)
    setSyncResults(p => ({ ...p, [id]: { tono: 'neutro', texto: 'Sincronizando…' } }))
    try {
      const res = await syncInstance(id)
      setSyncResults(p => ({ ...p, [id]: { tono: 'ok', texto: `Sincronizada: ${res.imported} elementos, ${res.missing} faltantes` } }))
    } catch (e: unknown) {
      setSyncResults(p => ({ ...p, [id]: { tono: 'error', texto: e instanceof Error && e.message ? e.message : 'Error de sincronización' } }))
    } finally {
      setSyncingId(null)
    }
  }

  // Devuelve el motivo si falla, para que el diálogo lo enseñe y se quede abierto.
  async function eliminar(inst: InstanceSafeResponse): Promise<string | null> {
    try {
      await deleteInstance(inst.id)
      setAEliminar(null)
      await load(true)
      void cargarSalud()
      return null
    } catch (e: unknown) {
      return e instanceof Error && e.message ? e.message : 'No se pudo eliminar la instancia'
    }
  }

  function startEdit(inst: InstanceSafeResponse) {
    setEditingId(inst.id)
    setEditForm(editFormFrom(inst))
    setEditError(null)
    setEditErrores({})
    setEditTestResult(null)
    // El botón «Editar» desaparece con la tarjeta: sin esto el foco caía en el body.
    enfocar(`#inst-edicion-${inst.id} input`)
  }

  function cancelEdit() {
    // Al cerrar la edición (cancelar o guardar), el foco vuelve a su «Editar».
    if (editingId !== null) enfocar(`[data-editar="${editingId}"]`)
    setEditingId(null)
    setEditForm(null)
    setEditError(null)
    setEditErrores({})
    setEditTestResult(null)
  }

  async function handleUpdate(inst: InstanceSafeResponse) {
    if (!editForm) return
    setEditError(null)
    const errores = validar(editForm, false)
    setEditErrores(errores)
    if (Object.keys(errores).length > 0) { enfocarPrimerError('.inst-edicion'); return }
    setEditSaving(true)
    try {
      const saved = await updateInstance(inst.id, {
        name: editForm.name.trim(),
        url: editForm.url.trim(),
        api_key: editForm.api_key.trim() || undefined,
        enabled: editForm.enabled,
        is_4k: editForm.is_4k,
        is_anime: editForm.is_anime,
      })
      cancelEdit()
      // Guardado, pero con un aviso (la instancia no respondía): se enseña en su tarjeta, donde van los resultados.
      setTestResults(p => {
        const siguiente = { ...p }
        if (saved.warning) siguiente[inst.id] = { tono: 'aviso', texto: saved.warning }
        else delete siguiente[inst.id]
        return siguiente
      })
      await load(true)
      void cargarSalud()
    } catch (err) {
      setEditError(err instanceof ApiClientError ? err.message : 'Error al guardar los cambios')
    } finally {
      setEditSaving(false)
    }
  }

  async function handleEditTest(inst: InstanceSafeResponse) {
    if (!editForm) return
    setEditTesting(true)
    setEditTestResult(null)
    try {
      const url = editForm.url.trim()
      const key = editForm.api_key.trim()
      // If the key was left blank (keep current), fall back to testing the saved instance.
      const r = key
        ? await testArrConnection({ kind: inst.type as 'radarr' | 'sonarr', base_url: url, api_key: key })
        : await testInstance(inst.id).then(r2 => ({ ok: r2.ok, service: inst.type, status: r2.ok ? 'connected' : 'connection_error', message: r2.error ?? 'OK', details: { version: r2.version, username: r2.username } } as IntegrationTestResult))
      setEditTestResult(r)
    } catch {
      setEditTestResult({ ok: false, service: inst.type, status: 'connection_error', message: 'Error al contactar con el servidor' })
    } finally {
      setEditTesting(false)
    }
  }

  const sinResponder = instances.filter(i => estadoDeInstancia(i, caidas).tono === 'error' && i.enabled).length

  return (
    <div data-tour="instances-content" className="inst-pagina">
      <div className="page-header">
        <div>
          <h1 className="page-title">Instancias</h1>
          <div className="page-subtitle">Gestiona tus instancias Radarr y Sonarr</div>
        </div>
        <div className="inst-cabecera-acciones">
          {sinResponder > 0 && (
            <span className="inst-estado inst-estado--error" role="status">
              <span className="inst-estado__punto" aria-hidden />
              {sinResponder === 1 ? '1 sin responder' : `${sinResponder} sin responder`}
            </span>
          )}
          {/* Siempre dice lo mismo: con el formulario abierto se desactiva, y «Cancelar» está junto a «Añadir». */}
          <button
            ref={botonAnadir}
            className="btn btn-primary btn-sm"
            aria-expanded={showAdd}
            aria-controls="inst-nueva"
            onClick={abrirAlta}
            disabled={showAdd}
          >
            + Añadir instancia
          </button>
        </div>
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="card inst-nueva" id="inst-nueva">
          <h2 className="inst-nueva-titulo">Nueva instancia</h2>
          <form onSubmit={handleAdd} noValidate>
            <div className="inst-rejilla-200">
              <Campo etiqueta="Tipo">
                {c => (
                  <select {...c} className="form-input form-select" value={form.type} onChange={e => setForm(p => ({ ...p, type: e.target.value as InstanceKind }))}>
                    <option value="radarr">Radarr</option>
                    <option value="sonarr">Sonarr</option>
                  </select>
                )}
              </Campo>
              <Campo etiqueta="Nombre" nota="máx. 15" error={addErrores.name}>
                {c => <input {...c} className="form-input" placeholder={form.type === 'sonarr' ? 'Sonarr principal' : 'Radarr principal'} value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} maxLength={15} autoComplete="off" />}
              </Campo>
              <Campo etiqueta="URL" error={addErrores.url}>
                {c => <input {...c} className="form-input" inputMode="url" placeholder={form.type === 'sonarr' ? 'http://192.168.1.100:8989' : 'http://192.168.1.100:7878'} value={form.url} onChange={e => setForm(p => ({ ...p, url: e.target.value }))} autoComplete="off" spellCheck={false} />}
              </Campo>
              <Campo etiqueta="API key" error={addErrores.api_key}>
                {c => <input {...c} className="form-input" type="password" placeholder="API key" value={form.api_key} onChange={e => setForm(p => ({ ...p, api_key: e.target.value }))} autoComplete="new-password" />}
              </Campo>
            </div>
            <div className="inst-checks">
              <label className="checkbox-label"><input type="checkbox" checked={form.is_4k} onChange={e => setForm(p => ({ ...p, is_4k: e.target.checked }))} /> 4K</label>
              <label className="checkbox-label"><input type="checkbox" checked={form.is_anime} onChange={e => setForm(p => ({ ...p, is_anime: e.target.checked }))} /> Anime</label>
            </div>
            {addError && <div className="alert alert-error inst-error" role="alert">{addError}</div>}
            <div className="inst-botones">
              <button type="submit" className="btn btn-primary btn-sm" disabled={adding}>
                {adding ? 'Probando conexión…' : 'Añadir'}
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={handleAddTest} disabled={addTesting}>
                {addTesting ? 'Probando…' : 'Probar conexión'}
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={cerrarAlta} disabled={adding}>Cancelar</button>
              <ResultadoPrueba resultado={addTestResult} />
            </div>
          </form>
        </div>
      )}

      {/* List */}
      {loading ? (
        <LoadingState label="Cargando instancias…" />
      ) : error ? (
        <ErrorState message={error} onRetry={() => load()} />
      ) : instances.length === 0 ? (
        <EmptyState
          icon={<IconoEnchufe />}
          title="Sin instancias configuradas"
          body="Añade una instancia Radarr o Sonarr para empezar."
          action={<button className="btn btn-primary btn-sm" onClick={abrirAlta}>+ Añadir instancia</button>}
        />
      ) : (
        <ul className="inst-lista">
          {instances.map(inst => {
            const estado = estadoDeInstancia(inst, caidas)
            const prueba = testResults[inst.id]
            const sync = syncResults[inst.id]
            return (
              <li key={inst.id} className={`instance-card inst-tarjeta inst-tarjeta--${estado.tono}`}>
                {editingId === inst.id && editForm ? (
                  <div className="inst-edicion" id={`inst-edicion-${inst.id}`}>
                    {/* Qué instancia se edita: los campos solos no lo decían. */}
                    <h3 className="inst-titulo inst-titulo-edicion">
                      <ServiceIcon type={inst.type as 'radarr' | 'sonarr'} size={20} />
                      Editar «{inst.name}»
                    </h3>
                    <div className="inst-rejilla-180">
                      <Campo etiqueta="Nombre" nota="máx. 15" error={editErrores.name}>
                        {c => <input {...c} className="form-input" value={editForm.name} onChange={e => setEditForm(p => p && ({ ...p, name: e.target.value }))} maxLength={15} autoComplete="off" />}
                      </Campo>
                      <Campo etiqueta="URL" error={editErrores.url}>
                        {c => <input {...c} className="form-input" inputMode="url" value={editForm.url} onChange={e => setEditForm(p => p && ({ ...p, url: e.target.value }))} autoComplete="off" spellCheck={false} />}
                      </Campo>
                      <Campo etiqueta="API key" nota="vacío = mantener">
                        {c => <input {...c} type="password" className="form-input" placeholder={inst.api_key_masked} value={editForm.api_key} onChange={e => setEditForm(p => p && ({ ...p, api_key: e.target.value }))} autoComplete="new-password" />}
                      </Campo>
                    </div>
                    <div className="inst-checks inst-checks-edicion">
                      <label className="checkbox-label"><input type="checkbox" checked={editForm.is_4k} onChange={e => setEditForm(p => p && ({ ...p, is_4k: e.target.checked }))} /> 4K</label>
                      <label className="checkbox-label"><input type="checkbox" checked={editForm.is_anime} onChange={e => setEditForm(p => p && ({ ...p, is_anime: e.target.checked }))} /> Anime</label>
                      <label className="checkbox-label"><input type="checkbox" checked={editForm.enabled} onChange={e => setEditForm(p => p && ({ ...p, enabled: e.target.checked }))} /> Activada</label>
                    </div>
                    {editError && <div className="alert alert-error inst-error inst-error-edicion" role="alert">{editError}</div>}
                    <div className="inst-botones">
                      <button className="btn btn-primary btn-sm" onClick={() => handleUpdate(inst)} disabled={editSaving}>
                        {editSaving ? 'Guardando…' : 'Guardar cambios'}
                      </button>
                      <button className="btn btn-secondary btn-sm" onClick={() => handleEditTest(inst)} disabled={editTesting}>
                        {editTesting ? 'Probando…' : 'Probar conexión'}
                      </button>
                      <button className="btn btn-secondary btn-sm" onClick={cancelEdit}>Cancelar</button>
                      <ResultadoPrueba resultado={editTestResult} />
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="instance-card-info">
                      <ServiceIcon type={inst.type as 'radarr' | 'sonarr'} size={30} />
                      <div className="instance-card-meta">
                        <div className="inst-nombre">
                          <h3 className="inst-titulo">{inst.name}</h3>
                          {inst.is_4k && <span className="badge status-queued inst-etiqueta">4K</span>}
                          {inst.is_anime && <span className="badge status-uploading inst-etiqueta">Anime</span>}
                          <span className={`inst-estado inst-estado--${estado.tono}`}>
                            <span className="inst-estado__punto" aria-hidden />
                            {estado.etiqueta}
                          </span>
                        </div>
                        <div className="instance-card-url" title={inst.url}>{inst.url}</div>
                        {/* Tres datos sueltos: cada uno en su hueco, no cosidos con puntos. */}
                        <dl className="inst-datos">
                          <div><dt>API key</dt><dd>{inst.api_key_masked}</dd></div>
                          <div><dt>Añadida</dt><dd>{formatDate(inst.created_at)}</dd></div>
                          {estado.detalle && <div><dt>{estado.detalle.titulo}</dt><dd>{estado.detalle.valor}</dd></div>}
                        </dl>
                        {(prueba || sync) && (
                          <div className="inst-resultados" role="status">
                            {prueba && <span className={`inst-resultado inst-resultado--${prueba.tono}`}>{prueba.texto}</span>}
                            {sync && <span className={`inst-resultado inst-resultado--${sync.tono}`}>{sync.texto}</span>}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="instance-card-actions">
                      <button
                        className="btn btn-secondary btn-sm"
                        disabled={testingId === inst.id}
                        onClick={() => handleTest(inst)}
                      >
                        {testingId === inst.id ? 'Probando…' : 'Probar conexión'}
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        disabled={syncingId === inst.id}
                        onClick={() => handleSync(inst.id)}
                      >
                        {syncingId === inst.id ? 'Sincronizando…' : 'Sincronizar'}
                      </button>
                      <button className="btn btn-secondary btn-sm" onClick={() => startEdit(inst)} aria-label={`Editar ${inst.name}`} data-editar={inst.id}>
                        Editar
                      </button>
                      <button className="btn btn-danger btn-sm" onClick={() => setAEliminar(inst)} aria-label={`Eliminar ${inst.name}`}>
                        Eliminar
                      </button>
                    </div>
                  </>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {aEliminar && (
        <ConfirmarEliminar instancia={aEliminar} onCancelar={() => setAEliminar(null)} onConfirmar={() => eliminar(aEliminar)} />
      )}
    </div>
  )
}
