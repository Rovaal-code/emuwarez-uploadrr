import type { PasoSubida } from '../types/api'

// Los pasos con nombre de una subida y cómo se reintenta (el servidor los manda: services/subida_pasos.py).
// `clave` da la clase `dsub-paso-<clave>` (styles/detalle-subida.css), que fija el color de cada estado.

export const ESTADO_PASO: Record<string, { clave: string; simbolo: string; texto: string }> = {
  hecho: { clave: 'hecho', simbolo: '✓', texto: 'Hecho' },
  en_curso: { clave: 'en_curso', simbolo: '●', texto: 'En curso' },
  fallido: { clave: 'fallido', simbolo: '✕', texto: 'Falló aquí' },
  cancelado: { clave: 'cancelado', simbolo: '■', texto: 'Cancelada aquí' },
  pendiente: { clave: 'pendiente', simbolo: '○', texto: 'Pendiente' },
}

/** El estado de un paso tal como se enseña; uno desconocido se trata como pendiente. */
export function estadoDePaso(paso: Pick<PasoSubida, 'estado'>) {
  return ESTADO_PASO[paso.estado] ?? ESTADO_PASO.pendiente
}

export interface OpcionDeReintento {
  etiqueta: string
  desdeElPrincipio: boolean
}

/** Los botones de reintento de una subida parada. Si el servidor puede reanudarla, ofrece reanudar y empezar de cero. */
export function opcionesDeReintento(job: { reintento_desde_nombre?: string | null }): OpcionDeReintento[] {
  if (!job.reintento_desde_nombre) return [{ etiqueta: 'Reintentar', desdeElPrincipio: false }]
  return [
    { etiqueta: `Reintentar desde «${job.reintento_desde_nombre}»`, desdeElPrincipio: false },
    { etiqueta: 'Reintentar desde el principio', desdeElPrincipio: true },
  ]
}
