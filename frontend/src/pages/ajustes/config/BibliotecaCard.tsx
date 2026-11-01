import { InfoIcon } from '../../../components/InfoIcon'
import type { ConfigForm } from './useConfigForm'

export function BibliotecaCard({ form }: { form: ConfigForm }) {
  const { allowedRoots, setAllowedRoots } = form

  return (
    <div className="placeholder-card">
      <h3 className="aj-card-titulo aj-mb-6">
        <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="1.75" aria-hidden>
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
        </svg>
        Acceso a la biblioteca
        <InfoIcon text="Antes de subir un archivo, la app comprueba que su ruta está dentro de una de estas carpetas: una red de seguridad para que nunca se toque un archivo fuera de donde debería. Si la dejas vacía, las subidas reales se bloquearán hasta que la rellenes." />
      </h3>
      <p className="form-hint aj-mt-0 aj-mb-12">
        La carpeta donde este contenedor accede a tu biblioteca (el punto de montaje del volumen, no necesariamente
        el mismo que reportan Radarr/Sonarr). Por ejemplo: <code>/data</code> si lo montas igual que Radarr/Sonarr.
        Varias rutas separadas por comas.
      </p>
      <div className="form-group">
        <label className="form-label">Rutas permitidas</label>
        <input
          className="form-input"
          value={allowedRoots}
          onChange={e => setAllowedRoots(e.target.value)}
          placeholder="/data"
        />
      </div>
    </div>
  )
}
