import { posterUrl } from '../../utils/libraryItem'
import { IconoTipo } from '../Iconos'

// La carátula pequeña de una fila; sin imagen (o si no carga), el icono del tipo.
export function Cartel({ url, serie, pequeno = false }: { url: string | null | undefined; serie: boolean; pequeno?: boolean }) {
  return (
    <div className={`poster-thumb panel-poster${pequeno ? ' panel-poster-peq' : ''}`}>
      {url ? (
        <img
          src={posterUrl(url, 'w154')}
          alt=""
          loading="lazy"
          className="panel-poster-img"
          onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
        />
      ) : (
        <span className="panel-poster-icono"><IconoTipo serie={serie} /></span>
      )}
    </div>
  )
}
