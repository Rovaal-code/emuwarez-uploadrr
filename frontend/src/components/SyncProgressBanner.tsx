import { useSync } from '../context/SyncContext'
import { ServiceIcon } from './ServiceIcon'

// "1m 20s" / "45s" for the eMuwarez ETA.
function fmtEta(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

// Rendered once in the app shell (above every page), so a sync started on any
// tab shows the same live progress on all of them.
export function SyncProgressBanner() {
  const { libProgress, catalogProgress, requestsSyncing } = useSync()
  if (!libProgress && !catalogProgress && !requestsSyncing) return null

  return (
    <>
      {libProgress && (
        <div className="activity-section" style={{ padding: '14px 18px', marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {libProgress.error
              ? <span style={{ color: 'var(--color-missing, #ef4444)', fontSize: 18, lineHeight: 1 }}>✗</span>
              : <span className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} />}
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontWeight: 600 }}>Sincronizando biblioteca…</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                {(libProgress.instance_type === 'radarr' || libProgress.instance_type === 'sonarr') &&
                  <ServiceIcon type={libProgress.instance_type} size={14} />}
                {libProgress.instance && <span>{libProgress.instance}</span>}
                <span>
                  {libProgress.error ?? (libProgress.total
                    ? `· ${libProgress.imported.toLocaleString('es-ES')} / ${libProgress.total.toLocaleString('es-ES')} elementos`
                    : `· ${libProgress.imported.toLocaleString('es-ES')} elementos`)}
                  {libProgress.missing ? ` · ${libProgress.missing.toLocaleString('es-ES')} no disponibles` : ''}
                </span>
              </div>
            </div>
          </div>
          {!libProgress.error && libProgress.total ? (
            <div className="progress-bar" style={{ marginTop: 10 }}>
              <div className="progress-fill" style={{ width: `${Math.min(100, Math.round((libProgress.imported / libProgress.total) * 100))}%` }} />
            </div>
          ) : null}
        </div>
      )}

      {catalogProgress && (
        <div className="activity-section" style={{ padding: '14px 18px', marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {catalogProgress.error
              ? <span style={{ color: 'var(--color-missing, #ef4444)', fontSize: 18, lineHeight: 1 }}>✗</span>
              : <span className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} />}
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                <ServiceIcon type="emu" size={15} /> Sincronizando con eMuwarez…
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {catalogProgress.error ?? catalogProgress.phase}
                {catalogProgress.total_pages ? ` · página ${catalogProgress.page}/${catalogProgress.total_pages}` : (catalogProgress.page ? ` · página ${catalogProgress.page}` : '')}
                {catalogProgress.torrents ? ` · ${catalogProgress.torrents.toLocaleString('es-ES')} torrents` : ''}
                {catalogProgress.items ? ` · ${catalogProgress.items.toLocaleString('es-ES')} comparados` : ''}
                {catalogProgress.eta_seconds != null ? ` · ~${fmtEta(catalogProgress.eta_seconds)} restante` : ''}
              </div>
            </div>
          </div>
          {!catalogProgress.error && catalogProgress.total_pages ? (
            <div className="progress-bar" style={{ marginTop: 10 }}>
              <div className="progress-fill" style={{ width: `${Math.min(100, Math.round((catalogProgress.page / catalogProgress.total_pages) * 100))}%` }} />
            </div>
          ) : null}
        </div>
      )}

      {requestsSyncing && (
        <div className="activity-section" style={{ padding: '14px 18px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="spinner" style={{ width: 18, height: 18, borderWidth: 2 }} />
          <div style={{ fontWeight: 600 }}>Sincronizando peticiones…</div>
        </div>
      )}
    </>
  )
}
