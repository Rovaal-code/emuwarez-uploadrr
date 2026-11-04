// Barra pegada al borde inferior de Configuración mientras hay campos sin guardar.
export function BarraGuardado({ cambios, guardando, onGuardar }: {
  cambios: number
  guardando: boolean
  onGuardar: () => void
}) {
  return (
    <div className="aj-guardado">
      <span role="status" className="aj-guardado__cuenta">
        {cambios === 1 ? '1 campo ha cambiado' : `${cambios} campos han cambiado`}
      </span>
      <button type="button" className="btn btn-primary btn-sm" onClick={onGuardar} disabled={guardando}>
        {guardando ? 'Guardando…' : 'Guardar'}
      </button>
    </div>
  )
}
