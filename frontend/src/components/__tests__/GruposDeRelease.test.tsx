// @vitest-environment jsdom
/**
 * El grupo de release en la ficha, las filas y las tablas: uno por insignia, «Varios» con la lista cuando no caben,
 * y un guion cuando no se sabe.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { GruposDeRelease, gruposDeRelease } from '../GruposDeRelease'
import { desmontar, montar, texto } from './dom'

afterEach(desmontar)

describe('gruposDeRelease', () => {
  it('prefiere la lista de los capítulos y, sin ella, el grupo de la propia fila', () => {
    expect(gruposDeRelease({ release_group: null, release_groups: ['FLUX', 'NTb'] })).toEqual(['FLUX', 'NTb'])
    expect(gruposDeRelease({ release_group: 'FLUX' })).toEqual(['FLUX'])
    expect(gruposDeRelease({ release_group: 'FLUX', release_groups: [] })).toEqual(['FLUX'])
  })

  it('sin ninguno devuelve la lista vacía', () => {
    expect(gruposDeRelease({ release_group: null, release_groups: null })).toEqual([])
    expect(gruposDeRelease({})).toEqual([])
  })
})

describe('GruposDeRelease', () => {
  it('sin grupo pone un guion', async () => {
    await montar(<GruposDeRelease grupos={[]} />)
    expect(texto()).toBe('—')
    expect(document.querySelector('.value-chip')).toBeNull()
  })

  it('con uno lo enseña en una insignia', async () => {
    await montar(<GruposDeRelease grupos={['FLUX']} />)
    expect(texto()).toBe('FLUX')
    expect(document.querySelectorAll('.value-chip')).toHaveLength(1)
  })

  it('en la ficha enseña cada grupo por separado hasta tres', async () => {
    await montar(<GruposDeRelease grupos={['FLUX', 'NTb', 'Loco87']} />)
    expect([...document.querySelectorAll('.value-chip')].map(c => c.textContent)).toEqual(['FLUX', 'NTb', 'Loco87'])
  })

  it('con más de tres los junta en «Varios» y deja la lista en el tooltip', async () => {
    await montar(<GruposDeRelease grupos={['A', 'B', 'C', 'D']} />)
    expect(document.querySelectorAll('.value-chip')).toHaveLength(1)
    expect(texto()).toContain('Varios (4)')
    expect(document.querySelector('.value-chip')!.getAttribute('aria-describedby')).toBeTruthy()
  })

  it('en una celda estrecha (junto) dos grupos ya son «Varios»', async () => {
    await montar(<GruposDeRelease grupos={['FLUX', 'NTb']} junto />)
    expect(texto()).toContain('Varios (2)')
    expect(document.querySelector('.value-chip')!.getAttribute('aria-describedby')).toBeTruthy()
  })
})
