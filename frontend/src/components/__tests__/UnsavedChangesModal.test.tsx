// @vitest-environment jsdom
/**
 * La confirmación de «cambios sin guardar»: lo seguro (seguir editando) lleva el foco y es lo que pasa con Escape;
 * salir exige pulsar «Salir sin guardar».
 */
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { guardedLeave, registerDirty } from '../../utils/unsavedGuard'
import { UnsavedChangesModal } from '../UnsavedChangesModal'
import { boton, desmontar, montar, pulsar } from './dom'

let quitar: () => void

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{}] as unknown as DOMRectList)
  Range.prototype.getClientRects = () => [] as unknown as DOMRectList
  quitar = registerDirty('prueba', () => true)
})
afterEach(async () => { quitar(); await desmontar(); vi.restoreAllMocks() })

describe('UnsavedChangesModal', () => {
  it('seguir editando lleva el foco, no sale y cierra el modal', async () => {
    const salir = vi.fn()
    await montar(<UnsavedChangesModal />)
    await act(async () => { guardedLeave(salir) })

    expect(document.querySelector('.modal-estrecho')).not.toBeNull()
    expect(document.activeElement).toBe(boton('Seguir editando'))

    await pulsar(boton('Seguir editando'))
    expect(salir).not.toHaveBeenCalled()
    expect(document.querySelector('.modal-panel')).toBeNull()
  })

  it('Escape equivale a seguir editando', async () => {
    const salir = vi.fn()
    await montar(<UnsavedChangesModal />)
    await act(async () => { guardedLeave(salir) })
    await act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })) })
    expect(salir).not.toHaveBeenCalled()
    expect(document.querySelector('.modal-panel')).toBeNull()
  })

  it('«Salir sin guardar» deja salir', async () => {
    const salir = vi.fn()
    await montar(<UnsavedChangesModal />)
    await act(async () => { guardedLeave(salir) })
    await pulsar(boton('Salir sin guardar'))
    expect(salir).toHaveBeenCalledTimes(1)
  })
})
