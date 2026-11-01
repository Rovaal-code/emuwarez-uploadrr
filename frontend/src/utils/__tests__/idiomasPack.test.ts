import { describe, expect, it } from 'vitest'
import { conIdioma, etiquetaPistaSinIdioma, idiomasDelServidor, idiomasParaServidor, SIN_IDIOMAS } from '../idiomasPack'
import { avisoSourceVisible } from '../avisoSource'
import { ajustesDeTemporada } from '../origenProveedor'

describe('conIdioma', () => {
  it('elige, cambia y quita sin tocar el original', () => {
    const uno = conIdioma(SIN_IDIOMAS, 2, 'spa')
    expect(uno).toEqual({ 2: 'spa' })
    expect(SIN_IDIOMAS).toEqual({})
    expect(conIdioma(uno, 2, 'eng')).toEqual({ 2: 'eng' })
    expect(conIdioma(uno, 2, '')).toEqual({})
  })
})

describe('idiomasParaServidor', () => {
  it('sin nada elegido no manda nada', () => {
    expect(idiomasParaServidor(undefined)).toBeUndefined()
    expect(idiomasParaServidor({})).toBeUndefined()
    expect(idiomasParaServidor({ 1: 'spa' })).toEqual({ 1: 'spa' })
  })
})

describe('idiomasDelServidor', () => {
  it('pasa las claves del JSON a número y descarta lo raro', () => {
    expect(idiomasDelServidor({ '1': 'spa', x: 'eng', '0': 'cat', '3': 7 })).toEqual({ 1: 'spa' })
    expect(idiomasDelServidor(undefined)).toEqual({})
  })
})

describe('etiquetaPistaSinIdioma', () => {
  it('dice qué pista es y en qué capítulos', () => {
    expect(etiquetaPistaSinIdioma(2, 'DD 5.1', [1, 2, 3])).toBe('Pista de audio 2 (DD 5.1), capítulos 1, 2 y 3')
    expect(etiquetaPistaSinIdioma(1, null, [4])).toBe('Pista de audio 1, capítulo 4')
    expect(etiquetaPistaSinIdioma(1, 'AAC 2.0', [])).toBe('Pista de audio 1 (AAC 2.0)')
  })
})

describe('ajustesDeTemporada con idiomas', () => {
  it('los idiomas elegidos viajan a la cola, aunque no haya más ajustes', () => {
    expect(ajustesDeTemporada(undefined, new Map(), 7, { 1: 'spa' })).toEqual({ provider: undefined, idiomas: { 1: 'spa' } })
    expect(ajustesDeTemporada({ tag: 'X' }, new Map(), 7, {})).toEqual({ tag: 'X', provider: undefined })
    expect(ajustesDeTemporada(undefined, new Map(), 7, {})).toBeUndefined()
  })
})

describe('avisoSourceVisible', () => {
  const aviso = 'MediaInfo indica BluRay, pero el nombre del archivo dice WEB-DL.'
  it('se ve mientras Source no diga lo mismo que MediaInfo', () => {
    expect(avisoSourceVisible(aviso, 'BluRay', 'WEB-DL')).toBe(aviso)
    expect(avisoSourceVisible(aviso, 'BluRay', 'BluRay')).toBeNull()
    expect(avisoSourceVisible(null, 'BluRay', 'WEB-DL')).toBeNull()
    expect(avisoSourceVisible(aviso, null, 'WEB-DL')).toBe(aviso)
  })
})
