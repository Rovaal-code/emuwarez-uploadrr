import type { ReactNode } from 'react'

// Sección plegable para lo que casi nunca hace falta tocar. El contenido sigue montado al plegarla, así que
// los campos conservan lo escrito.
export function SeccionAvanzado({ abierta, onAlternar, children }: {
  abierta: boolean
  onAlternar: () => void
  children: ReactNode
}) {
  return (
    <div className="aj-avanzado">
      <button
        type="button"
        className="aj-avanzado__cabecera"
        aria-expanded={abierta}
        aria-controls="aj-avanzado-cuerpo"
        onClick={onAlternar}
      >
        <span className="aj-avanzado__flecha" aria-hidden>{abierta ? '▾' : '▸'}</span>
        Avanzado
        <span className="form-hint">Rutas de acceso a la biblioteca</span>
      </button>
      <div id="aj-avanzado-cuerpo" className="aj-avanzado__cuerpo" hidden={!abierta}>
        {children}
      </div>
    </div>
  )
}
