import { InfoIcon } from '../../../components/InfoIcon'
import { Campo } from '../Campo'
import { CabeceraTarjeta } from '../CabeceraTarjeta'
import type { ConfigForm } from './useConfigForm'

export function BibliotecaCard({ form }: { form: ConfigForm }) {
  const { allowedRoots, setAllowedRoots } = form

  return (
    <div className="placeholder-card">
      <CabeceraTarjeta
        icono={(
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
            <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
          </svg>
        )}
        titulo="Acceso a la biblioteca"
        info={<InfoIcon text="Antes de subir un archivo, la app comprueba que su ruta está dentro de una de estas carpetas: una red de seguridad para que nunca se toque un archivo fuera de donde debería. Si la dejas vacía, las subidas reales se bloquearán hasta que la rellenes." />}
        descripcion={<>
          La carpeta donde este contenedor accede a tu biblioteca (el punto de montaje del volumen, no necesariamente
          el mismo que reportan Radarr/Sonarr). Por ejemplo: <code>/data</code> si lo montas igual que Radarr/Sonarr.
          Varias rutas separadas por comas.
        </>}
      />
      <Campo etiqueta="Rutas permitidas">
        {c => (
          <input
            {...c}
            className="form-input"
            value={allowedRoots}
            onChange={e => setAllowedRoots(e.target.value)}
            placeholder="/data"
            autoComplete="off"
            spellCheck={false}
          />
        )}
      </Campo>
    </div>
  )
}
