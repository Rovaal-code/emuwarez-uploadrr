export function SettingsPage() {
  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Configuración</div>
          <div className="page-subtitle">Ajustes generales, credenciales y servicios</div>
        </div>
      </div>
      <div className="placeholder-page">
        <div className="placeholder-card">
          <div className="placeholder-tag">Pendiente — Fase 5B</div>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.7 }}>
            La configuración general, TMDb, eMuwarez y Uploadrr podrán modificarse aquí sin
            necesidad de volver a ejecutar el asistente de configuración.
          </p>
        </div>
        <div className="placeholder-card">
          <h3>Secciones previstas</h3>
          <ol>
            <li>Configuración general (nombre, zona horaria, puerto)</li>
            <li>TMDb — API key, idioma, región</li>
            <li>eMuwarez — API key, endpoint, intervalo</li>
            <li>Uploadrr — ruta, modo cliente torrent</li>
            <li>Seguridad — cambiar contraseña, sesiones activas</li>
          </ol>
        </div>
      </div>
    </div>
  )
}
