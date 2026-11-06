import { posterUrl } from '../../utils/libraryItem'
import { IconoTipo } from '../Iconos'

// La carátula de una fila; sin imagen (o si no carga), el icono del tipo.
export function Cartel({ url, serie }: { url: string | null | undefined; serie: boolean }) {
  return (
    <div className="poster-thumb panel-poster">
      {url ? (
        <img
          src={posterUrl(url, 'w154')}
          alt=""
          width={44}
          height={66}
          loading="lazy"
          decoding="async"
          className="panel-poster-img"
          onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
        />
      ) : (
        <span className="panel-poster-icono"><IconoTipo serie={serie} /></span>
      )}
    </div>
  )
}
