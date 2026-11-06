// Barra pegada al borde inferior de Configuración mientras hay cambios sin guardar. Cuenta lo que ha cambiado, deja
// descartarlo (si quien la usa sabe volver a lo guardado) y guarda.
export function BarraGuardado({ resumen, etiqueta = 'Guardar', guardando, deshabilitado, onGuardar, onDescartar }: {
  resumen: string
  etiqueta?: string
  guardando: boolean
  deshabilitado?: boolean
  onGuardar: () => void
  onDescartar?: () => void
}) {
  return (
    <div className="aj-guardado">
      <span role="status" className="aj-guardado__cuenta">{resumen}</span>
      <div className="aj-guardado__acciones">
        {onDescartar && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={onDescartar} disabled={guardando}>
            Descartar
          </button>
        )}
        <button type="button" className="btn btn-primary btn-sm" onClick={onGuardar} disabled={guardando || deshabilitado}>
          {guardando ? 'Guardando…' : etiqueta}
        </button>
      </div>
    </div>
  )
}
