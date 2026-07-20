import { useEffect, useState } from 'react'
import { getSystemStats, type SystemStats } from '../api/system'
import { formatBytes } from '../utils/format'
import { useTooltip } from './Tooltip'

const POLL_MS = 4000
const RADIUS = 17
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

function Gauge({ percent, label, color, title }: { percent: number; label: string; color: string; title?: string }) {
  const clamped = Math.max(0, Math.min(100, percent))
  const offset = CIRCUMFERENCE * (1 - clamped / 100)
  const { triggerProps, tooltipNode } = useTooltip(title ?? null)
  return (
    <div className="sys-gauge" {...triggerProps}>
      <svg viewBox="0 0 40 40">
        <circle cx="20" cy="20" r={RADIUS} className="sys-gauge-track" />
        <circle
          cx="20" cy="20" r={RADIUS} className="sys-gauge-fill"
          style={{ stroke: color, strokeDasharray: CIRCUMFERENCE, strokeDashoffset: offset }}
          transform="rotate(-90 20 20)"
        />
      </svg>
      <div className="sys-gauge-pct">{Math.round(clamped)}%</div>
      <div className="sys-gauge-label">{label}</div>
      {tooltipNode}
    </div>
  )
}

export function SystemStatusPanel() {
  const [stats, setStats] = useState<SystemStats | null>(null)

  useEffect(() => {
    let alive = true
    const load = () => getSystemStats().then(s => { if (alive) setStats(s) }).catch(() => { /* ignore — next tick retries */ })
    load()
    const t = setInterval(load, POLL_MS)
    return () => { alive = false; clearInterval(t) }
  }, [])

  if (!stats) return null

  return (
    <div className="sys-status">
      <div className="sys-status-title">System Status</div>
      <div className="sys-gauge-grid">
        <Gauge percent={stats.cpu_percent} label="CPU" color="var(--hud-cyan)" />
        <Gauge percent={stats.ram_percent} label="RAM" color="var(--hud-cyan)"
          title={`${stats.ram_used_gb.toFixed(1)} / ${stats.ram_total_gb.toFixed(1)} GB`} />
        <Gauge percent={stats.disk_percent} label="Disco" color="var(--hud-ice)"
          title={`Biblioteca: ${stats.disk_used_gb.toFixed(0)} / ${stats.disk_total_gb.toFixed(0)} GB`} />
        {stats.gpu && (
          <>
            <Gauge percent={stats.gpu.percent} label="GPU" color="var(--hud-cyan)" title={stats.gpu.name} />
            <Gauge percent={stats.gpu.vram_percent} label="VRAM" color="var(--hud-ice)"
              title={`${stats.gpu.vram_used_gb.toFixed(1)} / ${stats.gpu.vram_total_gb.toFixed(1)} GB`} />
          </>
        )}
      </div>
      <div className="sys-net-row">
        <span className="sys-net-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M6 13l6 6 6-6" /></svg>{formatBytes(stats.net_down_bps)}/s</span>
        <span className="sys-net-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 19V5M6 11l6-6 6 6" /></svg>{formatBytes(stats.net_up_bps)}/s</span>
      </div>
    </div>
  )
}
