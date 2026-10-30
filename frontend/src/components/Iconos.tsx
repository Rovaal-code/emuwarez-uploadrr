// Iconos de línea para los sitios donde antes había un emoji (📺 🎬 ⚠ ⛔...).
// Mismo trazo que los de la barra lateral y el Panel: heredan el color del
// texto (currentColor) y miden 1em por defecto, así que crecen con el
// font-size de donde se pongan (un aviso en una línea de texto, el hueco de un
// póster sin imagen). Son decorativos: el texto de al lado ya dice lo mismo,
// por eso van con aria-hidden.

interface IconoProps {
  size?: number | string
  style?: React.CSSProperties
}

function Svg({ size = '1em', style, children }: IconoProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ flexShrink: 0, verticalAlign: '-0.125em', ...style }}
    >
      {children}
    </svg>
  )
}

export function IconoSerie(props: IconoProps) {
  return <Svg {...props}><rect x="3" y="6" width="18" height="12" rx="2" /><path d="M8 21h8M12 18v3M8.5 2.5 12 6l3.5-3.5" /></Svg>
}

export function IconoPelicula(props: IconoProps) {
  return <Svg {...props}><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M7.5 3v18M16.5 3v18M3 7.5h4.5M3 12h18M3 16.5h4.5M16.5 7.5H21M16.5 16.5H21" /></Svg>
}

export function IconoDocumental(props: IconoProps) {
  return <Svg {...props}><rect x="2" y="6" width="14" height="12" rx="2" /><path d="m22 8-6 4 6 4z" /></Svg>
}

/** Serie (o temporada o capítulo) frente a película: el hueco del póster. */
export function IconoTipo({ serie, ...props }: IconoProps & { serie: boolean }) {
  return serie ? <IconoSerie {...props} /> : <IconoPelicula {...props} />
}

export function IconoAviso(props: IconoProps) {
  return <Svg {...props}><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></Svg>
}

export function IconoCerrar(props: IconoProps) {
  return <Svg {...props}><path d="M18 6 6 18M6 6l12 12" /></Svg>
}

export function IconoBloqueado(props: IconoProps) {
  return <Svg {...props}><circle cx="12" cy="12" r="9" /><path d="m5.6 5.6 12.8 12.8" /></Svg>
}

export function IconoBandeja(props: IconoProps) {
  return <Svg {...props}><path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z" /></Svg>
}

export function IconoEstrella(props: IconoProps) {
  return <Svg {...props}><path d="m12 3 2.7 5.6 6.1.8-4.5 4.2 1.1 6.1L12 16.8l-5.4 2.9 1.1-6.1-4.5-4.2 6.1-.8z" /></Svg>
}

export function IconoLista(props: IconoProps) {
  return <Svg {...props}><rect x="8" y="2" width="8" height="4" rx="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2M9 12h6M9 16h4" /></Svg>
}

export function IconoDocumento(props: IconoProps) {
  return <Svg {...props}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h5" /></Svg>
}

export function IconoEnchufe(props: IconoProps) {
  return <Svg {...props}><path d="M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0zM12 17v5" /></Svg>
}

export function IconoLibros(props: IconoProps) {
  return <Svg {...props}><path d="M4 19V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14" /><path d="M4 19h16M8 7h8M8 11h5" /></Svg>
}

export function IconoSubida(props: IconoProps) {
  return <Svg {...props}><path d="M12 15V3M7 8l5-5 5 5" /><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" /></Svg>
}

/** La cuenta: el mismo en la barra superior, en Configuración y en el asistente. */
export function IconoUsuario(props: IconoProps) {
  return <Svg {...props}><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></Svg>
}

/** El orden de una columna: un triángulo hacia arriba o hacia abajo, centrado como el ▼ de los filtros, o los dos si no ordena por ella. */
export function IconoOrden({ sentido, ...props }: IconoProps & { sentido: 'asc' | 'desc' | null }) {
  const forma = sentido === 'asc' ? 'M12 8 19 16H5z' : sentido === 'desc' ? 'M12 16 5 8h14z' : 'M12 3 19 11H5zM12 21 5 13h14z'
  return <Svg {...props}><path d={forma} fill="currentColor" stroke="none" /></Svg>
}

/** El desplegable: apunta a la derecha cerrado y hacia abajo abierto. */
export function IconoDesplegar({ abierto, ...props }: IconoProps & { abierto: boolean }) {
  return <Svg {...props} style={{ transform: abierto ? 'rotate(90deg)' : undefined, ...props.style }}><path d="m9 6 6 6-6 6" /></Svg>
}
