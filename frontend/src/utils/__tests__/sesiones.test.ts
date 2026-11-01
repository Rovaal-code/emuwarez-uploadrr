import { describe, it, expect } from 'vitest'
import { descripcionDeSesion } from '../sesiones'

describe('descripcionDeSesion', () => {
  it('reconoce navegador y sistema', () => {
    expect(descripcionDeSesion('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36')).toBe('Chrome en Windows')
    expect(descripcionDeSesion('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36 Edg/130.0')).toBe('Edge en Windows')
    expect(descripcionDeSesion('Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0')).toBe('Firefox en Linux')
    expect(descripcionDeSesion('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15')).toBe('Safari en macOS')
  })

  it('Android y iOS no se confunden con Linux y macOS', () => {
    expect(descripcionDeSesion('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36')).toBe('Chrome en Android')
    expect(descripcionDeSesion('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1')).toBe('Safari en iOS')
  })

  it('sin user-agent o con uno desconocido no inventa nada', () => {
    expect(descripcionDeSesion(null)).toBe('Navegador desconocido')
    expect(descripcionDeSesion('')).toBe('Navegador desconocido')
    expect(descripcionDeSesion('curl/8.5.0')).toBe('curl/8.5.0')
    expect(descripcionDeSesion('x'.repeat(200))).toHaveLength(60)
  })
})
