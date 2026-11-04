// @vitest-environment jsdom
/** Las vistas guardadas de Biblioteca: guardar la combinación de ahora con un nombre, volver a ella con un clic y quitarla. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SIN_FILTROS, conVista, type FiltrosDeVista, type VistaGuardada } from '../../utils/vistasBiblioteca'
import { VistasGuardadas } from '../VistasGuardadas'
import { boton, desmontar, escribir, montar, pulsar } from './dom'

afterEach(desmontar)

const FLUX: FiltrosDeVista = { ...SIN_FILTROS, group: ['FLUX'] }
const UNA: VistaGuardada[] = conVista([], 'Solo FLUX', FLUX, 'a')

function montarVistas(vistas: VistaGuardada[], actual: FiltrosDeVista) {
  const onAplicar = vi.fn(), onGuardar = vi.fn(), onQuitar = vi.fn()
  return montar(<VistasGuardadas vistas={vistas} actual={actual} onAplicar={onAplicar} onGuardar={onGuardar} onQuitar={onQuitar} />)
    .then(() => ({ onAplicar, onGuardar, onQuitar }))
}

describe('VistasGuardadas', () => {
  it('sin filtros y sin vistas no enseña nada', async () => {
    await montarVistas([], SIN_FILTROS)
    expect(document.body.textContent).toBe('')
  })

  it('con filtros puestos ofrece guardarlos', async () => {
    await montarVistas([], FLUX)
    expect(boton('+ Guardar vista')).toBeDefined()
  })

  it('guarda con el nombre escrito', async () => {
    const { onGuardar } = await montarVistas([], FLUX)
    await pulsar(boton('+ Guardar vista'))
    await escribir(document.querySelector<HTMLInputElement>('input[aria-label="Nombre de la vista"]')!, '  Solo FLUX ')
    await pulsar(boton('Guardar'))
    expect(onGuardar).toHaveBeenCalledWith('  Solo FLUX ')
    expect(document.querySelector('input')).toBeNull()
  })

  it('sin nombre no deja guardar, y cancelar cierra el formulario', async () => {
    const { onGuardar } = await montarVistas([], FLUX)
    await pulsar(boton('+ Guardar vista'))
    expect(boton('Guardar')!.disabled).toBe(true)
    await pulsar(boton('Cancelar'))
    expect(onGuardar).not.toHaveBeenCalled()
    expect(boton('+ Guardar vista')).toBeDefined()
  })

  it('cada vista guardada se aplica con un clic', async () => {
    const { onAplicar } = await montarVistas(UNA, SIN_FILTROS)
    await pulsar(boton('Solo FLUX'))
    expect(onAplicar).toHaveBeenCalledWith(UNA[0])
  })

  it('marca como activa la vista que coincide con los filtros de ahora y no ofrece guardarla otra vez', async () => {
    await montarVistas(UNA, FLUX)
    expect(boton('Solo FLUX')!.getAttribute('aria-pressed')).toBe('true')
    expect(boton('+ Guardar vista')).toBeUndefined()
  })

  it('con otros filtros la vista no está activa', async () => {
    await montarVistas(UNA, { ...FLUX, quality: ['1080p'] })
    expect(boton('Solo FLUX')!.getAttribute('aria-pressed')).toBe('false')
    expect(boton('+ Guardar vista')).toBeDefined()
  })

  it('quita una vista', async () => {
    const { onQuitar } = await montarVistas(UNA, SIN_FILTROS)
    await pulsar(document.querySelector('button[aria-label="Quitar la vista «Solo FLUX»"]')!)
    expect(onQuitar).toHaveBeenCalledWith(UNA[0])
  })
})
