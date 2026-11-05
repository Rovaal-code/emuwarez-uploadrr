import { useId } from 'react'

// El marco de un carril del Panel: título, una nota a su derecha (y, si la hay, una acción tras ella) y el cuerpo,
// que se desplaza por dentro. `pie` va debajo del cuerpo, fuera del desplazamiento: siempre a la vista.
export function Carril({ titulo, nota, tour, accion, pie, children }: {
  titulo: string; nota?: string; tour?: string; accion?: React.ReactNode; pie?: React.ReactNode
  children: React.ReactNode
}) {
  const id = useId()
  const notaEl = nota && <span className="panel-carril-nota">{nota}</span>
  return (
    <section className="upload-panel panel-bloque panel-carril" aria-labelledby={id} data-tour={tour}>
      <div className="section-header">
        <h2 className="section-title" id={id}>{titulo}</h2>
        {accion ? <div className="panel-carril-fin">{notaEl}{accion}</div> : notaEl}
      </div>
      <div className="upload-panel-body">{children}</div>
      {pie}
    </section>
  )
}
