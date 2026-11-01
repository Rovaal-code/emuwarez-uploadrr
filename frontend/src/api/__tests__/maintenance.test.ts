/**
 * Bajar y subir backups: el token viaja en la cabecera (no en la URL), el archivo va como cuerpo sin
 * multipart, y un error del servidor llega con su motivo.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const json = (cuerpo: unknown, status = 200) =>
  new Response(JSON.stringify(cuerpo), { status, headers: { 'content-type': 'application/json' } })

let quitados: ReturnType<typeof vi.fn>
let pedir: ReturnType<typeof vi.fn>

async function cargar() {
  vi.resetModules()
  return import('../maintenance')
}

beforeEach(() => {
  quitados = vi.fn()
  pedir = vi.fn()
  vi.stubGlobal('localStorage', { getItem: () => 'token-de-prueba', setItem: vi.fn(), removeItem: quitados })
  vi.stubGlobal('sessionStorage', { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() })
  vi.stubGlobal('fetch', pedir)
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('uploadBackup', () => {
  it('manda el archivo como cuerpo, con el token y el tipo gzip', async () => {
    pedir.mockResolvedValue(json({ ok: true, name: 'emuwarez_config_subida_1.tar.gz', size_bytes: 3 }))
    const { uploadBackup } = await cargar()
    const archivo = new File([new Uint8Array([1, 2, 3])], 'mi-copia.tar.gz')

    const r = await uploadBackup(archivo)

    expect(r.name).toBe('emuwarez_config_subida_1.tar.gz')
    expect(pedir).toHaveBeenCalledWith('/api/maintenance/backups/upload', {
      method: 'POST',
      body: archivo,
      headers: { Authorization: 'Bearer token-de-prueba', 'Content-Type': 'application/gzip' },
    })
  })

  it('un rechazo del servidor llega con su motivo y su estado', async () => {
    pedir.mockResolvedValue(json({ detail: 'El archivo no es un backup (.tar.gz) válido' }, 422))
    const { uploadBackup } = await cargar()
    const { ApiClientError } = await import('../client')

    const error = await uploadBackup(new File(['x'], 'a.tar.gz')).catch(e => e)

    expect(error).toBeInstanceOf(ApiClientError)
    expect(error.message).toBe('El archivo no es un backup (.tar.gz) válido')
    expect(error.status).toBe(422)
  })

  it('sin cuerpo JSON en el error vale el texto del estado', async () => {
    pedir.mockResolvedValue(new Response('<html>', { status: 413, statusText: 'Payload Too Large' }))
    const { uploadBackup } = await cargar()
    await expect(uploadBackup(new File(['x'], 'a.tar.gz'))).rejects.toMatchObject({ message: 'Payload Too Large', status: 413 })
  })

  it('un 401 tira el token y dice que no hay sesión', async () => {
    pedir.mockResolvedValue(json({ detail: 'x' }, 401))
    const { uploadBackup } = await cargar()
    await expect(uploadBackup(new File(['x'], 'a.tar.gz'))).rejects.toMatchObject({ message: 'No autorizado', status: 401 })
    expect(quitados).toHaveBeenCalled()
  })

  it('si la petición no llega a completarse, estado 0', async () => {
    pedir.mockRejectedValue(new TypeError('Failed to fetch'))
    const { uploadBackup } = await cargar()
    await expect(uploadBackup(new File(['x'], 'a.tar.gz'))).rejects.toMatchObject({ status: 0 })
  })
})

describe('downloadBackup', () => {
  it('pide el backup por su nombre con el token y lo guarda con ese nombre', async () => {
    pedir.mockResolvedValue(new Response(new Blob(['contenido'])))
    const enlace = { href: '', download: '', click: vi.fn(), remove: vi.fn() }
    vi.stubGlobal('document', { createElement: vi.fn(() => enlace), body: { appendChild: vi.fn() } })
    const crear = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:copia')
    const revocar = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const { downloadBackup } = await cargar()

    await downloadBackup('emuwarez_config_20260101_030000.tar.gz')

    expect(pedir).toHaveBeenCalledWith(
      '/api/maintenance/backups/emuwarez_config_20260101_030000.tar.gz/download',
      { method: 'GET', body: undefined, headers: { Authorization: 'Bearer token-de-prueba' } },
    )
    expect(crear).toHaveBeenCalledTimes(1)
    expect(enlace.href).toBe('blob:copia')
    expect(enlace.download).toBe('emuwarez_config_20260101_030000.tar.gz')
    expect(enlace.click).toHaveBeenCalledTimes(1)
    expect(revocar).toHaveBeenCalledWith('blob:copia')
  })

  it('si no existe, el error lleva el motivo y no se descarga nada', async () => {
    pedir.mockResolvedValue(json({ detail: 'No hay ningún backup con ese nombre' }, 404))
    const crear = vi.spyOn(URL, 'createObjectURL')
    const { downloadBackup } = await cargar()
    await expect(downloadBackup('emuwarez_config_x.tar.gz')).rejects.toMatchObject({
      message: 'No hay ningún backup con ese nombre', status: 404,
    })
    expect(crear).not.toHaveBeenCalled()
  })
})
