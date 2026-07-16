import { Favicon, domainOf } from './Favicon'

// An external ID value (TMDb/IMDb/TVDB/MAL) with the service's real favicon in
// front, which acts as the button that opens its public page (and grows a touch
// on hover, like the Radarr/Sonarr origin). Shared by the request detail page
// and the library detail page so the ID fields look and behave the same.
export function ExternalIdLink({ id, href, label }: { id: string; href: string | null; label: string }) {
  const domain = domainOf(href)
  const inner = (
    <>
      <Favicon domain={domain} size={16} radius={3} fallback={<span style={{ fontSize: 12 }}>↗</span>} />
      {id}
    </>
  )
  const style: React.CSSProperties = { display: 'inline-flex', alignItems: 'center', gap: 6 }
  // The whole field (favicon AND the id text) is the link, so hovering the text
  // counts too and it turns the accent colour like a title.
  return href
    ? <a className="hover-link" href={href} target="_blank" rel="noreferrer" title={`Ver en ${label}`} onClick={e => e.stopPropagation()} style={style}>{inner}</a>
    : <span style={style}>{inner}</span>
}
