import { api } from './client'
import type { EstadisticasCuenta } from '../types/api'

export async function getEstadisticasCuenta(dias: number): Promise<EstadisticasCuenta> {
  return api.get<EstadisticasCuenta>(`/estadisticas/cuenta?dias=${dias}`)
}
