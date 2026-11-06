import { describe, expect, it } from 'vitest'
import type { InstanceSafeResponse } from '../../types/api'
import { estadoDeInstancia } from '../instancias'

function instancia(extra: Partial<InstanceSafeResponse> = {}): InstanceSafeResponse {
  return {
    id: 1, type: 'radarr', name: 'Radarr', url: 'http://radarr', api_key_masked: 'abcd...wxyz', enabled: true,
    is_4k: false, is_anime: false, last_test_status: null, last_test_at: null, created_at: '2026-11-01 10:00:00', updated_at: null,
    ...extra,
  }
}

describe('Instancias: estado de cada tarjeta', () => {
  it('una desactivada lo es aunque la vigilancia la vea caída', () => {
    const e = estadoDeInstancia(instancia({ enabled: false }), [{ id: 1, nombre: 'Radarr', tipo: 'radarr', ultima_sincronizacion: null }])
    expect(e).toEqual({ tono: 'neutro', etiqueta: 'Desactivada' })
  })

  it('la vigilancia manda sobre una prueba antigua que salió bien', () => {
    const e = estadoDeInstancia(
      instancia({ last_test_status: 'ok', last_test_at: '2026-11-01 10:00:00' }),
      [{ id: 1, nombre: 'Radarr', tipo: 'radarr', ultima_sincronizacion: null }],
    )
    expect(e.tono).toBe('error')
    expect(e.etiqueta).toBe('No responde')
    expect(e.detalle).toEqual({ titulo: 'Última sincronización', valor: 'nunca' })
  })

  it('sin vigilancia dice lo que sabe de la última prueba, y sin prueba no afirma nada', () => {
    expect(estadoDeInstancia(instancia({ last_test_status: 'ok', last_test_at: '2026-11-01 10:00:00' }), []))
      .toMatchObject({ tono: 'ok', etiqueta: 'Prueba correcta' })
    const fallida = estadoDeInstancia(instancia({ last_test_status: 'error: Connection refused', last_test_at: '2026-11-01 10:00:00' }), [])
    expect(fallida).toMatchObject({ tono: 'error', etiqueta: 'Prueba fallida' })
    expect(fallida.detalle?.valor).toContain('Connection refused')
    expect(fallida.detalle?.valor).not.toContain('error:')
    expect(estadoDeInstancia(instancia(), [])).toEqual({ tono: 'neutro', etiqueta: 'Sin probar' })
  })

  it('una caída de otra instancia no cuenta', () => {
    const e = estadoDeInstancia(instancia({ id: 2 }), [{ id: 1, nombre: 'Radarr', tipo: 'radarr', ultima_sincronizacion: null }])
    expect(e.etiqueta).toBe('Sin probar')
  })
})
