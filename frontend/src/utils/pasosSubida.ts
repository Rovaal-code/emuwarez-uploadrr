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
  /** Lo que esta opción no repite (se enseña como ayuda del botón). */
  ayuda?: string
}

/** Los botones de reintento de una subida parada. Si el servidor puede reanudarla, ofrece reanudar y empezar de cero. */
export function opcionesDeReintento(
  job: { reintento_desde_nombre?: string | null; reintento_reutiliza?: string[] },
): OpcionDeReintento[] {
  if (!job.reintento_desde_nombre) return [{ etiqueta: 'Reintentar', desdeElPrincipio: false }]
  const reutiliza = job.reintento_reutiliza ?? []
  return [
    {
      etiqueta: `Reintentar desde «${job.reintento_desde_nombre}»`,
      desdeElPrincipio: false,
      ...(reutiliza.length > 0 ? { ayuda: `Reutiliza lo ya hecho si los ficheros no han cambiado: ${reutiliza.join(', ').toLowerCase()}` } : {}),
    },
    { etiqueta: 'Reintentar desde el principio', desdeElPrincipio: true },
  ]
}

/** El paso donde se paró una subida (el último hecho, fallido o cancelado, o el que iba en curso), o null si no
 *  consta ninguno: entonces todos siguen «Pendiente» aunque la subida ya no siga. */
export function pasoDondeSeParo(pasos: readonly Pick<PasoSubida, 'estado'>[]): number | null {
  for (let i = pasos.length - 1; i >= 0; i--) {
    if (['hecho', 'en_curso', 'fallido', 'cancelado'].includes(pasos[i].estado)) return i
  }
  return null
}

/** «Subida a eMuwarez» → «subida a eMuwarez»: baja solo la primera letra, para no estropear un nombre propio. */
export function minusculaInicial(texto: string): string {
  return texto ? texto[0].toLowerCase() + texto.slice(1) : texto
}
