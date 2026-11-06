import { useEffect, useState } from 'react'
import { getEmuProviders } from '../api/nomenclature'
import { Favicon } from './Favicon'
import { SortableList, DragHandleIcon } from './SortableList'
import { useTooltip, HoverTitle } from './Tooltip'
import { IconoPelicula } from './Iconos'
import { Modal } from './Modal'

export interface ProviderOption {
  code: string
  label: string
  domain?: string | null
}

// The provider's favicon, linking to its official page when the domain is
// known — except in the setup wizard, where the picker is just a preview of
// the same list Configuración has, not meant to send you off-app mid-setup.
function ProviderIcon({ domain, size = 16, link = true }: { domain?: string | null; size?: number; link?: boolean }) {
  const { triggerProps, tooltipNode } = useTooltip(domain && link ? `Abrir ${domain}` : null)
  const icon = <Favicon domain={domain} size={size} fallback={<span className="provprio-sin-icono"><IconoPelicula /></span>} />
  if (!domain || !link) return icon
  return (
    <a
      href={`https://${domain}`}
      target="_blank"
      rel="noreferrer"
      onClick={e => e.stopPropagation()}
      draggable={false}
      className="provprio-enlace"
      {...triggerProps}
    >
      {icon}
      {tooltipNode}
    </a>
  )
}

// Its own component (not inlined in renderRow below) so useTooltip's hook
// call is legal — renderRow is a plain callback invoked once per row, not a
// separate component instance.
function RemoveProviderButton({ onClick, nombre }: { onClick: () => void; nombre: string }) {
  const { triggerProps, tooltipNode } = useTooltip('Quitar')
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Quitar ${nombre}`}
      className="provprio-quitar"
      {...triggerProps}
    >
      <span aria-hidden>✕</span>
      {tooltipNode}
    </button>
  )
}

interface ProviderPriorityPickerProps {
  order: string[]
  onChange: (order: string[]) => void
  // Settings links each icon out to the provider's own site; the setup
  // wizard shows the exact same list only as a preview, so its icons stay
  // inert instead of tempting you to leave the wizard mid-setup.
  linkIcons?: boolean
}

// Checkbox (enable/disable) + native HTML5 drag-and-drop reorder — no new
// dependency (frontend has no drag-and-drop library today).
//
// The provider list comes from the same backend source as the upload wizard
// (GET /nomenclature/providers → services/source_assistant.EMU_PROVIDERS,
// already returned sorted), so Crunchyroll and the rest stay in sync and are
// shown alphabetically everywhere.
export function ProviderPriorityPicker({ order, onChange, linkIcons = true }: ProviderPriorityPickerProps) {
  const [options, setOptions] = useState<ProviderOption[]>([])
  const [showAdd, setShowAdd] = useState(false)

  useEffect(() => {
    getEmuProviders()
      .then(r => setOptions(
        r.providers
          .map(p => ({ code: p.code, label: p.name, domain: p.domain }))
          .sort((a, b) => a.code.localeCompare(b.code, undefined, { sensitivity: 'base' })),
      ))
      .catch(() => setOptions([]))
  }, [])

  function enable(code: string) {
    // Newly-added provider goes FIRST — it's presumably being added because
    // it should now be preferred, not silently tacked on at the bottom of
    // the priority order where it would rarely if ever get picked.
    if (!order.includes(code)) onChange([code, ...order])
  }

  function disable(code: string) {
    onChange(order.filter(c => c !== code))
  }

  const available = options.filter(p => !order.includes(p.code))

  return (
    <>
    <div className="provider-card__body">
      {order.length === 0 && (
        <p className="provprio-aviso">
          Ningún proveedor activado: se añadirán por orden de prioridad.
        </p>
      )}
      {order.length > 0 && (
        <div className="provider-card__list">
          <SortableList etiqueta={code => options.find(p => p.code === code)?.label ?? code} ids={order} onChange={onChange} renderRow={(code, idx, { dragging, handleProps }) => {
            const opt = options.find(p => p.code === code)
            return (
              <div className={`provprio-fila${dragging ? ' provprio-fila-arrastrando' : ''}`}>
                <span className="provprio-numero">{idx + 1}</span>
                <HoverTitle
                  as="span"
                  tip="Arrastra para reordenar, o usa las flechas del teclado"
                  {...handleProps}
                  className="drag-handle provprio-asa"
                  style={handleProps.style}
                ><DragHandleIcon /></HoverTitle>
                <ProviderIcon domain={opt?.domain} size={16} link={linkIcons} />
                {/* minWidth: 0 para que el flex:1 pueda encogerse por debajo
                    del ancho natural del texto; sin esto, un nombre largo
                    (o la tarjeta estrecha de abajo de 300px) empujaba el
                    botón de quitar fuera de la tarjeta en vez de truncar. */}
                <span className="provprio-nombre">
                  {opt?.label ?? code} <span className="provprio-codigo">({code})</span>
                </span>
                <RemoveProviderButton onClick={() => disable(code)} nombre={opt?.label ?? code} />
              </div>
            )
          }} />
        </div>
      )}
      {available.length > 0 && (
        <button className="btn btn-secondary btn-sm provider-card__add-btn" type="button" onClick={() => setShowAdd(true)}>
          + Añadir proveedor ({available.length})
        </button>
      )}
    </div>

      {showAdd && (
        <Modal titulo="Añadir proveedor de vídeo" onClose={() => setShowAdd(false)} className="provprio-modal">
          <div className="modal-body">
            {available.length === 0 ? (
              <p className="provprio-todos">Ya están todos añadidos.</p>
            ) : (
              <div className="provprio-rejilla">
                {available.map(opt => (
                  <button
                    key={opt.code}
                    type="button"
                    className="btn btn-ghost btn-sm provprio-opcion"
                    onClick={() => enable(opt.code)}
                  >
                    <Favicon domain={opt.domain} size={16} fallback={<IconoPelicula />} />
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </Modal>
      )}
    </>
  )
}
