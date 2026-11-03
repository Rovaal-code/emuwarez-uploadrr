import { useSync } from '../context/SyncContext'
import { ServiceIcon } from './ServiceIcon'
import { useTooltip } from './Tooltip'

// "1m 20s" / "45s" for the eMuwarez ETA.
function fmtEta(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

// Rendered inside the topbar's reserved sync row (see Topbar.tsx), so a sync
// started on any tab shows the same live status everywhere without ever
// pushing the page content down — the topbar's height never changes whether
// this is empty or full.
export function SyncProgressBanner() {
  const {
    libProgress, catalogProgress, requestsSyncing, requestsProgress,
    message, messageIsError, messageFadingOut,
  } = useSync()
  if (!libProgress && !catalogProgress && !requestsSyncing && !message) return null

  return (
    <div className="topbar-sync-row">
      {message && (
        <div className={`sync-toast${messageIsError ? ' sync-toast-error' : ' sync-toast-ok'}${messageFadingOut ? ' sync-toast-fading' : ''}`}>
          {message}
        </div>
      )}

      {libProgress && (
        <SyncChip
          error={libProgress.error}
          icon={(libProgress.instance_type === 'radarr' || libProgress.instance_type === 'sonarr')
            ? <ServiceIcon type={libProgress.instance_type} size={13} /> : null}
          label="Biblioteca"
          detail={libProgress.error ?? [
            libProgress.instance,
            libProgress.total
              ? `${libProgress.imported.toLocaleString('es-ES')}/${libProgress.total.toLocaleString('es-ES')}`
              : `${libProgress.imported.toLocaleString('es-ES')} elementos`,
            libProgress.missing ? `${libProgress.missing.toLocaleString('es-ES')} no disponibles` : null,
          ].filter(Boolean).join('; ')}
          percent={!libProgress.error && libProgress.total ? Math.min(100, Math.round((libProgress.imported / libProgress.total) * 100)) : null}
          bar
        />
      )}

      {catalogProgress && (
        <SyncChip
          error={catalogProgress.error}
          icon={<ServiceIcon type="emu" size={13} />}
          label="eMuwarez"
          detail={catalogProgress.error ?? [
            catalogProgress.total_pages
              ? `pág. ${catalogProgress.page}/${catalogProgress.total_pages}`
              // Total pages isn't known yet (still waiting on page 1's own
              // response) — the torrent count is real progress too, and
              // showing it beats a bar that looks frozen with no text at all.
              // Before even that (still on the pre-flight check, or between
              // phases), fall back to the phase label itself — so the chip
              // never shows literally nothing while something is happening.
              : catalogProgress.torrents ? `${catalogProgress.torrents} torrents` : catalogProgress.phase || null,
            catalogProgress.eta_seconds != null ? `~${fmtEta(catalogProgress.eta_seconds)}` : null,
          ].filter(Boolean).join('; ')}
          percent={!catalogProgress.error && catalogProgress.total_pages
            ? Math.min(100, Math.round((catalogProgress.page / catalogProgress.total_pages) * 100)) : null}
          bar
        />
      )}

      {requestsSyncing && (
        <SyncChip
          error={null}
          icon={<ServiceIcon type="emu" size={13} />}
          label="Peticiones"
          // Mientras baja las páginas, la página; después, lo que está haciendo (cruzar, preparar, pósters).
          detail={requestsProgress
            ? (requestsProgress.phase.startsWith('Descargando') && requestsProgress.total_pages
              ? `pág. ${requestsProgress.page}/${requestsProgress.total_pages}` : requestsProgress.phase)
            : 'Sincronizando…'}
          percent={requestsProgress?.total_pages
            ? Math.min(100, Math.round((requestsProgress.page / requestsProgress.total_pages) * 100)) : 0}
          bar
        />
      )}
    </div>
  )
}

function SyncChip({ error, icon, label, detail, percent, bar }: {
  error: string | null | undefined
  icon: React.ReactNode
  label: string
  detail: string
  percent: number | null
  // Reserve the bar's width from the very first render (at 0%) for metrics
  // that will eventually report a percent, so the chip doesn't visibly
  // widen/shift once the real total lands a tick later — it used to render
  // icon+label alone at first, then insert the bar, which re-centers
  // .topbar-center's content and reads as everything jumping left.
  bar: boolean
}) {
  const { triggerProps, tooltipNode } = useTooltip(`${label}${detail ? ` · ${detail}` : ''}`)
  return (
    <div className="sync-chip" {...triggerProps}>
      {error
        ? <span className="sync-chip-error">✗</span>
        : <span className="spinner emusync-spinner" />}
      {icon}
      <span className="sync-chip-label">{label}</span>
      <span className={`sync-chip-detail${error ? ' sync-chip-detail-error' : ''}`}>{detail}</span>
      {bar && (
        <div className="sync-chip-bar">
          <div className="sync-chip-bar-fill" style={{ transform: `scaleX(${(percent ?? 0) / 100})` }} />
        </div>
      )}
      {tooltipNode}
    </div>
  )
}
