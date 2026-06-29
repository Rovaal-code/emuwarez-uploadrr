// Requests page — placeholder until real eMuwarez endpoint is captured

export function RequestsPage() {
  return (
    <div className="placeholder-page">
      <div className="page-header">
        <div>
          <div className="page-title">Peticiones eMuwarez</div>
          <div className="page-subtitle">Vista de peticiones activas de eMuwarez cruzadas con tu biblioteca local</div>
        </div>
      </div>

      <div className="placeholder-card">
        <div className="placeholder-tag">Pendiente — Fase 5B</div>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.7, marginBottom: 16 }}>
          Esta sección mostrará todas las peticiones actuales de eMuwarez ordenadas por compatibilidad
          con tu biblioteca local.
        </p>
        <p style={{ color: 'var(--text-muted)', fontSize: 12, marginBottom: 12 }}>
          Para activar esta sección es necesario capturar el endpoint real de la API de peticiones
          de eMuwarez desde DevTools → Network.
        </p>
        <h3>Orden previsto de peticiones</h3>
        <ol>
          <li>Compatible + disponible + nomenclatura correcta</li>
          <li>Compatible + disponible + nomenclatura no adaptada</li>
          <li>Parcial por source (solo un motivo)</li>
          <li>Parcial por resolución (solo un motivo)</li>
          <li>Parcial por source y resolución</li>
          <li>Existe en biblioteca pero no cumple bien (baja confianza)</li>
          <li>No encontrado en biblioteca</li>
          <li>Petición llena</li>
        </ol>
      </div>

      <div className="placeholder-card">
        <h3>Columnas previstas</h3>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
          {['Petición', 'Categoría', 'Resolución pedida', 'Estado EMU', 'Compatibilidad', 'Contenido local', 'Nomenclatura', 'Acciones'].map(col => (
            <span key={col} style={{ padding: '3px 10px', background: 'var(--bg-input)', borderRadius: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
              {col}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
