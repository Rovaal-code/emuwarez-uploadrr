/**
 * Las listas que se reordenan arrastrando (prioridad de proveedores de vídeo y
 * de imágenes) también se reordenan con el teclado desde la asa de cada fila.
 */
import { describe, it, expect } from 'vitest'
import { moverConTecla } from '../reordenar'

const lista = ['imgbb', 'pixhost', 'imgbox', 'ptpimg']

describe('reordenar con el teclado', () => {
  it('flecha arriba sube una posición', () => {
    expect(moverConTecla(lista, 'imgbox', 'ArrowUp')).toEqual(['imgbb', 'imgbox', 'pixhost', 'ptpimg'])
  })

  it('flecha abajo baja una posición', () => {
    expect(moverConTecla(lista, 'imgbb', 'ArrowDown')).toEqual(['pixhost', 'imgbb', 'imgbox', 'ptpimg'])
  })

  it('Inicio y Fin la llevan a los extremos', () => {
    expect(moverConTecla(lista, 'imgbox', 'Home')).toEqual(['imgbox', 'imgbb', 'pixhost', 'ptpimg'])
    expect(moverConTecla(lista, 'pixhost', 'End')).toEqual(['imgbb', 'imgbox', 'ptpimg', 'pixhost'])
  })

  it('en el borde no hay nada que mover', () => {
    expect(moverConTecla(lista, 'imgbb', 'ArrowUp')).toBeNull()
    expect(moverConTecla(lista, 'ptpimg', 'ArrowDown')).toBeNull()
    expect(moverConTecla(lista, 'imgbb', 'Home')).toBeNull()
  })

  it('otras teclas y filas que no están no hacen nada', () => {
    expect(moverConTecla(lista, 'imgbb', 'Enter')).toBeNull()
    expect(moverConTecla(lista, 'nada', 'ArrowDown')).toBeNull()
  })

  it('no toca la lista original', () => {
    const copia = [...lista]
    moverConTecla(lista, 'imgbox', 'ArrowUp')
    expect(lista).toEqual(copia)
  })
})
