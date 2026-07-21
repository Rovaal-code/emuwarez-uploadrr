// ServiceIcon — SVG icons for Radarr, Sonarr, EMU, Uploadrr
// Must appear next to any Radarr/Sonarr text in tables or summaries.
//
// Radarr/Sonarr use the real official marks, fetched directly from
// github.com/Radarr/Radarr and github.com/Sonarr/Sonarr (Logo/ folders).
// Radarr specifically uses their "Simple-Logo-Dark" variant
// (frontend/src/Content/Images/logo.svg in their repo) — the ribbon is
// white instead of charcoal, which is the variant Radarr's own project
// ships for dark backgrounds like this app's theme. Sonarr's mark already
// reads fine on dark as-is (light ring + navy + cyan). Neither needs a
// background chip behind it.

interface ServiceIconProps {
  type: 'radarr' | 'sonarr' | 'emu' | 'uploadrr' | 'discord' | 'telegram' | 'qbittorrent' | 'imghost' | 'tmdb'
  size?: number
}

export function ServiceIcon({ type, size = 16 }: ServiceIconProps) {
  const s = size

  if (type === 'tmdb') {
    // The Movie DB's real brand mark: rounded square with their teal→blue
    // gradient and the two-bar logo.
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" aria-label="TMDb">
        <defs>
          <linearGradient id="tmdbGrad" x1="0" y1="0" x2="24" y2="0" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#90cea1" />
            <stop offset="0.56" stopColor="#3cbec9" />
            <stop offset="1" stopColor="#00b3e5" />
          </linearGradient>
        </defs>
        <rect x="1" y="1" width="22" height="22" rx="5" fill="url(#tmdbGrad)" />
        <rect x="5" y="8" width="14" height="3.1" rx="1.55" fill="#0d253f" />
        <rect x="5" y="12.9" width="9" height="3.1" rx="1.55" fill="#0d253f" />
      </svg>
    )
  }

  if (type === 'radarr') {
    return (
      <svg width={s} height={s} viewBox="0 0 1024 1025" aria-label="Radarr">
        <g transform="translate(70 18)">
          <path d="M105.302 156.117L112.824 876.083C52.6511 883.662 7.52159 853.347 7.52159 792.719L0 194.01C0 4.54526 172.997 -40.9263 278.299 34.8596L812.332 345.582C887.548 398.632 902.591 497.154 864.983 565.361C857.461 512.311 834.897 481.996 789.767 451.682L188.04 110.646C142.91 80.3311 105.302 87.9097 105.302 156.117Z" fill="#FFFFFF" />
          <path d="M0 378.929C45.1296 394.087 90.2591 386.508 127.867 363.772L744.638 0C782.245 53.0501 774.724 106.1 729.594 136.415L210.605 439.558C135.389 477.451 37.608 439.558 0 378.929Z" transform="translate(60.1727 535.046)" fill="#FFFFFF" />
          <path d="M0 416.822L368.558 204.622L7.52159 0L0 416.822Z" transform="translate(240.6909 284.953)" fill="#FFC230" />
        </g>
      </svg>
    )
  }

  if (type === 'sonarr') {
    return (
      <svg width={s} height={s} viewBox="0 0 216.7 216.9" aria-label="Sonarr">
        <path clipRule="evenodd" d="M216.7 108.45c0 29.833-10.533 55.4-31.6 76.7-.7.833-1.483 1.6-2.35 2.3-3.466 3.4-7.133 6.484-11 9.25-18.267 13.467-39.367 20.2-63.3 20.2-23.967 0-45.033-6.733-63.2-20.2-4.8-3.4-9.3-7.25-13.5-11.55-16.367-16.266-26.417-35.167-30.15-56.7-.733-4.2-1.217-8.467-1.45-12.8-.1-2.4-.15-4.8-.15-7.2 0-2.533.05-4.95.15-7.25 0-.233.066-.467.2-.7 1.567-26.6 12.033-49.583 31.4-68.95C53.05 10.517 78.617 0 108.45 0c29.933 0 55.484 10.517 76.65 31.55 21.067 21.433 31.6 47.067 31.6 76.9z" fill="#EEE" fillRule="evenodd" />
        <path clipRule="evenodd" d="M194.65 42.5l-22.4 22.4C159.152 77.998 158 89.4 158 109.5c0 17.934 2.852 34.352 16.2 47.7 9.746 9.746 19 18.95 19 18.95-2.5 3.067-5.2 6.067-8.1 9-.7.833-1.483 1.6-2.35 2.3-2.533 2.5-5.167 4.817-7.9 6.95l-17.55-17.55c-15.598-15.6-27.996-17.1-48.6-17.1-19.77 0-33.223 1.822-47.7 16.3-8.647 8.647-18.55 18.6-18.55 18.6-3.767-2.867-7.333-6.034-10.7-9.5-2.8-2.8-5.417-5.667-7.85-8.6 0 0 9.798-9.848 19.15-19.2 13.852-13.853 16.1-29.916 16.1-47.85 0-17.5-2.874-33.823-15.6-46.55-8.835-8.836-21.05-21-21.05-21 2.833-3.6 5.917-7.067 9.25-10.4 2.934-2.867 5.934-5.55 9-8.05L61.1 43.85C74.102 56.852 90.767 60.2 108.7 60.2c18.467 0 35.077-3.577 48.6-17.1 8.32-8.32 19.3-19.25 19.3-19.25 2.9 2.367 5.733 4.933 8.5 7.7 3.467 3.533 6.65 7.183 9.55 10.95z" fill="#3A3F51" fillRule="evenodd" />
        <g clipRule="evenodd">
          <path d="M78.7 114c-.2-1.167-.332-2.35-.4-3.55-.032-.667-.05-1.333-.05-2 0-.7.018-1.367.05-2 0-.067.018-.133.05-.2.435-7.367 3.334-13.733 8.7-19.1 5.9-5.833 12.984-8.75 21.25-8.75 8.3 0 15.384 2.917 21.25 8.75 5.834 5.934 8.75 13.033 8.75 21.3 0 8.267-2.916 15.35-8.75 21.25-.2.233-.416.45-.65.65-.966.933-1.982 1.783-3.05 2.55-5.065 3.733-10.916 5.6-17.55 5.6s-12.466-1.866-17.5-5.6c-1.332-.934-2.582-2-3.75-3.2-4.532-4.5-7.316-9.734-8.35-15.7z" fill="#0CF" fillRule="evenodd" />
          <path d="M157.8 59.75l-15 14.65M30.785 32.526L71.65 73.25m84.6 84.25l27.808 28.78m1.855-153.894L157.8 59.75m-125.45 126l27.35-27.4" fill="none" stroke="#0CF" strokeMiterlimit={1} strokeWidth={2} />
          <path d="M157.8 59.75l-16.95 17.2M58.97 60.604l17.2 17.15M59.623 158.43l16.75-17.4m61.928-1.396l18.028 17.945" fill="none" stroke="#0CF" strokeMiterlimit={1} strokeWidth={7} />
        </g>
      </svg>
    )
  }

  if (type === 'emu') {
    // Stylized E — HUD cyan, matching the app's own holographic signature banner.
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none" aria-label="eMuwarez">
        <rect x="4" y="4" width="16" height="16" rx="4" fill="#2fd8ff" opacity="0.15" />
        <path d="M8 7h8M8 12h6M8 17h8" stroke="#2fd8ff" strokeWidth="2" strokeLinecap="round" />
      </svg>
    )
  }

  if (type === 'discord') {
    return (
      <svg width={s} height={s} viewBox="0 0 127.14 96.36" aria-label="Discord">
        <path
          fill="#5865F2"
          d="M107.7,8.07A105.15,105.15,0,0,0,81.47,0a72.06,72.06,0,0,0-3.36,6.83A97.68,97.68,0,0,0,49,6.83,72.37,72.37,0,0,0,45.64,0,105.89,105.89,0,0,0,19.39,8.09C2.79,32.65-1.71,56.6.54,80.21h0A105.73,105.73,0,0,0,32.71,96.36,77.7,77.7,0,0,0,39.6,85.25a68.42,68.42,0,0,1-10.85-5.18c.91-.66,1.8-1.34,2.66-2a75.57,75.57,0,0,0,64.32,0c.87.71,1.76,1.39,2.66,2a68.68,68.68,0,0,1-10.87,5.19,77,77,0,0,0,6.89,11.1A105.25,105.25,0,0,0,126.6,80.22h0C129.24,52.84,122.09,29.11,107.7,8.07ZM42.45,65.69C36.18,65.69,31,60,31,53s5-12.74,11.43-12.74S54,46,53.89,53,48.84,65.69,42.45,65.69Zm42.24,0C78.41,65.69,73.25,60,73.25,53s5-12.74,11.44-12.74S96.23,46,96.12,53,91.08,65.69,84.69,65.69Z"
        />
      </svg>
    )
  }

  if (type === 'telegram') {
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" aria-label="Telegram">
        <circle cx="12" cy="12" r="12" fill="#29B6F6" />
        <path
          fill="#FFF"
          d="M16.906 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"
        />
      </svg>
    )
  }

  if (type === 'qbittorrent') {
    // qBittorrent official mark: light-blue rounded gauge with the "6" needle.
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" aria-label="qBittorrent">
        <circle cx="12" cy="12" r="11" fill="#3771C8" />
        <path d="M12 3.2A8.8 8.8 0 0 0 3.2 12H6a6 6 0 0 1 6-6z" fill="#FFFFFF" opacity="0.55" />
        <path
          d="M12 6.5A5.5 5.5 0 1 0 17.5 12H14.6A2.6 2.6 0 1 1 12 9.4z"
          fill="#FFFFFF"
        />
        <circle cx="12" cy="12" r="1.5" fill="#FFFFFF" />
      </svg>
    )
  }

  if (type === 'imghost') {
    // Generic image-host icon (photo frame with mountains + sun).
    return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none" aria-label="Image host">
        <rect x="3" y="4" width="18" height="16" rx="3" fill="#8b5cf6" opacity="0.15" stroke="#8b5cf6" strokeWidth="1.5" />
        <circle cx="8.5" cy="9" r="1.6" fill="#8b5cf6" />
        <path d="M5 17l4.5-4.5L13 16l2.5-2.5L19 17" stroke="#8b5cf6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
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
