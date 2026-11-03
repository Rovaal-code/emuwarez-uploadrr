import { useEffect, useState } from 'react'
import { getSystemStats, type SystemStats } from '../api/system'
import { formatBytes } from '../utils/format'
import { Tooltip, useTooltip } from './Tooltip'

const POLL_MS = 4000

// The backend already reports *_gb as a float — feeding it back through
// formatBytes (which expects raw bytes) picks the right unit on its own
// (GB vs TB) instead of always printing "GB" even once it's really 5+ TB.
function formatGb(gb: number): string {
  return formatBytes(gb * 1024 ** 3)
}

// Sin dato (nulo o no finito) no se pinta un 0 %, que diría "vacío".
function porcentaje(valor: number | null | undefined): string | null {
  if (typeof valor !== 'number' || !Number.isFinite(valor)) return null
  return `${Math.round(Math.max(0, Math.min(100, valor)))}%`
}

function Medida({ nombre, valor, detalle }: { nombre: string; valor: string | null; detalle: React.ReactNode }) {
  const { triggerProps, tooltipNode } = useTooltip(detalle)
  return (
    <li className="sys-med" tabIndex={0} aria-label={`${nombre} ${valor ?? 'sin datos'}`} {...triggerProps}>
      <span className="sys-med-nombre">{nombre}</span> <span className="sys-med-valor">{valor ?? '—'}</span>
      {tooltipNode}
    </li>
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
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
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
        <span className="sys-net-item"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M6 13l6 6 6-6" /></svg>{formatBytes(down)}/s</span>
      </Tooltip>
      <Tooltip content="Velocidad de subida">
        <span className="sys-net-item"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 19V5M6 11l6-6 6 6" /></svg>{formatBytes(up)}/s</span>
      </Tooltip>
    </div>
  )
}

// Una sola línea al pie de la barra: el valor de cada medida y, en su tooltip, el detalle.
export function ResumenSistema({ stats, collapsed = false }: { stats: SystemStats; collapsed?: boolean }) {
  const discoLeible = stats.disk_total_gb > 0
  return (
    <div data-tour="sidebar-gauges" className={`sys-status${collapsed ? ' collapsed' : ''}`}>
      <ul className="sys-med-lista" aria-label="Uso de recursos">
        <Medida nombre="CPU" valor={porcentaje(stats.cpu_percent)} detalle={stats.cpu_name || null} />
        <Medida nombre="RAM" valor={porcentaje(stats.ram_percent)}
          detalle={`${formatGb(stats.ram_used_gb)} / ${formatGb(stats.ram_total_gb)}`} />
        <Medida nombre="Disco" valor={discoLeible ? porcentaje(stats.disk_percent) : null}
          detalle={discoLeible ? (
            <>
              <div>{formatGb(stats.disk_used_gb)} / {formatGb(stats.disk_total_gb)}</div>
              <div>{stats.disk_path}</div>
            </>
          ) : 'No se pudo medir el disco'} />
        {stats.gpu && <Medida nombre="GPU" valor={porcentaje(stats.gpu.percent)} detalle={stats.gpu.name} />}
        {stats.gpu && <Medida nombre="VRAM" valor={porcentaje(stats.gpu.vram_percent)}
          detalle={`${formatGb(stats.gpu.vram_used_gb)} / ${formatGb(stats.gpu.vram_total_gb)}`} />}
      </ul>
      <NetRow down={stats.net_down_bps} up={stats.net_up_bps} collapsed={collapsed} />
    </div>
  )
}

export function SystemStatusPanel({ collapsed = false }: { collapsed?: boolean }) {
  const [stats, setStats] = useState<SystemStats | null>(null)

  // Este sondeo se queda, y es a propósito: es el único que no se pasó a
  // avisos del servidor (services/eventos.py). CPU, RAM y disco no "cambian"
  // en ningún instante concreto — se miden cuando alguien mira. No hay nada
  // que el servidor pueda anunciar salvo "ha pasado un rato", que es
  // exactamente lo que ya hace un temporizador y más barato.
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
  return <ResumenSistema stats={stats} collapsed={collapsed} />
}
