// El póster de la ficha de una petición o de una subida: de ancho fijo y proporción 2:3, para que la ficha dé el sitio
// al contenido y no al cartel. (Biblioteca sigue con el grande, DetailPoster.)
export function FichaPoster({ url, alt, fallbackIcon }: { url?: string | null; alt: string; fallbackIcon: React.ReactNode }) {
  return (
    <div className="ficha-poster detail-poster">
      {url ? (
        <img
          src={url}
          alt={alt}
          className="ficha-poster-img"
          onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
        />
      ) : (
        <div className="ficha-poster-vacio">{fallbackIcon}</div>
      )}
    </div>
  )
}
