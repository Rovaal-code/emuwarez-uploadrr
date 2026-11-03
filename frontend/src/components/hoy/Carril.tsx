import { useId } from 'react'

// El marco de un carril de «Hoy»: título, una nota a su derecha y el cuerpo, que se desplaza por dentro.
export function Carril({ titulo, nota, tour, children }: {
  titulo: string; nota?: string; tour?: string; children: React.ReactNode
}) {
  const id = useId()
  return (
    <section className="upload-panel panel-bloque panel-carril" aria-labelledby={id} data-tour={tour}>
      <div className="section-header">
        <h2 className="section-title" id={id}>{titulo}</h2>
        {nota && <span className="panel-carril-nota">{nota}</span>}
      </div>
      <div className="upload-panel-body">{children}</div>
    </section>
  )
}
