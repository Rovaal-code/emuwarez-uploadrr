import { ProviderPriorityPicker } from '../../../components/ProviderPriorityPicker'
import type { ConfigForm } from './useConfigForm'

export function ProveedoresVideoCard({ form }: { form: ConfigForm }) {
  const { providerOrder, setProviderOrder } = form

  return (
    <div className="placeholder-card provider-card">
      <h3 className="aj-card-titulo aj-mb-8">
        <svg width={18} height={18} viewBox="0 0 24 24" fill="none" aria-hidden>
          <rect x="2.5" y="5" width="19" height="14" rx="2.5" stroke="#8b5cf6" strokeWidth="1.6" />
          <path d="M10 9.2v5.6l4.5-2.8z" fill="#8b5cf6" />
        </svg>
        Proveedores de vídeo
      </h3>
      <span className="form-hint aj-block aj-mb-6">
        Se usa para elegir automáticamente el proveedor cuando TMDb devuelve varios. Arrastra para reordenar, o usa las flechas desde el asa de cada fila. El icono de cada uno enlaza a su web oficial.
      </span>
      <div className="form-group provider-card__body">
        <label className="form-label">Prioridad de proveedores</label>
        <ProviderPriorityPicker order={providerOrder} onChange={setProviderOrder} />
      </div>
    </div>
  )
}
