// @vitest-environment jsdom
/**
 * La fila «Petición» de la ficha de Biblioteca: sin petición, solo la insignia de siempre; con ella, quién la pidió
 * (si eMuwarez lo enseña), la recompensa, un botón que la abre en Peticiones y un enlace a su página en eMuwarez.
 * La heredada de la serie o la temporada se dice como tal, y una serie lista las de sus temporadas.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PeticionDeLaFicha } from '../../types/api'
import { CampoPeticion, DEBAJO_MAX, PeticionesDebajo, alcanceDePeticion } from '../CampoPeticion'
import { boton, desmontar, montar, pulsar, texto } from './dom'

const peticion = (parcial: Partial<PeticionDeLaFicha> = {}): PeticionDeLaFicha => ({
  id: 42, title: 'Re:Zero', author: 'Gabriel', is_mine: false, points: 12500,
  url: 'https://emu-warez.com/requests/600', emu_status: 'Sin llenar', created_at: '2026-04-19T10:00:00Z',
  req_scope: null, req_season: null, req_episode: null, heredada_de: null, estado: 'Compatible',
  library_item_id: 1, ...parcial,
})

const enlaceEmu = () => document.querySelector<HTMLAnchorElement>('a.bibdet-pet-emu')

afterEach(desmontar)

describe('CampoPeticion', () => {
  it('sin petición queda solo la insignia, como siempre', async () => {
    await montar(<CampoPeticion itemType="movie" requestStatus="Sin petición" peticion={null} onAbrirPeticion={() => {}} />)
    expect(texto()).toBe('Sin petición')
    expect(document.querySelector('.bibdet-pet')).toBeNull()
    expect(document.querySelector('a, button')).toBeNull()
  })

  it('con petición dice quién la pidió, la recompensa y enlaza a Peticiones y a eMuwarez', async () => {
    const abrir = vi.fn()
    await montar(<CampoPeticion itemType="movie" requestStatus="Compatible" peticion={peticion()} onAbrirPeticion={abrir} />)
    expect(document.querySelector('.badge')?.textContent).toBe('Compatible')
    expect(texto()).toContain('de Gabriel')
    expect(texto()).not.toContain('(Yo)')
    // La cifra a la española, y lo que oye un lector de pantalla.
    expect(document.querySelector('.bibdet-pet-puntos')?.textContent).toBe('Recompensa: 12.500 puntos')

    const ver = boton('Ver petición')!
    expect(ver.type).toBe('button')
    expect(ver.tabIndex).toBe(0)
    await pulsar(ver)
    expect(abrir).toHaveBeenCalledWith(42)

    const a = enlaceEmu()!
    expect(a.getAttribute('href')).toBe('https://emu-warez.com/requests/600')
    expect(a.target).toBe('_blank')
    expect(a.rel).toBe('noreferrer')
    expect(a.getAttribute('aria-label')).toBe('Abrir la petición en eMuwarez: Re:Zero')
  })

  it('la tuya sale con (Yo); sin autor visible no se inventa uno', async () => {
    await montar(<CampoPeticion itemType="movie" requestStatus="Compatible" peticion={peticion({ is_mine: true })} />)
    expect(document.querySelector('.bibdet-pet-mio')?.textContent).toBe('Gabriel (Yo)')
    await desmontar()

    await montar(<CampoPeticion itemType="movie" requestStatus="Compatible"
      peticion={peticion({ author: null, points: null, url: null })} onAbrirPeticion={() => {}} />)
    expect(texto()).not.toContain('de ')
    expect(document.querySelector('.bibdet-pet-autor')).toBeNull()
    expect(document.querySelector('.bibdet-pet-puntos')).toBeNull()
    expect(enlaceEmu()).toBeNull()
    expect(boton('Ver petición')).toBeDefined()
  })

  it('sin forma de navegar no pinta el botón, pero sí el enlace a eMuwarez', async () => {
    await montar(<CampoPeticion itemType="movie" requestStatus="Compatible" peticion={peticion()} />)
    expect(boton('Ver petición')).toBeUndefined()
    expect(enlaceEmu()).not.toBeNull()
  })

  it('la heredada de la serie se dice como tal, con el estado de la serie', async () => {
    await montar(<CampoPeticion itemType="season" requestStatus="Sin petición"
      peticion={peticion({ heredada_de: 'serie', estado: 'Compatible' })} onAbrirPeticion={() => {}} />)
    expect(document.querySelector('.bibdet-pet-linea')?.textContent).toBe('Petición de la serieCompatible')
    expect(texto()).toContain('de Gabriel')
    expect(boton('Ver petición')).toBeDefined()
  })

  it('una serie que guarda la petición de una temporada dice de cuál', async () => {
    await montar(<CampoPeticion itemType="series" requestStatus="Compatible"
      peticion={peticion({ req_scope: 'season', req_season: 1 })} />)
    expect(document.querySelector('.bibdet-pet-linea')?.textContent).toBe('Temporada 1Compatible')
  })

  it('una serie lista las peticiones de sus temporadas, cada una abre la suya', async () => {
    const abrir = vi.fn()
    const debajo = [
      peticion({ id: 1, req_scope: 'season', req_season: 1, estado: 'Compatible' }),
      peticion({ id: 2, req_scope: 'episode', req_season: 1, req_episode: 4, estado: 'No disponible' }),
      ...Array.from({ length: DEBAJO_MAX }, (_, i) => peticion({ id: 10 + i, req_scope: 'season', req_season: 2 + i })),
    ]
    await montar(<PeticionesDebajo itemType="series" debajo={debajo} onAbrirPeticion={abrir} />)
    expect(texto()).toContain('Peticiones de sus temporadas')
    const lineas = [...document.querySelectorAll('.bibdet-pet-lista > li')]
    expect(lineas.map(l => [l.querySelector('button')?.textContent, l.querySelector('.bibdet-pet-nota')?.textContent]))
      .toEqual([['Temporada 1', 'Compatible'], ['S01E04', 'Faltante'], ['Temporada 2', 'Compatible'],
        ['Temporada 3', 'Compatible']])
    expect(texto()).toContain('y 2 más')
    await pulsar(lineas[1].querySelector('button')!)
    expect(abrir).toHaveBeenCalledWith(2)
  })

  it('sin peticiones debajo no pinta nada; una temporada habla de sus capítulos', async () => {
    await montar(<PeticionesDebajo itemType="series" debajo={null} />)
    expect(texto()).toBe('')
    await desmontar()
    await montar(<PeticionesDebajo itemType="season" debajo={[peticion({ req_scope: 'episode', req_season: 2, req_episode: 7 })]} />)
    expect(texto()).toContain('Peticiones de sus capítulos')
    expect(document.querySelector('.bibdet-pet-lista button')).toBeNull()
    expect(document.querySelector('.bibdet-pet-lista li')?.textContent).toBe('S02E07Compatible')
  })

  it('alcanceDePeticion', () => {
    expect(alcanceDePeticion({ req_scope: null, req_season: null, req_episode: null })).toBeNull()
    expect(alcanceDePeticion({ req_scope: 'season', req_season: 3, req_episode: null })).toBe('Temporada 3')
    expect(alcanceDePeticion({ req_scope: 'episode', req_season: 1, req_episode: 12 })).toBe('S01E12')
  })
})
