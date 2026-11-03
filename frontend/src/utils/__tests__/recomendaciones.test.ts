import { describe, it, expect } from 'vitest'
import { recompensaDeRecomendacion } from '../recomendaciones'
import { SIN_DATO } from '../format'

describe('la recompensa de una recomendación', () => {
  it('es la de la petición en el grupo 1, con los miles a la española', () => {
    expect(recompensaDeRecomendacion({ rec_group: 1, rec_points: 12500 })).toBe('12.500')
    expect(recompensaDeRecomendacion({ rec_group: 1, rec_points: 800 })).toBe('800')
    expect(recompensaDeRecomendacion({ rec_group: 1, rec_points: 0 })).toBe('0')
  })

  it('es la raya de sin dato si la petición no dice puntos', () => {
    expect(recompensaDeRecomendacion({ rec_group: 1, rec_points: null })).toBe(SIN_DATO)
  })

  it('no hay en los grupos 2 y 3: no son una petición', () => {
    expect(recompensaDeRecomendacion({ rec_group: 2, rec_points: null })).toBeNull()
    expect(recompensaDeRecomendacion({ rec_group: 3, rec_points: null })).toBeNull()
  })
})
