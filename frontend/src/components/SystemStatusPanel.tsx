import { useEffect, useState } from 'react'
import { getSystemStats, type SystemStats } from '../api/system'
import { formatBytes } from '../utils/format'
import { Tooltip, useTooltip } from './Tooltip'

const POLL_MS = 4000
const RADIUS = 44
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

// The backend already reports *_gb as a float — feeding it back through
// formatBytes (which expects raw bytes) picks the right unit on its own
// (GB vs TB) instead of always printing "GB" even once it's really 5+ TB.
function formatGb(gb: number): string {
  return formatBytes(gb * 1024 ** 3)
}

function Gauge({ percent, label, color, title }: { percent: number; label: string; color: string; title?: string }) {
  const clamped = Math.max(0, Math.min(100, percent))
  const offset = CIRCUMFERENCE * (1 - clamped / 100)
  const { triggerProps, tooltipNode } = useTooltip(title ?? null)
  return (
    <div className="sys-gauge-row" {...triggerProps}>
      <div className="sys-gauge">
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r={RADIUS} className="sys-gauge-track" />
          <circle
            cx="50" cy="50" r={RADIUS} className="sys-gauge-fill"
            style={{ stroke: color, strokeDasharray: CIRCUMFERENCE, strokeDashoffset: offset }}
            transform="rotate(-90 50 50)"
          />
        </svg>
        <div className="sys-gauge-center">
          <div className="sys-gauge-pct">{Math.round(clamped)}%</div>
          <div className="sys-gauge-label">{label}</div>
        </div>
      </div>
      {tooltipNode}
    </div>
  )
}

// Collapsed sidebar (icon-only nav): the down/up throughput no longer fits
// as text side by side, so it collapses to a single icon whose tooltip
// carries both values — same reveal-on-hover pattern as the nav items.
function NetRow({ down, up, collapsed }: { down: number; up: number; collapsed: boolean }) {
  const { triggerProps, tooltipNode } = useTooltip(collapsed ? (
    <>
      <div>Velocidad de bajada: {formatBytes(down)}/s</div>
      <div>Velocidad de subida: {formatBytes(up)}/s</div>
    </>
  ) : null)
  if (collapsed) {
    return (
      <div className="sys-net-row collapsed" {...triggerProps}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 3v8M8 7l4-4 4 4" />
          <path d="M12 21v-8M8 17l4 4 4-4" />
        </svg>
        {tooltipNode}
      </div>
    )
  }
  return (
    <div className="sys-net-row">
      <Tooltip content="Velocidad de bajada">
        <span className="sys-net-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M6 13l6 6 6-6" /></svg>{formatBytes(down)}/s</span>
      </Tooltip>
      <Tooltip content="Velocidad de subida">
        <span className="sys-net-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 19V5M6 11l6-6 6 6" /></svg>{formatBytes(up)}/s</span>
      </Tooltip>
    </div>
  )
}

export function SystemStatusPanel({ collapsed = false }: { collapsed?: boolean }) {
  const [stats, setStats] = useState<SystemStats | null>(null)

  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    // A plain setInterval would fire the next poll even while the previous
    // one is still in flight — if the backend ever takes longer than
    // POLL_MS (e.g. a cold disk-path cache, see system_stats.py), several
    // requests pile up in parallel instead of one at a time. Scheduling the
    // next call only after the current one settles avoids that entirely.
    const load = () => {
      getSystemStats()
        .then(s => { if (alive) setStats(s) })
        .catch(() => { /* ignore — next tick retries */ })
        .finally(() => { if (alive) timer = setTimeout(load, POLL_MS) })
    }
    load()
    return () => { alive = false; if (timer) clearTimeout(timer) }
  }, [])

  if (!stats) return null

  return (
    <div data-tour="sidebar-gauges" className={`sys-status${collapsed ? ' collapsed' : ''}`}>
      <div className="sys-gauge-list">
        <Gauge percent={stats.cpu_percent} label="CPU" color="var(--hud-cyan)" title={stats.cpu_name} />
        <Gauge percent={stats.ram_percent} label="RAM" color="var(--hud-cyan)"
          title={`${formatGb(stats.ram_used_gb)} / ${formatGb(stats.ram_total_gb)}`} />
        <Gauge percent={stats.disk_percent} label="Disco" color="var(--hud-ice)"
          title={`Biblioteca: ${formatGb(stats.disk_used_gb)} / ${formatGb(stats.disk_total_gb)}`} />
        {stats.gpu && (
          <>
            <Gauge percent={stats.gpu.percent} label="GPU" color="var(--hud-cyan)" title={stats.gpu.name} />
            <Gauge percent={stats.gpu.vram_percent} label="VRAM" color="var(--hud-ice)"
              title={`${formatGb(stats.gpu.vram_used_gb)} / ${formatGb(stats.gpu.vram_total_gb)}`} />
          </>
        )}
      </div>
      <NetRow down={stats.net_down_bps} up={stats.net_up_bps} collapsed={collapsed} />
    </div>
  )
}
