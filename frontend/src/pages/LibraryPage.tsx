import { useState, useEffect, useCallback } from 'react'
import { getLibrary, TOP_LEVEL_PARENT_FILTER, getLibraryFilterOptions } from '../api/library'
import { getInstances } from '../api/instances'
import { refreshArrHealth } from '../api/diagnostics'
import type { LibraryItemResponse, LibraryListResponse, InstanceSafeResponse } from '../types/api'
import { PosterStatusIcon } from '../components/PosterStatusIcon'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { NomenclatureModal } from '../components/NomenclatureModal'
import { NomenclatureFieldsModal } from '../components/NomenclatureFieldsModal'
import { UploadPreflightModal } from '../components/UploadPreflightModal'
import { UploadWizardModal } from '../components/UploadWizardModal'
import { RequestFormModal } from '../components/RequestFormModal'
import { LibraryTreeRow, type LibraryActionKind } from '../components/LibraryTreeRow'
import { LargePosterCard } from '../components/LargePosterCard'
import { LibraryDetailPage } from '../components/LibraryDetailPage'
import { SeasonPackModal } from '../components/SeasonPackModal'
import { buildDeepLink, posterUrl } from '../utils/libraryItem'

const LOAD_LIMIT = 20000  // show everything in one container (no pagination); backend caps here
const VIEW_MODE_STORAGE_KEY = 'emuwarez_uploadrr_library_view'
// Sentinel matching the backend's NOT_AVAILABLE_STATUS_FILTER
// (services/library.py) — expands server-side to the same LocalStatus
// "not available" set the old standalone Faltantes tab used, so removing
// that tab doesn't lose the combined view.
const NOT_AVAILABLE_STATUS_FILTER = '__not_available__'

type ViewMode = 'grid' | 'grid-lg' | 'list'

function loadViewMode(): ViewMode {
  const stored = localStorage.getItem(VIEW_MODE_STORAGE_KEY)
  return stored === 'list' || stored === 'grid-lg' ? stored : 'grid'
}

function PosterCard({ item, instances, onClick }: { item: LibraryItemResponse; instances: InstanceSafeResponse[]; onClick: () => void }) {
  const deepLink = buildDeepLink(item, instances)
  return (
    <div
      className="clickable"
      onClick={onClick}
      style={{
        display: 'flex', flexDirection: 'column', borderRadius: 8, overflow: 'hidden',
        background: 'var(--bg-surface)', border: '1px solid var(--border)', cursor: 'pointer',
      }}
    >
      <div style={{ position: 'relative', width: '100%', aspectRatio: '2 / 3', background: 'rgba(255,255,255,0.04)' }}>
        {item.poster_url ? (
          <img
            src={posterUrl(item.poster_url, 'w342')}
            alt={item.title}
            loading="lazy"
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 36, opacity: 0.35 }}>
            {item.item_type === 'series' || item.item_type === 'episode' ? '📺' : '🎬'}
          </div>
        )}
        <div style={{ position: 'absolute', top: 6, right: 6 }}>
          <PosterStatusIcon status={item.local_status} />
        </div>
        {deepLink && (
          <a
            href={deepLink}
            target="_blank"
            rel="noreferrer"
            onClick={e => e.stopPropagation()}
            title={`Ver en ${item.instance_name ?? item.instance_type}`}
            style={{
              position: 'absolute', top: 6, left: 6, width: 22, height: 22, borderRadius: 5,
              background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, textDecoration: 'none',
            }}
          >
            🔗
          </a>
        )}
      </div>
    </div>
  )
}

export function LibraryPage() {
  const [data, setData] = useState<LibraryListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<LibraryItemResponse | null>(null)
  // Only opened from the "Pósters grandes" view — the small modal (grid/list) stays as-is.
  const [nomenclatureItem, setNomenclatureItem] = useState<LibraryItemResponse | null>(null)
  const [fieldsItem, setFieldsItem] = useState<LibraryItemResponse | null>(null)
  const [uploadItem, setUploadItem] = useState<LibraryItemResponse | null>(null)
  const [wizardItem, setWizardItem] = useState<LibraryItemResponse | null>(null)
  const [requestItem, setRequestItem] = useState<LibraryItemResponse | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>(loadViewMode)
  // Season pack modal — opened for a single Season row, or for a whole
  // Series row (its seasons resolved first, then all listed/applied here).
  const [packSeasons, setPackSeasons] = useState<LibraryItemResponse[] | null>(null)

  // Movie/episode leaf rows: open the existing single-item modals as
  // before. Season/Series rows: all 3 buttons open the same season-pack
  // modal (its per-episode filenames are already computed automatically —
  // no separate manual field-editing step for "Campos" in this version).
  async function handleTreeAction(kind: LibraryActionKind, item: LibraryItemResponse) {
    if (kind === 'nomenclature') { setNomenclatureItem(item); return }
    if (kind === 'fields') { setFieldsItem(item); return }
    if (kind === 'request') { setRequestItem(item); return }
    // 'upload' → unified Subir wizard. For a series/season the wizard itself
    // asks which season/episode (or the whole season) to target.
    setWizardItem(item)
  }

  useEffect(() => { localStorage.setItem(VIEW_MODE_STORAGE_KEY, viewMode) }, [viewMode])

  const [instances, setInstances] = useState<InstanceSafeResponse[]>([])
  useEffect(() => { getInstances().then(setInstances).catch(() => {}) }, [])

  // Provider/quality options across ALL levels (a value that only exists in a
  // mixed series' episodes wouldn't appear in the top-level list otherwise).
  const [providerOptions, setProviderOptions] = useState<string[]>([])
  const [qualityOptions, setQualityOptions] = useState<string[]>([])
  useEffect(() => {
    getLibraryFilterOptions()
      .then(o => { setProviderOptions(o.providers); setQualityOptions(o.qualities) })
      .catch(() => {})
  }, [])

  // Diagnostic actions — relocated here from the removed standalone
  // Faltantes tab (its own filtered view of Biblioteca now covers what it
  // used to show; these 3 buttons were the only functionality that didn't
  // already exist elsewhere).
  const [diagActionMsg, setDiagActionMsg] = useState<string | null>(null)
  const [diagActionLoading, setDiagActionLoading] = useState(false)

  async function handleRefreshHealth() {
    setDiagActionLoading(true)
    setDiagActionMsg(null)
    try {
      await refreshArrHealth({ include_queue: true, include_history: true })
      setDiagActionMsg('Salud ARR actualizada')
      await load()
    } catch {
      setDiagActionMsg('Error al refrescar salud ARR')
    } finally {
      setDiagActionLoading(false)
    }
  }


  // Filters
  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterInstanceId, setFilterInstanceId] = useState('')
  const [filterNomenclature, setFilterNomenclature] = useState('')
  const [filterRequest, setFilterRequest] = useState('')
  // Client-side text filters (no backend param) over the loaded items.
  const [searchProvider, setSearchProvider] = useState('')
  const [searchQuality, setSearchQuality] = useState('')
  const [offset, setOffset] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Provider/quality are rollups computed across the hierarchy, so when
      // one is active we fetch ALL levels (not just top level) — otherwise a
      // mixed-provider series would hide a season whose episodes are all e.g.
      // Netflix. Without them we keep the top-level tree.
      const flatFilter = !!(searchProvider || searchQuality)
      const result = await getLibrary({
        search: search || undefined,
        type: filterType || undefined,
        status: filterStatus || undefined,
        instance_id: filterInstanceId ? Number(filterInstanceId) : undefined,
        nomenclature: filterNomenclature || undefined,
        request_status: filterRequest || undefined,
        parent_id: flatFilter ? undefined : TOP_LEVEL_PARENT_FILTER,
        limit: LOAD_LIMIT,
        offset,
      })
      setData(result)
    } catch {
      setError('Error al cargar la biblioteca')
    } finally {
      setLoading(false)
    }
  }, [search, filterType, filterStatus, filterInstanceId, filterNomenclature, filterRequest, searchProvider, searchQuality, offset])

  useEffect(() => { load() }, [load])

  function applyFilters() {
    setOffset(0)
    load()
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const qualityOf = (it: LibraryItemResponse) => [it.resolution, it.source].filter(Boolean).join(' · ')

  const matchesFilter = (it: LibraryItemResponse) => {
    const provOk = !searchProvider || it.provider_label === searchProvider
    const qualOk = !searchQuality || qualityOf(it) === searchQuality
    return provOk && qualOk
  }
  // With a provider/quality filter active, `items` holds every level. Show the
  // matching items at the highest matching level: if a whole series matches,
  // show the series (not each of its seasons); if only some seasons match
  // (mixed series), show those seasons.
  const flatFilter = !!(searchProvider || searchQuality)
  let filteredItems: LibraryItemResponse[]
  if (flatFilter) {
    const matchIds = new Set(items.filter(matchesFilter).map(i => i.id))
    filteredItems = items.filter(it => matchIds.has(it.id) && !(it.parent_id != null && matchIds.has(it.parent_id)))
  } else {
    filteredItems = items
  }

  // Modals/overlays, shared by the list view and the detail page so an action
  // triggered from the detail page (Subir/Petición) shows its window without
  // having to go back to the library first.
  const modals = (
    <>
      {packSeasons && packSeasons.length > 0 && (
        <SeasonPackModal seasons={packSeasons} onClose={() => { setPackSeasons(null); load() }} />
      )}
      {nomenclatureItem && (
        <NomenclatureModal itemId={nomenclatureItem.id} itemTitle={nomenclatureItem.title} onClose={() => setNomenclatureItem(null)} />
      )}
      {fieldsItem && (
        <NomenclatureFieldsModal itemId={fieldsItem.id} itemTitle={fieldsItem.title} onClose={() => setFieldsItem(null)} onSaved={load} />
      )}
      {uploadItem && (
        <UploadPreflightModal itemId={uploadItem.id} itemTitle={uploadItem.title} onClose={() => setUploadItem(null)} />
      )}
      {wizardItem && (
        <UploadWizardModal item={wizardItem} onClose={() => setWizardItem(null)} onDone={() => { load() }} />
      )}
      {requestItem && (
        <RequestFormModal item={requestItem} onClose={() => setRequestItem(null)} />
      )}
    </>
  )

  // Dedicated detail page (Radarr/Sonarr-style) — shown in place of the list
  // when an item is selected, instead of a modal/card.
  if (selected) {
    return (
      <div>
        <LibraryDetailPage
          item={selected}
          instances={instances}
          onBack={() => setSelected(null)}
          onSelect={setSelected}
          onAction={handleTreeAction}
        />
        {modals}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="page-header">
        <div>
          <div className="page-title">Biblioteca</div>
          <div className="page-subtitle">
            {total > 0 ? `${total} elementos sincronizados` : 'Sin elementos'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button className="btn btn-primary btn-sm" onClick={handleRefreshHealth} disabled={diagActionLoading}>
            {diagActionLoading
              ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Sincronizando…</>
              : '↻ Sincronizar'}
          </button>
        </div>
      </div>

      {/* Search by title — where the ARR diagnostic buttons used to be */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
        <input
          className="form-input"
          placeholder="Buscar título…"
          value={search}
          onChange={e => { setSearch(e.target.value); if (!e.target.value) { setOffset(0) } }}
          onKeyDown={e => e.key === 'Enter' && applyFilters()}
          style={{ width: 140 }}
        />
        {diagActionMsg && <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{diagActionMsg}</span>}
      </div>

      {/* Filters + view modes on one line */}
      <div className="filters-bar">
        <select className="form-input form-select" value={filterType} onChange={e => { setFilterType(e.target.value); setOffset(0) }}>
          <option value="">Tipo: Todos</option>
          <option value="movie">Película</option>
          <option value="series">Serie</option>
          <option value="episode">Episodio</option>
        </select>
        <select className="form-input form-select" value={filterStatus} onChange={e => { setFilterStatus(e.target.value); setOffset(0) }}>
          <option value="">Estado: Todos</option>
          <option value="Disponible">Disponible</option>
          <option value="Parcial">Parcial</option>
          <option value={NOT_AVAILABLE_STATUS_FILTER}>Todos los no disponibles</option>
          <option value="Faltante">Faltante</option>
          <option value="En cola">En cola</option>
          <option value="Descargando">Descargando</option>
          <option value="Pendiente de importar">Pendiente de importar</option>
          <option value="Error de importación">Error de importación</option>
          <option value="Error de búsqueda">Error de búsqueda</option>
        </select>
        <select className="form-input form-select" value={filterInstanceId} onChange={e => { setFilterInstanceId(e.target.value); setOffset(0) }}>
          <option value="">Origen: Todos</option>
          {instances.map(inst => {
            // Cap the instance name at 15 chars so a long name can't blow up
            // the dropdown width.
            const name = inst.name.length > 15 ? inst.name.slice(0, 15) + '…' : inst.name
            return (
              <option key={inst.id} value={inst.id}>{inst.type === 'radarr' ? 'Radarr' : 'Sonarr'} — {name}</option>
            )
          })}
        </select>
        <select className="form-input form-select" value={filterNomenclature} onChange={e => { setFilterNomenclature(e.target.value); setOffset(0) }}>
          <option value="">Nomenclatura: Todas</option>
          <option value="Correcta">Correcta</option>
          <option value="No adaptada">No adaptada</option>
          <option value="N/A">N/A</option>
        </select>
        <select className="form-input form-select" value={filterRequest} onChange={e => { setFilterRequest(e.target.value); setOffset(0) }}>
          <option value="">Petición: Todas</option>
          <option value="Sin petición">Sin petición</option>
          <option value="Compatible">Compatible</option>
          <option value="Parcial">Parcial</option>
          <option value="No compatible">No compatible</option>
          <option value="Llena">Llena</option>
        </select>
        <select className="form-input form-select" value={searchProvider} onChange={e => setSearchProvider(e.target.value)}>
          <option value="">Provider: Todos</option>
          {providerOptions.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="form-input form-select" value={searchQuality} onChange={e => setSearchQuality(e.target.value)}>
          <option value="">Calidad: Todas</option>
          {qualityOptions.map(q => <option key={q} value={q}>{q}</option>)}
        </select>
        <div style={{ display: 'flex', gap: 4, marginLeft: 'auto' }}>
          <button
            className="btn btn-primary btn-sm"
            style={{ opacity: viewMode === 'grid' ? 1 : 0.55 }}
            onClick={() => setViewMode('grid')}
            title="Vista de pósters"
          >
            ▦ Pósters
          </button>
          <button
            className="btn btn-primary btn-sm"
            style={{ opacity: viewMode === 'grid-lg' ? 1 : 0.55 }}
            onClick={() => setViewMode('grid-lg')}
            title="Vista de pósters grandes"
          >
            ▦▦ Pósters grandes
          </button>
          <button
            className="btn btn-primary btn-sm"
            style={{ opacity: viewMode === 'list' ? 1 : 0.55 }}
            onClick={() => setViewMode('list')}
            title="Vista de lista"
          >
            ☰ Lista
          </button>
        </div>
      </div>

      {loading ? (
        <LoadingState label="Cargando biblioteca…" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : items.length === 0 ? (
        <EmptyState
          icon="📚"
          title="Biblioteca vacía"
          body="Añade instancias Radarr/Sonarr en la sección Instancias y sincroniza para ver el contenido aquí."
        />
      ) : viewMode === 'grid' ? (
        <div className="activity-section" style={{ padding: 20, flex: 1, minHeight: 0, overflowY: 'auto' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 16 }}>
            {filteredItems.map(item => (
              <PosterCard key={item.id} item={item} instances={instances} onClick={() => setSelected(item)} />
            ))}
          </div>
        </div>
      ) : viewMode === 'grid-lg' ? (
        <div className="activity-section" style={{ padding: 20, flex: 1, minHeight: 0, overflowY: 'auto' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 20 }}>
            {filteredItems.map(item => (
              <LargePosterCard key={item.id} item={item} instances={instances} onClick={() => setSelected(item)} />
            ))}
          </div>
        </div>
      ) : (
        <div className="activity-section" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ overflow: 'auto', flex: 1, minHeight: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Título</th>
                  <th>Tipo</th>
                  <th>Origen</th>
                  <th>Estado</th>
                  <th>Petición</th>
                  <th>Nomenclatura</th>
                  <th>Tamaño</th>
                  <th>Provider</th>
                  <th>Calidad</th>
                  <th>Actualizado</th>
                  <th className="col-actions">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map(item => (
                  <LibraryTreeRow
                    key={item.id}
                    item={item}
                    depth={0}
                    instances={instances}
                    onSelect={setSelected}
                    onAction={handleTreeAction}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {modals}
    </div>
  )
}
