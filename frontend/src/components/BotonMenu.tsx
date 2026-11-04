import type { Ref } from 'react'

interface BotonMenuProps {
  abierto: boolean
  onAlternar: () => void
  botonRef?: Ref<HTMLButtonElement>
}

// Solo se ve en ventanas estrechas (layout.css), donde la barra lateral es un cajón.
export function BotonMenu({ abierto, onAlternar, botonRef }: BotonMenuProps) {
  return (
    <button
      type="button"
      ref={botonRef}
      className="topbar-btn boton-menu"
      onClick={onAlternar}
      aria-expanded={abierto}
      aria-controls="menu-lateral"
      aria-label="Menú"
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" aria-hidden="true">
        <path d="M4 7h16M4 12h16M4 17h16" />
      </svg>
    </button>
  )
}
