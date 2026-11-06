import { Tooltip } from './Tooltip'

export type ModoDeVista = 'grid' | 'grid-lg' | 'list'

const OPCIONES: { modo: ModoDeVista; nombre: string; icono: React.ReactNode }[] = [
  {
    modo: 'grid', nombre: 'Vista de pósters',
    icono: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  },
  {
    modo: 'grid-lg', nombre: 'Vista de pósters grandes',
    icono: <><rect x="3" y="3" width="8" height="18" rx="1.5" /><rect x="14" y="3" width="7" height="18" rx="1.5" /></>,
  },
  {
    modo: 'list', nombre: 'Vista de lista',
    icono: <><path d="M8 6h13M8 12h13M8 18h13" /><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01" /></>,
  },
]

/** Los tres modos de ver Biblioteca como un solo control: el que está puesto se ve encendido y los demás, apagados. */
export function SelectorDeVista({ modo, onCambiar }: { modo: ModoDeVista; onCambiar: (m: ModoDeVista) => void }) {
  return (
    <div className="bib-vistas" role="group" aria-label="Cómo ver la biblioteca">
      {OPCIONES.map(o => (
        <Tooltip key={o.modo} content={o.nombre}>
          <button
            type="button"
            className={`bib-vista-boton${modo === o.modo ? ' activa' : ''}`}
            onClick={() => onCambiar(o.modo)}
            aria-label={o.nombre}
            aria-pressed={modo === o.modo}
          >
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
              {o.icono}
            </svg>
          </button>
        </Tooltip>
      ))}
    </div>
  )
}
