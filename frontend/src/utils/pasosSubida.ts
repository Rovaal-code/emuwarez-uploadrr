import type { PasoSubida } from '../types/api'

// Los pasos con nombre de una subida y cómo se reintenta (el servidor los manda: services/subida_pasos.py).

export const ESTADO_PASO: Record<string, { simbolo: string; texto: string; color: string }> = {
  hecho: { simbolo: '✓', texto: 'Hecho', color: 'var(--color-available)' },
  en_curso: { simbolo: '●', texto: 'En curso', color: 'var(--color-available)' },
  fallido: { simbolo: '✕', texto: 'Falló aquí', color: 'var(--color-error-pale)' },
  cancelado: { simbolo: '■', texto: 'Cancelada aquí', color: 'var(--text-muted)' },
  pendiente: { simbolo: '○', texto: 'Pendiente', color: 'var(--text-muted)' },
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
