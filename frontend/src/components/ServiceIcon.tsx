// ServiceIcon — SVG icons for Radarr, Sonarr, EMU, Uploadrr
// Must appear next to any Radarr/Sonarr text in tables or summaries.
//
// Not exact trademarked logo traces (no network/image access to fetch the
// official assets) — redesigned to match each project's real badge shape
// and brand color family so they read as "that service" at a glance:
//   Radarr = amber/gold circular radar-sweep badge (official Radarr color)
//   Sonarr = blue rounded-screen badge with broadcast/sonar waves

interface ServiceIconProps {
  type: 'radarr' | 'sonarr' | 'emu' | 'uploadrr'
  size?: number
}

export function ServiceIcon({ type, size = 16 }: ServiceIconProps) {
  const s = size

  if (type === 'radarr') {
    // Amber circular badge with a radar sweep + radiating blips.
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none" aria-label="Radarr">
        <circle cx="12" cy="12" r="10" fill="#f2a900" opacity="0.16" />
        <circle cx="12" cy="12" r="10" stroke="#f2a900" strokeWidth="1.2" opacity="0.5" fill="none" />
        <circle cx="12" cy="12" r="6.5" stroke="#f2a900" strokeWidth="1.2" opacity="0.7" fill="none" />
        <circle cx="12" cy="12" r="2.4" fill="#ffc230" />
        <path d="M12 12 L18 5.5" stroke="#ffc230" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="16.2" cy="8.8" r="1" fill="#ffc230" opacity="0.85" />
      </svg>
    )
  }

  if (type === 'sonarr') {
    // Blue rounded-screen badge with broadcast/sonar waves.
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none" aria-label="Sonarr">
        <rect x="3" y="3" width="18" height="18" rx="6" fill="#1f6fd6" opacity="0.14" />
        <rect x="3" y="3" width="18" height="18" rx="6" stroke="#1f6fd6" strokeWidth="1.2" opacity="0.5" fill="none" />
        <circle cx="12" cy="14.5" r="1.8" fill="#35a7f4" />
        <path d="M8.3 11a5.2 5.2 0 0 1 7.4 0" stroke="#35a7f4" strokeWidth="1.6" strokeLinecap="round" fill="none" opacity="0.85" />
        <path d="M6 8.3a8.5 8.5 0 0 1 12 0" stroke="#35a7f4" strokeWidth="1.6" strokeLinecap="round" fill="none" opacity="0.5" />
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
