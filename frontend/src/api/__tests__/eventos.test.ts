/**
 * El troceado de los avisos del servidor.
 *
 * Es la parte frágil del canal y la que no se ve fallar: un trozo de red no
 * respeta las fronteras de los mensajes, así que puede traer dos avisos
 * pegados o la mitad de uno. Si el corte se lleva mal, el aviso partido se
 * pierde y —peor— deja el resto del flujo descolocado, con lo que el canal
 * queda mudo sin dar ningún error.
 */
import { describe, it, expect } from 'vitest'
import { extraerAvisos, esperaDelIntento, ESPERAS_MS } from '../eventos'

const aviso = (obj: unknown) => `data: ${JSON.stringify(obj)}\n\n`

describe('sacar los avisos de lo que va llegando', () => {
  it('un aviso completo se entiende', () => {
    const { avisos, resto } = extraerAvisos(aviso({ tipo: 'sync-terminada', que: 'biblioteca' }))
    expect(avisos).toEqual([{ tipo: 'sync-terminada', que: 'biblioteca' }])
    expect(resto).toBe('')
  })

  it('dos avisos que llegan pegados se separan', () => {
    const { avisos } = extraerAvisos(aviso({ tipo: 'uno' }) + aviso({ tipo: 'dos' }))
    expect(avisos.map(a => a.tipo)).toEqual(['uno', 'dos'])
  })

  // El caso que rompe el canal si se hace mal.
  it('un aviso partido en dos trozos se recompone', () => {
    const entero = aviso({ tipo: 'sync-terminada', que: 'catalogo' })
    const corte = 20
    const primero = extraerAvisos(entero.slice(0, corte))
    expect(primero.avisos).toEqual([])                       // todavía no hay nada
    const segundo = extraerAvisos(primero.resto + entero.slice(corte))
    expect(segundo.avisos).toEqual([{ tipo: 'sync-terminada', que: 'catalogo' }])
  })

  it('lo que llega a medias se guarda para el siguiente trozo', () => {
    const { avisos, resto } = extraerAvisos(aviso({ tipo: 'uno' }) + 'data: {"tipo":"do')
    expect(avisos.map(a => a.tipo)).toEqual(['uno'])
    expect(resto).toBe('data: {"tipo":"do')
  })

  it('los latidos se ignoran solos: para eso son comentarios', () => {
    const { avisos } = extraerAvisos(': latido\n\n: conectado\n\n')
    expect(avisos).toEqual([])
  })

  it('un latido entre dos avisos no estorba', () => {
    const { avisos } = extraerAvisos(aviso({ tipo: 'uno' }) + ': latido\n\n' + aviso({ tipo: 'dos' }))
    expect(avisos.map(a => a.tipo)).toEqual(['uno', 'dos'])
  })

  // Solo dicen "recarga", así que tirar uno cuesta enterarse por el sondeo de
  // siempre. Lo que no puede es cortar el canal.
  it('un aviso ilegible se tira sin llevarse los buenos por delante', () => {
    const { avisos } = extraerAvisos('data: {esto no es json\n\n' + aviso({ tipo: 'bueno' }))
    expect(avisos.map(a => a.tipo)).toEqual(['bueno'])
  })

  it('un json válido pero sin tipo no cuela', () => {
    const { avisos } = extraerAvisos(aviso({ cosa: 1 }))
    expect(avisos).toEqual([])
  })

  it('lo vacío no produce nada', () => {
    expect(extraerAvisos('')).toEqual({ avisos: [], resto: '' })
  })
})

describe('la espera antes de reintentar', () => {
  it('el primer intento es casi inmediato', () => {
    expect(esperaDelIntento(0)).toBe(1000)
  })

  it('se va abriendo, para no machacar un servidor caído', () => {
    const esperas = [0, 1, 2, 3].map(esperaDelIntento)
    expect(esperas).toEqual([...esperas].sort((a, b) => a - b))
    expect(new Set(esperas).size).toBe(esperas.length)
  })

  // Sin tope, un servidor que estuvo caído un rato largo tardaría una eternidad
  // en recuperar el canal justo cuando ya está bien.
  it('deja de crecer, y no falla al pasarse de la lista', () => {
    const tope = ESPERAS_MS[ESPERAS_MS.length - 1]
    expect(esperaDelIntento(ESPERAS_MS.length)).toBe(tope)
    expect(esperaDelIntento(999)).toBe(tope)
  })
})
