import { useState, useEffect, useCallback, useTransition } from 'react'
import { getLibrary, TOP_LEVEL_PARENT_FILTER, getLibraryFilterOptions } from '../api/library'
import { Tooltip } from '../components/Tooltip'
import { useSync } from '../context/SyncContext'
import { getInstances } from '../api/instances'
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
import { HeaderFilter } from '../components/HeaderFilter'
import { buildDeepLink, posterUrl } from '../utils/libraryItem'

const LOAD_LIMIT = 20000  // show everything in one container (no pagination); backend caps here

const VIEW_MODE_STORAGE_KEY = 'emuwarez_uploadrr_library_view'

type ViewMode = 'grid' | 'grid-lg' | 'list'

function formatWait(seconds: number): string {
  const m = Math.ceil(seconds / 60)
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}min` : `${m} min`
}

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
  // Applying a Provider/Calidad filter fetches every level (up to LOAD_LIMIT)
  // and re-renders a large list — a synchronous commit that briefly froze the
  // UI after `loading` had already flipped back to false. Committing the data
  // (and the client-side filter changes) inside a transition keeps `isPending`
  // true through that heavy render so we can keep showing "Cargando…".
  const [isPending, startTransition] = useTransition()
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
  // Library + eMuwarez syncs are global (shared with the Dashboard/Peticiones
  // and the progress banner), so a running sync stays visible and its button
  // stays disabled on every tab.
  const {
    libSyncing, startLibrarySync,
    catalogSyncing, catalogStatus: emuStatus, startCatalogSync,
    lastCompletedAt,
  } = useSync()

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
  const [filterEmu, setFilterEmu] = useState('')
  const [sortBy, setSortBy] = useState('title_asc')
  const [offset, setOffset] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Provider/quality are rollups computed across the hierarchy, so when
      // one is active we fetch ALL levels (not just top level) — otherwise a
      // mixed-provider series would hide a season whose episodes are all e.g.
      // Netflix. Without them we keep the top-level tree.
      const flatFilter = !!(searchProvider || searchQuality || filterEmu)
      const result = await getLibrary({
        search: search || undefined,
        type: filterType || undefined,
        status: filterStatus || undefined,
        instance_id: filterInstanceId ? Number(filterInstanceId) : undefined,
        nomenclature: filterNomenclature || undefined,
        request_status: filterRequest || undefined,
        sort: sortBy,
        parent_id: flatFilter ? undefined : TOP_LEVEL_PARENT_FILTER,
        limit: LOAD_LIMIT,
        offset,
      })
      startTransition(() => setData(result))
    } catch {
      setError('Error al cargar la biblioteca')
    } finally {
      setLoading(false)
    }
  }, [search, filterType, filterStatus, filterInstanceId, filterNomenclature, filterRequest, searchProvider, searchQuality, filterEmu, sortBy, offset])

  useEffect(() => { load() }, [load])

  // Refresh the list whenever any global sync finishes (library or eMuwarez).
  useEffect(() => { if (lastCompletedAt) load() }, [lastCompletedAt, load])

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
    // "candidate" = No (not on eMuwarez), "present" = Sí. A partial series
    // (emu_in_catalog === 2) matches neither on its own — its Sí/No seasons do,
    // so filtering surfaces those seasons instead of the misleading series row.
    const emuOk = !filterEmu || (filterEmu === 'candidate' ? it.emu_in_catalog === 0 : it.emu_in_catalog === 1)
    return provOk && qualOk && emuOk
  }
  // With a Provider/Calidad/eMuwarez filter active, `items` holds every level.
  // Show the matching items at the highest matching level: if a whole series
  // matches, show the series (not each of its seasons); if only some seasons
  // match (mixed series), show those seasons.
  const flatFilter = !!(searchProvider || searchQuality || filterEmu)
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
          <Tooltip content="Consulta tus instancias de Radarr/Sonarr y actualiza la biblioteca local (títulos, rutas, estado en disco y nomenclatura).">
            <button
              className="btn btn-primary btn-sm"
              onClick={startLibrarySync}
              disabled={libSyncing}
            >
              {libSyncing
                ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Sincronizando…</>
                : '↻ Sincronizar biblioteca'}
            </button>
          </Tooltip>
          <Tooltip content={emuStatus && !emuStatus.can_sync
            ? `Disponible en ${formatWait(emuStatus.wait_seconds)}`
            : 'Descarga el catálogo de eMuwarez y compara con tu biblioteca (1 vez/hora)'}>
            <button
              className="btn btn-primary btn-sm"
              onClick={startCatalogSync}
              disabled={catalogSyncing || (emuStatus != null && !emuStatus.can_sync)}
            >
              {catalogSyncing
                ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Comparando…</>
                : emuStatus && !emuStatus.can_sync
                  ? `⇅ eMuwarez (${formatWait(emuStatus.wait_seconds)})`
                  : '⇅ Sincronizar eMuwarez'}
            </button>
          </Tooltip>
        </div>
      </div>

      {/* Search by title + filters + view modes, all on one line */}
      <div className="filters-bar">
        <input
          className="form-input"
          placeholder="Buscar título…"
          value={search}
          onChange={e => { setSearch(e.target.value); if (!e.target.value) { setOffset(0) } }}
          onKeyDown={e => e.key === 'Enter' && applyFilters()}
          style={{ width: 140 }}
        />
        <select className="form-input form-select" value={sortBy} onChange={e => { setSortBy(e.target.value); setOffset(0) }} style={{ width: 'max-content', paddingRight: 26, backgroundPosition: 'right 8px center' }}>
          <option value="title_asc">Orden: Título (A-Z)</option>
          <option value="title_desc">Orden: Título (Z-A)</option>
          <option value="updated_desc">Orden: RR (Reciente)</option>
          <option value="year_desc">Orden: Año (Nuevo)</option>
          <option value="year_asc">Orden: Año (Antiguo)</option>
        </select>
        <div style={{ display: 'flex', gap: 4, marginLeft: 'auto' }}>
          <Tooltip content="Vista de pósters">
            <button
              className="btn btn-primary btn-sm"
              style={{ opacity: viewMode === 'grid' ? 1 : 0.55 }}
              onClick={() => setViewMode('grid')}
              aria-label="Vista de pósters"
            >
              ▦
            </button>
          </Tooltip>
          <Tooltip content="Vista de pósters grandes">
            <button
              className="btn btn-primary btn-sm"
              style={{ opacity: viewMode === 'grid-lg' ? 1 : 0.55 }}
              onClick={() => setViewMode('grid-lg')}
              aria-label="Vista de pósters grandes"
            >
              ▦▦
            </button>
          </Tooltip>
          <Tooltip content="Vista de lista">
            <button
              className="btn btn-primary btn-sm"
              style={{ opacity: viewMode === 'list' ? 1 : 0.55 }}
              onClick={() => setViewMode('list')}
              aria-label="Vista de lista"
            >
              ☰
            </button>
          </Tooltip>
        </div>
      </div>

      {loading || isPending ? (
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
                  <th><HeaderFilter label="Tipo" value={filterType} onChange={v => { setFilterType(v); setOffset(0) }} options={[
                    { value: '', label: 'Todos' }, { value: 'movie', label: 'Película' }, { value: 'series', label: 'Serie' }, { value: 'episode', label: 'Episodio' },
                  ]} /></th>
                  <th><HeaderFilter label="Origen" value={filterInstanceId} onChange={v => { setFilterInstanceId(v); setOffset(0) }} options={[
                    { value: '', label: 'Todos' },
                    ...instances.map(inst => ({ value: String(inst.id), label: `${inst.type === 'radarr' ? 'Radarr' : 'Sonarr'} — ${inst.name.length > 15 ? inst.name.slice(0, 15) + '…' : inst.name}` })),
                  ]} /></th>
                  <th><HeaderFilter label="Estado" value={filterStatus} onChange={v => { setFilterStatus(v); setOffset(0) }} options={[
                    { value: '', label: 'Todos' }, { value: 'Disponible', label: 'Disponible' }, { value: 'Parcial', label: 'Parcial' }, { value: 'Faltante', label: 'Faltante' }, { value: 'Error de importación', label: 'Error' },
                  ]} /></th>
                  <th><HeaderFilter label="Petición" value={filterRequest} onChange={v => { setFilterRequest(v); setOffset(0) }} options={[
                    { value: '', label: 'Todas' }, { value: 'Sin petición', label: 'Sin petición' }, { value: 'Compatible', label: 'Compatible' }, { value: 'Parcial', label: 'Parcial' }, { value: 'No compatible', label: 'No compatible' }, { value: 'Llena', label: 'Llena' },
                  ]} /></th>
                  <th><HeaderFilter label="Nomenclatura" value={filterNomenclature} onChange={v => { setFilterNomenclature(v); setOffset(0) }} options={[
                    { value: '', label: 'Todas' }, { value: 'Correcta', label: 'Correcta' }, { value: 'No adaptada', label: 'No adaptada' }, { value: 'N/A', label: 'N/A' },
                  ]} /></th>
                  <th>Tamaño</th>
                  <th><HeaderFilter label="Provider" value={searchProvider} onChange={setSearchProvider} options={[
                    { value: '', label: 'Todos' }, ...providerOptions.map(p => ({ value: p, label: p })),
                  ]} /></th>
                  <th><HeaderFilter label="Calidad" value={searchQuality} onChange={setSearchQuality} options={[
                    { value: '', label: 'Todas' }, ...qualityOptions.map(q => ({ value: q, label: q })),
                  ]} /></th>
                  <th><HeaderFilter label="¿En eMuwarez?" value={filterEmu} onChange={v => { setFilterEmu(v); setOffset(0) }} options={[
                    { value: '', label: 'Todos' }, { value: 'present', label: 'Sí' }, { value: 'candidate', label: 'No' },
                  ]} /></th>
                  <th>Aportes</th>
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
                    onReload={load}
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
