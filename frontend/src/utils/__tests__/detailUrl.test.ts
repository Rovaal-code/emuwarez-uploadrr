/**
 * La ruta de una ficha: /<seccion>/<id> mientras está abierta.
 *
 * `esDeLaSeccion` parece de más hasta que se ve para qué está: al salir de una
 * sección, esa sección se reinicia y cierra su ficha, pero eso pasa DESPUÉS de
 * que la navegación haya puesto la URL de la sección nueva. Sin la
 * comprobación, salir de Biblioteca con una ficha abierta dejaba la barra de
 * direcciones diciendo /library estando ya en Subidas — y recargar ahí te
 * llevaba a la sección equivocada.
 */
import { describe, it, expect } from 'vitest'
import { idEnLaRuta, esDeLaSeccion } from '../detailUrl'

describe('el id de la ficha en la ruta', () => {
  it('lo saca de /library/42', () => {
    expect(idEnLaRuta('/library/42', 'library')).toBe(42)
  })

  it('la sección a secas no lleva ficha', () => {
    expect(idEnLaRuta('/library', 'library')).toBeNull()
  })

  it('la raíz tampoco', () => {
    expect(idEnLaRuta('/', 'library')).toBeNull()
  })

  it('no confunde la ficha de otra sección', () => {
    expect(idEnLaRuta('/uploads/42', 'library')).toBeNull()
  })

  it('una ruta con basura donde va el id no cuela', () => {
    expect(idEnLaRuta('/library/pepe', 'library')).toBeNull()
  })

  it('aguanta barras de más', () => {
    expect(idEnLaRuta('//library/42', 'library')).toBe(42)
  })
})

describe('si la ruta es de esta sección', () => {
  it('la sección a secas, sí', () => {
    expect(esDeLaSeccion('/library', 'library')).toBe(true)
  })

  it('con una ficha abierta, también', () => {
    expect(esDeLaSeccion('/library/42', 'library')).toBe(true)
  })

  // El caso de verdad: Biblioteca se reinicia justo después de que la URL ya
  // sea /uploads, y no puede pisarla.
  it('estando en otra sección, no', () => {
    expect(esDeLaSeccion('/uploads', 'library')).toBe(false)
    expect(esDeLaSeccion('/uploads/7', 'library')).toBe(false)
  })

  it('no le vale un nombre que empieza igual', () => {
    expect(esDeLaSeccion('/librarything', 'library')).toBe(false)
  })
})
