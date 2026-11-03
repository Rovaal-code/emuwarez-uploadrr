// @vitest-environment jsdom
/**
 * El carril «Peticiones listas para subir» del Panel: en el orden que manda el servidor (la de más recompensa
 * primero), cinco como mucho, cada una un botón que se alcanza con Tab y abre su petición; sin ninguna, nada.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { RequestItemResponse } from '../../types/api'
import { CarrilPeticionesListas, CARRIL_LISTAS_MAX } from '../CarrilPeticionesListas'
import { desmontar, montar, pulsar, texto } from './dom'

const peticion = (id: number, parcial: Partial<RequestItemResponse> = {}): RequestItemResponse => ({
  id, title: `Peticion ${id}`, points: 1000 - id, category: 'Movies', library_year: null,
  req_scope: null, req_season: null, req_episode: null, poster_url: null, readiness_status: 'ready_to_upload',
  ...parcial,
} as RequestItemResponse)

const filas = () => [...document.querySelectorAll<HTMLButtonElement>('.panel-listas-carril button')]

afterEach(desmontar)

describe('CarrilPeticionesListas', () => {
  it('sin peticiones listas no pinta nada, ni la cabecera', async () => {
    await montar(<CarrilPeticionesListas items={[]} total={0} onOpen={() => {}} />)
    expect(document.querySelector('.panel-listas')).toBeNull()
    expect(texto()).toBe('')
  })

  it('pinta las peticiones en el orden recibido, con su título, año o temporada y su recompensa', async () => {
    await montar(<CarrilPeticionesListas total={3} onOpen={() => {}} items={[
      peticion(1, { title: 'Dune', library_year: 2021, points: 12500 }),
      peticion(2, { title: 'The Bear', req_scope: 'season', req_season: 2, library_year: 2022, points: 800 }),
      peticion(3, { title: 'Sin puntos', points: null }),
    ]} />)
    expect(texto()).toContain('Peticiones listas para subir')
    const [primera, segunda, tercera] = filas()
    expect(filas()).toHaveLength(3)
    expect(primera.textContent).toBe('Dune (2021)12.500')
    expect(segunda.textContent).toBe('The Bear (2022) - Temporada 2800')
    expect(tercera.textContent).toBe('Sin puntos—')
    // Lo que oye un lector de pantalla, con las cifras a la española.
    expect(primera.getAttribute('aria-label')).toBe('Dune (2021). Recompensa: 12.500 puntos')
    expect(tercera.getAttribute('aria-label')).toBe('Sin puntos. Recompensa: sin dato')
    expect(document.querySelector('.panel-ver-todas')?.textContent).toBe('3 listas')
  })

  it(`enseña ${CARRIL_LISTAS_MAX} como mucho y dice cuántas listas hay en total`, async () => {
    const muchas = Array.from({ length: 8 }, (_, i) => peticion(i + 1))
    await montar(<CarrilPeticionesListas items={muchas} total={12345} onOpen={() => {}} />)
    expect(filas().map(b => b.querySelector('.panel-listas-titulo')?.textContent)).toEqual(
      ['Peticion 1', 'Peticion 2', 'Peticion 3', 'Peticion 4', 'Peticion 5'])
    expect(document.querySelector('.panel-ver-todas')?.textContent).toBe('12.345 listas')
    await desmontar()
    await montar(<CarrilPeticionesListas items={[peticion(1)]} total={1} onOpen={() => {}} />)
    expect(document.querySelector('.panel-ver-todas')?.textContent).toBe('1 lista')
  })

  it('cada fila es un botón de verdad que abre su petición', async () => {
    const abrir = vi.fn()
    await montar(<CarrilPeticionesListas items={[peticion(7), peticion(9)]} total={2} onOpen={abrir} />)
    for (const b of filas()) {
      expect(b.tagName).toBe('BUTTON')
      expect(b.type).toBe('button')
      expect(b.tabIndex).toBe(0)
    }
    await pulsar(filas()[1])
    expect(abrir).toHaveBeenCalledWith(9)
  })
})
