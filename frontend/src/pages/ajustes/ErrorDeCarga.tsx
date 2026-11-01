// Fallo al leer los ajustes. Quien lo enseña no pinta su formulario: con los valores por defecto,
// guardar escribiría encima de los reales.
export function ErrorDeCarga({ mensaje, onReintentar }: { mensaje: string; onReintentar: () => void }) {
  return (
    <div>
      <p className="aj-err-13 aj-mt-0 aj-mb-10">✗ {mensaje}</p>
      <button className="btn btn-secondary btn-sm" type="button" onClick={onReintentar}>Reintentar</button>
    </div>
  )
}
