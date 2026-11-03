import type { AvisoHoy } from '../../utils/hoy'
import { EmptyState } from '../EmptyState'
import { HoverTitle } from '../Tooltip'
import { Carril } from './Carril'

const PUNTO: Record<AvisoHoy['tipo'], string> = {
  instancia: 'panel-punto-apagada',
  subida: 'panel-punto-mala',
  version: 'panel-punto-aviso',
  mas: 'panel-punto-mala',
}

// «Necesita atención»: solo lo que va mal, nunca lo que va bien. Sin avisos, lo dice y ya.
export function CarrilAtencion({ avisos, onVerSubida, onVerSubidas, onVerVersion }: {
  avisos: AvisoHoy[]
  onVerSubida: (jobId: number) => void
  onVerSubidas: () => void
  onVerVersion: () => void
}) {
  return (
    <Carril titulo="Necesita atención" nota={avisos.length ? String(avisos.length) : undefined} tour="dashboard-attention">
      {avisos.length === 0 ? (
        <EmptyState title="Nada que revisar" body="Aquí saldrán las instancias que no respondan, las subidas fallidas y las versiones nuevas." />
      ) : (
        <ul className="panel-lista">
          {avisos.map(a => (
            <li key={a.clave} className="panel-aviso">
              <span className={`panel-punto ${PUNTO[a.tipo]}`} aria-hidden="true" />
              <div className="panel-item-texto">
                <div className="panel-aviso-titulo">{a.titulo}</div>
                {a.detalle && <div className="panel-item-spec">{a.detalle}</div>}
              </div>
              {a.tipo === 'subida' && (
                <HoverTitle as="span" className="hover-link panel-aviso-accion" onClick={() => onVerSubida(a.jobId)} tip="Abrir la subida y ver por qué falló">Ver motivo</HoverTitle>
              )}
              {a.tipo === 'mas' && (
                <HoverTitle as="span" className="hover-link panel-aviso-accion" onClick={onVerSubidas} tip="Abrir Subidas">Ver todas</HoverTitle>
              )}
              {a.tipo === 'version' && (
                <HoverTitle as="span" className="hover-link panel-aviso-accion" onClick={onVerVersion} tip="Abrir Configuración">Ver</HoverTitle>
              )}
            </li>
          ))}
        </ul>
      )}
    </Carril>
  )
}
