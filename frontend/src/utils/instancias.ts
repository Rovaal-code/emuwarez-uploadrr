import type { InstanceSafeResponse } from '../types/api'
import { timeAgo } from './format'

// Una instancia que la vigilancia no vio responder en su última mirada (dato de /dashboard/summary).
export interface CaidaDeInstancia {
  id: number
  nombre: string
  tipo: string
  ultima_sincronizacion: string | null
}

export interface EstadoDeInstancia {
  tono: 'ok' | 'error' | 'neutro'
  etiqueta: string
  // Un dato más que explica el estado («Última prueba: hace 5 min»); no siempre lo hay.
  detalle?: { titulo: string; valor: string }
}

/**
 * Cómo está una instancia, sin afirmar más de lo que se sabe. Manda lo más reciente y fiable: desactivada, lo que ve la
 * vigilancia (que mira cada pocos minutos) y, si no hay nada de eso, el resultado de la última prueba hecha a mano.
 * Sin ninguna de las dos no se dice que responda.
 */
export function estadoDeInstancia(inst: InstanceSafeResponse, caidas: CaidaDeInstancia[]): EstadoDeInstancia {
  if (!inst.enabled) return { tono: 'neutro', etiqueta: 'Desactivada' }
  const caida = caidas.find(c => c.id === inst.id)
  if (caida) {
    return {
      tono: 'error',
      etiqueta: 'No responde',
      detalle: { titulo: 'Última sincronización', valor: caida.ultima_sincronizacion ? timeAgo(caida.ultima_sincronizacion) : 'nunca' },
    }
  }
  const prueba = inst.last_test_status
  if (prueba === 'ok') {
    return { tono: 'ok', etiqueta: 'Prueba correcta', detalle: { titulo: 'Última prueba', valor: timeAgo(inst.last_test_at) } }
  }
  if (prueba) {
    const motivo = prueba.replace(/^error:\s*/i, '')
    return {
      tono: 'error',
      etiqueta: 'Prueba fallida',
      detalle: { titulo: 'Última prueba', valor: `${timeAgo(inst.last_test_at)}${motivo ? ` · ${motivo}` : ''}` },
    }
  }
  return { tono: 'neutro', etiqueta: 'Sin probar' }
}
