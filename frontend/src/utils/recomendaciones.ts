import type { DashboardRecommendationItem } from '../api/dashboard'
import { formatNumero, SIN_DATO } from './format'

/** El grupo de Recomendaciones que es una petición de eMuwarez compatible: el único con recompensa. */
const REC_GRUPO_PETICION = 1

/** La columna «Recompensa»: los puntos de la petición del grupo 1 (`SIN_DATO` si no los dice) y null en los grupos 2 y 3. */
export function recompensaDeRecomendacion(item: Pick<DashboardRecommendationItem, 'rec_group' | 'rec_points'>): string | null {
  if (item.rec_group !== REC_GRUPO_PETICION) return null
  return item.rec_points == null ? SIN_DATO : formatNumero(item.rec_points)
}
