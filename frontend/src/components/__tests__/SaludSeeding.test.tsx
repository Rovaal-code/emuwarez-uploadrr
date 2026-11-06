// @vitest-environment jsdom
/**
 * La salud del seeding en Subidas: la celda de la lista y el bloque del detalle, con el servidor simulado.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/seeding', () => ({ getSeeding: vi.fn() }))

import { getSeeding, type SeedingItem, type SeedingResponse } from '../../api/seeding'
import { useSeeding } from '../../hooks/useSeeding'
import type { UploadJob } from '../../types/api'
import { SeedingBloque, SeedingCelda, nombreDelTorrent } from '../SaludSeeding'
import { boton, desmontar, esperar, montar, pulsar, texto } from './dom'

const m = vi.mocked(getSeeding)

const subida = (parcial: Partial<UploadJob> = {}): UploadJob => ({ id: 7, status: 'completed', ...parcial }) as UploadJob

function respuesta(item: Partial<SeedingItem> | null, parcial: Partial<SeedingResponse> = {}): SeedingResponse {
  return {
    configurado: true, disponible: true, mensaje: null, actualizado: '2026-11-02T10:00:00+00:00',
    items: item ? [{ job_id: 7, estado: 'sembrando', etiqueta: 'Sembrando', ratio: 1.5, subido: 3221225472,
      progreso: 1, seeds: 12, peers: 3, ...item }] : [],
    ...parcial,
  }
}

function Pagina({ job }: { job: UploadJob }) {
  const seeding = useSeeding()
  return (
    <>
      <div data-testid="celda"><SeedingCelda job={job} seeding={seeding} /></div>
      <SeedingBloque job={job} seeding={seeding} />
    </>
  )
}

beforeEach(() => { m.mockReset() })
afterEach(desmontar)

describe('SaludSeeding', () => {
  it('enseña estado y ratio en la lista y el bloque completo en el detalle, con cifras es-ES', async () => {
    m.mockResolvedValue(respuesta({}))
    await montar(<Pagina job={subida()} />)
    await esperar(() => texto().includes('Ratio'))
    expect(document.querySelector('[data-testid="celda"]')!.textContent).toBe('Sembrando · ratio 1,50')
    const bloque = document.querySelector('[data-testid="seeding-bloque"]')!.textContent!
    expect(bloque).toContain('3,0 GB')
    expect(bloque).toContain('100,0 %')
    expect(bloque).toContain('12 / 3')
    expect(bloque).toContain('Leído')
  })

  describe('Abrir en qBittorrent', () => {
    const enlace = () => [...document.querySelectorAll('a')].find(a => a.textContent?.includes('Abrir en qBittorrent'))

    it('sin URL pública no hay enlace ni «Copiar nombre»', async () => {
      m.mockResolvedValue(respuesta({}, { url_publica: null }))
      await montar(<Pagina job={subida({ prepared_path: '/data/uploads/Peli.2020.1080p' })} />)
      await esperar(() => texto().includes('Ratio'))
      expect(enlace()).toBeUndefined()
      expect(boton('Copiar nombre')).toBeUndefined()
    })

    it('con URL pública enseña el enlace a esa URL, en pestaña nueva y sin opener', async () => {
      m.mockResolvedValue(respuesta({}, { url_publica: 'https://qbit.midominio.es/' }))
      await montar(<Pagina job={subida({ prepared_path: '/data/uploads/Peli.2020.1080p' })} />)
      await esperar(() => enlace() !== undefined)
      const a = enlace()!
      expect(a.getAttribute('href')).toBe('https://qbit.midominio.es/')
      expect(a.getAttribute('target')).toBe('_blank')
      expect(a.getAttribute('rel')).toBe('noopener noreferrer')
    })

    it('el enlace sigue ahí aunque qBittorrent no responda (la URL no depende de la consulta)', async () => {
      m.mockResolvedValue(respuesta(null, { disponible: false, mensaje: 'No se pudo conectar con qBittorrent',
        url_publica: 'http://192.168.1.5:8080' }))
      await montar(<Pagina job={subida()} />)
      await esperar(() => enlace() !== undefined)
      expect(enlace()!.getAttribute('href')).toBe('http://192.168.1.5:8080')
    })

    it('«Copiar nombre» copia el último trozo de la ruta preparada', async () => {
      const escribirPortapapeles = vi.fn().mockResolvedValue(undefined)
      vi.stubGlobal('isSecureContext', true)
      Object.defineProperty(navigator, 'clipboard', { value: { writeText: escribirPortapapeles }, configurable: true })
      try {
        m.mockResolvedValue(respuesta({}, { url_publica: 'https://qbit.midominio.es' }))
        await montar(<Pagina job={subida({ prepared_path: '/data/uploads/Peli.2020.1080p-EMUWAREZ/' })} />)
        await esperar(() => boton('Copiar nombre') !== undefined)
        await pulsar(boton('Copiar nombre'))
        expect(escribirPortapapeles).toHaveBeenCalledWith('Peli.2020.1080p-EMUWAREZ')
        expect(boton('Nombre copiado')).toBeDefined()
      } finally {
        vi.unstubAllGlobals()
        Reflect.deleteProperty(navigator, 'clipboard')
      }
    })

    it('sin ruta preparada no se ofrece copiar el nombre, pero el enlace sí', async () => {
      m.mockResolvedValue(respuesta({}, { url_publica: 'https://qbit.midominio.es' }))
      await montar(<Pagina job={subida({ prepared_path: undefined })} />)
      await esperar(() => enlace() !== undefined)
      expect(boton('Copiar nombre')).toBeUndefined()
    })

    it('nombreDelTorrent acepta barras de las dos clases y una ruta vacía', () => {
      expect(nombreDelTorrent(subida({ prepared_path: 'C:\\uploads\\Peli 2020' }))).toBe('Peli 2020')
      expect(nombreDelTorrent(subida({ prepared_path: undefined }))).toBe('')
    })
  })

  it('el estado va siempre con texto, no solo con color', async () => {
    m.mockResolvedValue(respuesta({ estado: 'faltan_ficheros', etiqueta: 'Faltan ficheros', progreso: 0.4 }))
    await montar(<Pagina job={subida()} />)
    await esperar(() => texto().includes('Ratio'))
    expect(document.querySelector('[data-testid="celda"]')!.textContent).toContain('Faltan ficheros')
    expect(document.querySelector('.badge.status-error')).not.toBeNull()
    expect(texto()).toContain('carpeta de subidas')
  })

  it('«No se encuentra» cuando qBittorrent responde pero no hay torrent de esa subida', async () => {
    m.mockResolvedValue(respuesta({ estado: 'no_encontrado', etiqueta: 'No se encuentra' }, { items: [
      { job_id: 7, estado: 'no_encontrado', etiqueta: 'No se encuentra' }] }))
    await montar(<Pagina job={subida()} />)
    await esperar(() => document.querySelector('[data-testid="celda"]')!.textContent === 'No se encuentra')
    expect(texto()).toContain('Estado')
  })

  it('sin qBittorrent (no responde o no está configurado) dice «Sin datos de qBittorrent»', async () => {
    m.mockResolvedValue(respuesta(null, { disponible: false, mensaje: 'No se pudo conectar con qBittorrent' }))
    await montar(<Pagina job={subida()} />)
    await esperar(() => texto().includes('No se pudo conectar con qBittorrent'))
    expect(document.querySelector('[data-testid="celda"]')!.textContent).toBe('Sin datos de qBittorrent')
    expect(texto()).toContain('Sin datos de qBittorrent')
  })

  it('si la petición falla (un 500, sin red) tampoco rompe: «Sin datos de qBittorrent»', async () => {
    m.mockRejectedValue(new Error('HTTP 500'))
    await montar(<Pagina job={subida()} />)
    await esperar(() => document.querySelector('[data-testid="celda"]')!.textContent === 'Sin datos de qBittorrent')
    expect(texto()).toContain('Esto no afecta a la subida')
  })

  it('una subida que no está completada no consulta ni enseña nada', async () => {
    m.mockResolvedValue(respuesta({}))
    await montar(<Pagina job={subida({ status: 'running' })} />)
    expect(document.querySelector('[data-testid="celda"]')!.textContent).toBe('—')
    expect(document.querySelector('[data-testid="seeding-bloque"]')).toBeNull()
  })

  it('«Actualizar» pide de nuevo saltándose la caché del servidor', async () => {
    m.mockResolvedValue(respuesta({}))
    await montar(<Pagina job={subida()} />)
    await esperar(() => boton('Actualizar') && !boton('Actualizar')!.disabled)
    m.mockResolvedValue(respuesta({ ratio: 2.25 }))
    await pulsar(boton('Actualizar'))
    await esperar(() => document.querySelector('[data-testid="celda"]')!.textContent === 'Sembrando · ratio 2,25')
    expect(m).toHaveBeenLastCalledWith(true)
    expect(m.mock.calls.slice(0, -1).every(c => c[0] === false)).toBe(true)
  })

  it('no hay reloj: pasado un buen rato no se vuelve a pedir nada solo', async () => {
    vi.useFakeTimers()
    try {
      m.mockResolvedValue(respuesta({}))
      await montar(<Pagina job={subida()} />)
      const antes = m.mock.calls.length
      await vi.advanceTimersByTimeAsync(10 * 60 * 1000)
      expect(m.mock.calls.length).toBe(antes)
    } finally {
      vi.useRealTimers()
    }
  })
})
