// ServiceIcon — SVG icons for Radarr, Sonarr, EMU, Uploadrr
// Must appear next to any Radarr/Sonarr text in tables or summaries

interface ServiceIconProps {
  type: 'radarr' | 'sonarr' | 'emu' | 'uploadrr'
  size?: number
}

export function ServiceIcon({ type, size = 16 }: ServiceIconProps) {
  const s = size

  if (type === 'radarr') {
    // Radar/sonar circles — orange
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none" aria-label="Radarr">
        <circle cx="12" cy="12" r="2.5" fill="#f97316" />
        <circle cx="12" cy="12" r="6" stroke="#f97316" strokeWidth="1.5" strokeOpacity="0.6" fill="none" />
        <circle cx="12" cy="12" r="10" stroke="#f97316" strokeWidth="1" strokeOpacity="0.3" fill="none" />
        <line x1="12" y1="12" x2="18" y2="6" stroke="#f97316" strokeWidth="1.5" strokeLinecap="round" opacity="0.8" />
      </svg>
    )
  }

  if (type === 'sonarr') {
    // Antenna/broadcast waves — blue
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none" aria-label="Sonarr">
        <circle cx="12" cy="14" r="2" fill="#3b82f6" />
        <path d="M8 10.5a5.5 5.5 0 0 1 8 0" stroke="#3b82f6" strokeWidth="1.5" strokeLinecap="round" fill="none" opacity="0.7" />
        <path d="M5.5 7.5a9 9 0 0 1 13 0" stroke="#3b82f6" strokeWidth="1.5" strokeLinecap="round" fill="none" opacity="0.4" />
        <line x1="12" y1="16" x2="12" y2="20" stroke="#3b82f6" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="9" y1="20" x2="15" y2="20" stroke="#3b82f6" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    )
  }

  if (type === 'emu') {
    // Stylized E — purple/blue
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none" aria-label="eMuwarez">
        <rect x="4" y="4" width="16" height="16" rx="4" fill="#6366f1" opacity="0.15" />
        <path d="M8 7h8M8 12h6M8 17h8" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" />
      </svg>
    )
  }

  // uploadrr — arrow up in box
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" aria-label="Uploadrr">
      <rect x="3" y="3" width="18" height="18" rx="4" stroke="#22c55e" strokeWidth="1.5" fill="none" opacity="0.5" />
      <path d="M12 16V9M9 12l3-3 3 3" stroke="#22c55e" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// Inline helper: icon + text
interface ServiceLabelProps {
  type: 'radarr' | 'sonarr' | 'emu' | 'uploadrr' | string
  label?: string
  size?: number
}

export function ServiceLabel({ type, label, size = 14 }: ServiceLabelProps) {
  const iconType = (['radarr', 'sonarr', 'emu', 'uploadrr'].includes(type)
    ? type
    : null) as 'radarr' | 'sonarr' | 'emu' | 'uploadrr' | null

  return (
    <span className="service-inline">
      {iconType && <ServiceIcon type={iconType} size={size} />}
      <span>{label ?? type}</span>
    </span>
  )
}
