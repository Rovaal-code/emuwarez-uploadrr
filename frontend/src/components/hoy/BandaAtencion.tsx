import { useState } from 'react'
import type { AvisoHoy } from '../../utils/hoy'
import { HoverTitle } from '../Tooltip'

const PUNTO: Record<AvisoHoy['tipo'], string> = {
  instancia: 'panel-punto-apagada',
  subida: 'panel-punto-mala',
  version: 'panel-punto-aviso',
  mas: 'panel-punto-mala',
}

// Avisos a la vista sin desplegar: dos filas de dos columnas. El resto, tras «y N más».
const VISIBLES = 4

// «Necesita atención»: una banda fina, no un carril. Sin avisos es una sola línea; con avisos, filas compactas.
export function BandaAtencion({ avisos, onVerSubida, onVerSubidas, onVerVersion }: {
  avisos: AvisoHoy[]
  onVerSubida: (jobId: number) => void
  onVerSubidas: () => void
  onVerVersion: () => void
}) {
  const [todos, setTodos] = useState(false)

  if (avisos.length === 0) {
    return (
      <section className="panel-atencion panel-atencion-vacia" aria-label="Necesita atención" aria-live="polite" data-tour="dashboard-attention">
        Todo en orden
      </section>
    )
  }

  const vistos = todos ? avisos : avisos.slice(0, VISIBLES)
  const ocultos = avisos.length - vistos.length
  return (
    <section className="panel-atencion" aria-label="Necesita atención" aria-live="polite" data-tour="dashboard-attention">
      <div className="panel-atencion-cabecera">
        <h2 className="panel-atencion-titulo">Necesita atención <span className="panel-atencion-cuenta">{avisos.length}</span></h2>
        {(ocultos > 0 || todos) && (
          <button type="button" className="btn btn-ghost btn-sm panel-atencion-mas" onClick={() => setTodos(t => !t)}>
            {todos ? 'Ver menos' : `y ${ocultos} más`}
          </button>
        )}
      </div>
      <ul className="panel-atencion-lista">
        {vistos.map(a => (
          <li key={a.clave} className="panel-aviso">
            <span className={`panel-punto ${PUNTO[a.tipo]}`} aria-hidden="true" />
            <div className="panel-item-texto">
              <div className="panel-aviso-titulo">{a.titulo}</div>
              {a.detalle && <div className="panel-aviso-detalle" title={a.detalle}>{a.detalle}</div>}
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
    </section>
  )
}
