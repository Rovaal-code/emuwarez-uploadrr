// An external ID value (TMDb/IMDb/TVDB/MAL) with a small ↗ button that opens
// its public page. Shared by the request detail page and the library detail
// page so the ID fields look and behave the same in both.
export function ExternalIdLink({ id, href, label }: { id: string; href: string | null; label: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      {id}
      {href && (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          title={`Ver en ${label}`}
          style={{ textDecoration: 'none', fontSize: 12, lineHeight: '16px', padding: '1px 6px', borderRadius: 4, border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
        >
          ↗
        </a>
      )}
    </span>
  )
}
