import { PistaReordenar } from '../../../components/SortableList'
import { ProviderPriorityPicker } from '../../../components/ProviderPriorityPicker'
import { CabeceraTarjeta } from '../CabeceraTarjeta'
import type { ConfigForm } from './useConfigForm'

export function ProveedoresVideoCard({ form }: { form: ConfigForm }) {
  const { providerOrder, setProviderOrder } = form

  return (
    <div className="placeholder-card provider-card">
      <CabeceraTarjeta
        icono={(
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" aria-hidden>
            <rect x="2.5" y="5" width="19" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
            <path d="M10 9.2v5.6l4.5-2.8z" fill="currentColor" />
          </svg>
        )}
        titulo="Proveedores de vídeo"
        descripcion={<>Se usa para elegir automáticamente el proveedor cuando TMDb devuelve varios. <PistaReordenar raton="Arrastra para reordenar, o usa las flechas desde el asa de cada fila." dedo="Reordénalos con las flechas de cada fila." /> El icono de cada uno enlaza a su web oficial.</>}
      />
      <div className="form-group">
        <span className="form-label">Prioridad de proveedores</span>
        <ProviderPriorityPicker order={providerOrder} onChange={setProviderOrder} />
      </div>
    </div>
  )
}
