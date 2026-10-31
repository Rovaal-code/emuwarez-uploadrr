import { describe, it, expect } from 'vitest'
import { decimalEs, enlacesCuentaEmu, ratioBajo } from '../cuentaEmu'

describe('los enlaces a tu cuenta de eMuwarez', () => {
  it('salen de las rutas de UNIT3D', () => {
    expect(enlacesCuentaEmu('Kisnov')).toEqual({
      perfil: 'https://emu-warez.com/users/Kisnov',
      mensajes: 'https://emu-warez.com/users/Kisnov/conversations',
      notificaciones: 'https://emu-warez.com/users/Kisnov/notifications',
      subidas: 'https://emu-warez.com/users/Kisnov/uploads',
    })
  })

  it('codifican el usuario', () => {
    expect(enlacesCuentaEmu('a b/c').perfil).toBe('https://emu-warez.com/users/a%20b%2Fc')
  })
})

describe('el aviso de ratio', () => {
  it.each([['0.99', true], ['0', true], ['1', false], ['4.1', false], ['∞', false], [null, false]])(
    '%s → %s', (ratio, bajo) => expect(ratioBajo(ratio)).toBe(bajo))
})

describe('decimalEs', () => {
  it('cambia el punto decimal por la coma', () => {
    expect(decimalEs('1.23 TiB')).toBe('1,23 TiB')
    expect(decimalEs('4.1')).toBe('4,1')
    expect(decimalEs('300 GiB')).toBe('300 GiB')
    expect(decimalEs('∞')).toBe('∞')
  })
})
