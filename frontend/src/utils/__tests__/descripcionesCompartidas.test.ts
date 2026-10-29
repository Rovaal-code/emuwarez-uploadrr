/**
 * Las descripciones de tooltip se comparten: un nodo oculto por texto
 * distinto, no uno por cada disparador de cada fila.
 */
import { describe, it, expect } from 'vitest'
import { crearRegistroDescripciones } from '../descripcionesCompartidas'

function registroDePrueba() {
  const vivos = new Map<string, string>()
  const registro = crearRegistroDescripciones((id, texto) => {
    vivos.set(id, texto)
    return { remove: () => { vivos.delete(id) } }
  })
  return { registro, vivos }
}

describe('descripciones compartidas', () => {
  it('el mismo texto en muchas filas es un solo nodo', () => {
    const { registro, vivos } = registroDePrueba()
    for (let fila = 0; fila < 50; fila++) {
      registro.montar('Abrir en Sonarr', registro.idDe('Abrir en Sonarr'))
    }
    expect(vivos.size).toBe(1)
    expect([...vivos.values()]).toEqual(['Abrir en Sonarr'])
  })

  it('textos distintos tienen ids distintos', () => {
    const { registro } = registroDePrueba()
    expect(registro.idDe('Ver ficha')).not.toBe(registro.idDe('Abrir en Radarr'))
    expect(registro.idDe('Ver ficha')).toBe(registro.idDe('Ver ficha'))
  })

  it('el nodo se queda mientras alguien lo use y se va con el último', () => {
    const { registro, vivos } = registroDePrueba()
    const id = registro.idDe('Ver ficha')
    registro.montar('Ver ficha', id)
    registro.montar('Ver ficha', id)
    registro.soltar('Ver ficha')
    expect(vivos.has(id)).toBe(true)
    registro.soltar('Ver ficha')
    expect(vivos.has(id)).toBe(false)
    expect(registro.tamano()).toBe(0)
  })

  it('al volver a montar después de soltarlo todo, recupera el mismo id', () => {
    // Pasa con StrictMode: monta, desmonta y vuelve a montar con el id que
    // el disparador ya tiene puesto desde el render.
    const { registro, vivos } = registroDePrueba()
    const id = registro.idDe('Forzar sync')
    registro.montar('Forzar sync', id)
    registro.soltar('Forzar sync')
    registro.montar('Forzar sync', id)
    expect(vivos.get(id)).toBe('Forzar sync')
  })

  it('soltar un texto que no está no rompe nada', () => {
    const { registro } = registroDePrueba()
    expect(() => registro.soltar('nada')).not.toThrow()
  })
})
