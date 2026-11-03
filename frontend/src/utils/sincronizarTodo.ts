import type { EmuSyncStatus } from '../api/library'
import type { RequestSyncStatusResponse } from '../types/api'

export type PasoSincronizacion = 'biblioteca' | 'catalogo' | 'peticiones'

/**
 * Lo que lanza «Sincronizar todo», en este orden: la biblioteca (lo que cruzan las otras dos), el catálogo de
 * eMuwarez (solo lo nuevo; el completo sigue en Biblioteca) y las peticiones. Una que eMuwarez limita a una vez por
 * hora y que aún no toca se salta en vez de fallar. Sin su estado cargado se intenta, y manda el servidor.
 */
export function pasosDeSincronizarTodo(
  catalogo: EmuSyncStatus | null, peticiones: RequestSyncStatusResponse | null,
): PasoSincronizacion[] {
  const pasos: PasoSincronizacion[] = ['biblioteca']
  if (!catalogo || catalogo.incremental_can_sync) pasos.push('catalogo')
  if (!peticiones || peticiones.can_sync) pasos.push('peticiones')
  return pasos
}
