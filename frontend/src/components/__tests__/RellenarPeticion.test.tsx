// @vitest-environment jsdom
/**
 * «Rellenar petición»: solo en una subida completada que cubría una petición; copia la URL del torrent, abre la
 * petición y, si el navegador no deja copiar (http en la red local), enseña la URL para copiarla a mano.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { UploadJob } from '../../types/api'
import { RellenarPeticion } from '../RellenarPeticion'
import { boton, desmontar, esperar, montar, pulsar, texto } from './dom'

const TORRENT = 'https://emu-warez.com/torrents/123'
const PETICION = 'https://emu-warez.com/requests/45'
const trabajo = (parcial: Partial<UploadJob> = {}): UploadJob => ({
  id: 1, status: 'completed', result_url: TORRENT, request_url: PETICION, request_title: 'Dune', ...parcial,
} as UploadJob)

let escribir: ReturnType<typeof vi.fn>
let abrir: ReturnType<typeof vi.fn>
let copiarComando: ReturnType<typeof vi.fn>

function contexto({ seguro, portapapeles, comando }: { seguro: boolean; portapapeles: 'ok' | 'falla'; comando: boolean }) {
  Object.defineProperty(window, 'isSecureContext', { value: seguro, configurable: true })
  escribir = vi.fn(() => (portapapeles === 'ok' ? Promise.resolve() : Promise.reject(new Error('sin permiso'))))
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: escribir }, configurable: true })
  copiarComando = vi.fn(() => comando)
  ;(document as unknown as { execCommand: unknown }).execCommand = copiarComando
}

beforeEach(() => {
  abrir = vi.fn(() => ({ opener: 'algo' }))
  window.open = abrir as unknown as typeof window.open
})
afterEach(desmontar)

describe('RellenarPeticion', () => {
  it('solo sale en una subida completada con la URL del torrent y la de la petición', async () => {
    for (const parcial of [{ status: 'failed' }, { status: 'running' }, { result_url: null }, { request_url: null }]) {
      await montar(<RellenarPeticion job={trabajo(parcial)} />)
      expect(boton('Rellenar petición')).toBeUndefined()
      await desmontar()
    }
    await montar(<RellenarPeticion job={trabajo()} />)
    expect(boton('Rellenar petición')).toBeDefined()
  })

  it('copia la URL del torrent y abre la petición en otra pestaña', async () => {
    contexto({ seguro: true, portapapeles: 'ok', comando: false })
    await montar(<RellenarPeticion job={trabajo()} />)
    await pulsar(boton('Rellenar petición'))
    await esperar(() => boton('URL copiada'))
    expect(escribir).toHaveBeenCalledWith(TORRENT)
    expect(abrir).toHaveBeenCalledWith(PETICION, '_blank')
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  })

  it('por http, donde no hay portapapeles, copia con execCommand', async () => {
    contexto({ seguro: false, portapapeles: 'ok', comando: true })
    await montar(<RellenarPeticion job={trabajo()} />)
    await pulsar(boton('Rellenar petición'))
    await esperar(() => boton('URL copiada'))
    expect(escribir).not.toHaveBeenCalled()
    expect(copiarComando).toHaveBeenCalledWith('copy')
    expect(abrir).toHaveBeenCalledWith(PETICION, '_blank')
    expect(document.querySelector('.portapapeles-oculto')).toBeNull()
  })

  it('si el portapapeles falla prueba execCommand', async () => {
    contexto({ seguro: true, portapapeles: 'falla', comando: true })
    await montar(<RellenarPeticion job={trabajo()} />)
    await pulsar(boton('Rellenar petición'))
    await esperar(() => boton('URL copiada'))
    expect(escribir).toHaveBeenCalled()
    expect(copiarComando).toHaveBeenCalled()
  })

  it('si no se puede copiar de ninguna forma, abre la petición y enseña la URL para copiarla a mano', async () => {
    contexto({ seguro: true, portapapeles: 'falla', comando: false })
    await montar(<RellenarPeticion job={trabajo()} />)
    await pulsar(boton('Rellenar petición'))
    const campo = await esperar(() => document.querySelector<HTMLInputElement>('[role="dialog"] input'))
    expect(campo.value).toBe(TORRENT)
    expect(campo.readOnly).toBe(true)
    expect(texto()).toContain('Cópiala a mano')
    expect(abrir).toHaveBeenCalledWith(PETICION, '_blank')
    expect(boton('URL copiada')).toBeUndefined()
    // Desde el modal se vuelve a intentar, ya con la página enfocada.
    copiarComando.mockReturnValue(true)
    await pulsar(boton('Copiar'))
    await esperar(() => boton('Copiada'))
  })
})
