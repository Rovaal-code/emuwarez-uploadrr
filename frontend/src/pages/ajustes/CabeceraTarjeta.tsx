import type { ReactNode } from 'react'

// La cabecera de toda tarjeta de Configuración: icono, título, lo que lo acompaña a la derecha (un estado, un botón) y,
// debajo, una línea que dice para qué sirve. El título es un h3: el buscador de Configuración lee los h3 y las etiquetas.
export function CabeceraTarjeta({ icono, titulo, info, lateral, descripcion }: {
  icono?: ReactNode
  titulo: ReactNode
  info?: ReactNode
  lateral?: ReactNode
  descripcion?: ReactNode
}) {
  return (
    <header className="aj-cab">
      <div className="aj-cab__fila">
        <h3 className="aj-cab__titulo">
          {icono && <span className="aj-cab__icono" aria-hidden>{icono}</span>}
          {titulo}
          {info}
        </h3>
        {lateral && <div className="aj-cab__lateral">{lateral}</div>}
      </div>
      {descripcion && <p className="aj-cab__desc">{descripcion}</p>}
    </header>
  )
}
