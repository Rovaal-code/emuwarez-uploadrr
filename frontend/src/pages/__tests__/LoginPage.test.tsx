// @vitest-environment jsdom
/**
 * Inicio de sesión: el botón no se apaga con los campos vacíos (parecía roto): al pulsarlo dice qué falta y lleva el foco
 * al primer campo vacío; con los datos llama a la API y avisa de que ha entrado.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/auth', () => ({ login: vi.fn() }))

import { login } from '../../api/auth'
import { ApiClientError } from '../../api/client'
import { LoginPage } from '../LoginPage'
import { desmontar, escribir, montar, pulsar } from '../../components/__tests__/dom'

const enviar = () => pulsar(document.querySelector('button[type="submit"]')!)
const usuario = () => document.getElementById('username') as HTMLInputElement
const clave = () => document.getElementById('password') as HTMLInputElement
const aviso = () => document.querySelector('[role="alert"]')?.textContent

beforeEach(() => { vi.mocked(login).mockReset(); vi.mocked(login).mockResolvedValue(undefined as never) })
afterEach(desmontar)

describe('LoginPage', () => {
  it('con los campos vacíos el botón sigue activo, dice qué falta y enfoca el campo', async () => {
    await montar(<LoginPage onSuccess={vi.fn()} />)
    const boton = document.querySelector<HTMLButtonElement>('button[type="submit"]')!
    expect(boton.disabled).toBe(false)

    await enviar()
    expect(aviso()).toBe('Escribe tu usuario.')
    expect(document.activeElement).toBe(usuario())
    expect(login).not.toHaveBeenCalled()

    await escribir(usuario(), 'gabriel')
    await enviar()
    expect(aviso()).toBe('Escribe tu contraseña.')
    expect(document.activeElement).toBe(clave())
    // Los dos campos se describen con el aviso, pero solo el que falta se marca como inválido.
    for (const campo of [usuario(), clave()]) expect(campo.getAttribute('aria-describedby')).toBe('login-error')
    expect(clave().getAttribute('aria-invalid')).toBe('true')
    expect(usuario().hasAttribute('aria-invalid')).toBe(false)
  })

  it('sin error, los campos no se marcan como inválidos', async () => {
    await montar(<LoginPage onSuccess={vi.fn()} />)
    expect(usuario().hasAttribute('aria-invalid')).toBe(false)
    expect(clave().hasAttribute('aria-describedby')).toBe(false)
  })

  it('con usuario y contraseña inicia sesión', async () => {
    const onSuccess = vi.fn()
    await montar(<LoginPage onSuccess={onSuccess} />)
    await escribir(usuario(), ' gabriel ')
    await escribir(clave(), 'secreta')
    await enviar()
    expect(login).toHaveBeenCalledWith('gabriel', 'secreta', true)
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(aviso()).toBeUndefined()
  })

  it('unas credenciales malas marcan los dos campos; un fallo de red, ninguno', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    await montar(<LoginPage onSuccess={vi.fn()} />)
    await escribir(usuario(), 'gabriel')
    await escribir(clave(), 'mala')
    vi.mocked(login).mockRejectedValueOnce(new ApiClientError('no', 401, null))
    await enviar()
    expect(aviso()).toContain('Credenciales incorrectas')
    expect([usuario(), clave()].map(c => c.getAttribute('aria-invalid'))).toEqual(['true', 'true'])
    vi.mocked(login).mockRejectedValueOnce(new ApiClientError('sin red', 0, null))
    await enviar()
    expect(aviso()).toContain('No se pudo conectar con el servidor')
    expect([usuario(), clave()].some(c => c.hasAttribute('aria-invalid'))).toBe(false)
    vi.mocked(console.error).mockRestore()
  })

  it('el título es el h1 de la pantalla y el nombre de la marca no se traduce', async () => {
    await montar(<LoginPage onSuccess={vi.fn()} />)
    const h1 = document.querySelector('h1')!
    expect(h1.textContent).toBe('eMuwarez Uploadrr')
    expect(h1.getAttribute('translate')).toBe('no')
  })
})
