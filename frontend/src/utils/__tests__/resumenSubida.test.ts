/**
 * Los textos del Resumen del asistente de subida: lo que dicen de una película, un pack y una tanda, y que no
 * afirmen nada que no saben (un catálogo sin sincronizar no es «contenido único»).
 */
import { describe, it, expect } from 'vitest'
import type { EmuComparison } from '../../api/library'
import {
  conclusionDuplicados, resumirComparaciones, textoCategoria, textoCopia, textoFicheros, textoPeticion, textoPistas, tipoDeEnlace,
} from '../resumenSubida'

const coincidencia = (nombre: string, extra: Partial<EmuComparison['matches'][number]> = {}) =>
  ({ name: nombre, resolution: '1080p', source: 'WEB-DL', codec: null, has_spanish: 1, size: 1, ...extra })

const comparacion = (matches: EmuComparison['matches'], available = true): EmuComparison =>
  ({ available, message: null, matches })

describe('ficheros', () => {
  it('un fichero con su tamaño', () => {
    expect(textoFicheros({ bytes: 4_500_000_000 })).toBe('1 fichero · 4,2 GB')
  })
  it('sin tamaño no lo inventa', () => {
    expect(textoFicheros({ bytes: null })).toBe('1 fichero')
  })
  it('un pack dice cuántos capítulos y que van en una carpeta', () => {
    expect(textoFicheros({ esPack: true, capitulosEnPack: 10, bytes: 28_000_000_000 })).toBe('10 capítulos en una carpeta · 26,1 GB')
    expect(textoFicheros({ esPack: true, capitulosEnPack: 1, bytes: null })).toBe('1 capítulo en una carpeta')
    expect(textoFicheros({ esPack: true, bytes: null })).toBe('Pack de temporada en una carpeta')
  })
  it('una tanda cuenta los elementos', () => {
    expect(textoFicheros({ elementos: 3, capitulos: true, bytes: null })).toBe('3 capítulos')
    expect(textoFicheros({ elementos: 2, bytes: null })).toBe('2 temporadas')
  })
})

describe('categoría', () => {
  it('película o serie, con el source y la resolución que haya', () => {
    expect(textoCategoria(false, 'WEB-DL', '2160p')).toBe('Película · WEB-DL · 2160p')
    expect(textoCategoria(true, null, '1080p')).toBe('Serie · 1080p')
    expect(textoCategoria(true)).toBe('Serie')
  })
})

describe('pistas', () => {
  it('con «Ninguno» el original no se toca, edite lo que edite el usuario', () => {
    expect(textoPistas('ninguno', 0, 0)).toBe('Sin cambios (Ninguno) · el original no se toca')
    expect(textoPistas('ninguno', 3, 2)).toBe('Sin cambios (Ninguno) · el original no se toca')
  })
  it('con otro modo dice cuál, cuántas cambian y cuántas se editaron a mano', () => {
    expect(textoPistas('reordenar_y_renombrar', 3, 1)).toBe('Reordenar y renombrar · 3 pistas cambian · 1 editada a mano')
    expect(textoPistas('solo_renombrar', 1, 0)).toBe('Solo renombrar · 1 pista cambia')
    expect(textoPistas('solo_reordenar', 0, 0)).toBe('Solo reordenar · ya están como se piden')
  })
  it('sin plan (un pack, una tanda) dice solo el modo del ajuste', () => {
    expect(textoPistas('solo_renombrar', null, 0)).toBe('Solo renombrar')
  })
  it('un modo que no conoce cae al de fábrica, como el resto de la app', () => {
    expect(textoPistas(undefined, null, 0)).toBe('Solo renombrar')
    expect(textoPistas('algo_nuevo', null, 0)).toBe('Solo renombrar')
  })
})

describe('copia', () => {
  const check = (status: 'ok' | 'fail', message: string) => [{ id: 'carpeta_subida', label: '', status, message }] as never

  it('el tipo de enlace sale del mensaje de la comprobación, solo si pasó', () => {
    expect(tipoDeEnlace(check('ok', '/config/Uploadrr/uploads (enlace duro)'))).toBe('duro')
    expect(tipoDeEnlace(check('ok', '/config/Uploadrr/uploads (enlace simbólico)'))).toBe('simbólico')
    expect(tipoDeEnlace(check('fail', '/config (enlace duro)'))).toBeNull()
    expect(tipoDeEnlace(undefined)).toBeNull()
  })
  it('un enlace no ocupa espacio; las ediciones de un original compartido van a una copia reflink', () => {
    expect(textoCopia('duro', 'solo_renombrar')).toEqual({
      texto: 'Enlace duro en la carpeta de subidas · sin espacio extra',
      nota: 'Si un original lo comparte otro torrent, sus ediciones van a una copia reflink: solo ocupa lo que cambia.',
    })
  })
  it('con «Ninguno» no hay nada que editar y no hay nota', () => {
    expect(textoCopia('simbólico', 'ninguno').nota).toBeNull()
  })
  it('sin la comprobación no afirma ningún tipo', () => {
    expect(textoCopia(null, 'ninguno').texto).toBe('Se decide al preparar los ficheros')
  })
})

describe('petición', () => {
  it('la que cubre, con lo que paga', () => {
    expect(textoPeticion({ enlazada: { titulo: 'Dune', puntos: 1500 }, sinEnlazar: null, alcance: 'esta película' }))
      .toEqual({ texto: 'Cubre «Dune» · 1500 pts', aviso: false })
  })
  it('en una tanda dice a cuántos elementos alcanza, si no a todos', () => {
    const base = { enlazada: { titulo: 'Serie', puntos: null }, sinEnlazar: null, alcance: 'estos' }
    expect(textoPeticion({ ...base, cubre: { cuantos: 2, de: 3 } }).texto).toBe('Cubre «Serie» en 2 de 3')
    expect(textoPeticion({ ...base, cubre: { cuantos: 3, de: 3 } }).texto).toBe('Cubre «Serie»')
  })
  it('una abierta que la subida no cubre es un aviso', () => {
    const r = textoPeticion({ enlazada: null, sinEnlazar: 'Dune 4K', alcance: 'esta película' })
    expect(r.aviso).toBe(true)
    expect(r.texto).toContain('«Dune 4K»')
  })
  it('sin ninguna, lo dice del contenido concreto', () => {
    expect(textoPeticion({ enlazada: null, sinEnlazar: null, alcance: 'esta temporada' }))
      .toEqual({ texto: 'Ninguna abierta para esta temporada', aviso: false })
  })
})

describe('lo que ya hay en eMuwarez', () => {
  it('sin ninguna respuesta no hay nada que decir; una que falla invalida la tabla entera', () => {
    expect(resumirComparaciones([])).toEqual({ estado: 'error' })
    expect(resumirComparaciones([comparacion([]), null])).toEqual({ estado: 'error' })
  })
  it('un catálogo sin sincronizar no es «contenido único»', () => {
    expect(resumirComparaciones([comparacion([], false)])).toEqual({ estado: 'sin-catalogo' })
  })
  it('las filas llevan el nombre, la calidad y el veredicto del servidor', () => {
    const r = resumirComparaciones([comparacion([
      coincidencia('Dune 720p', { resolution: '720p', source: 'HDTV', veredicto: 'mejor' }),
      coincidencia('Dune 2160p', { resolution: '2160p', source: null, veredicto: 'peor' }),
      coincidencia('Dune sin datos', { resolution: null, source: null }),
    ])])
    expect(r).toEqual({
      estado: 'listo', total: 1, sinNada: 0, filas: [
        { clave: '0-0', nombre: 'Dune 720p', calidad: '720p HDTV', veredicto: 'mejor' },
        { clave: '0-1', nombre: 'Dune 2160p', calidad: '2160p', veredicto: 'peor' },
        { clave: '0-2', nombre: 'Dune sin datos', calidad: '', veredicto: null },
      ],
    })
  })
  it('en una tanda cuenta los elementos que no están y suma las filas de los que sí', () => {
    const r = resumirComparaciones([comparacion([coincidencia('E01', { veredicto: 'igual' })]), comparacion([]), comparacion([], false)])
    expect(r).toMatchObject({ estado: 'listo', total: 2, sinNada: 1 })
    expect((r as { filas: unknown[] }).filas).toHaveLength(1)
  })
})

describe('la conclusión de duplicados y trumps', () => {
  const fila = (veredicto: 'mejor' | 'igual' | 'peor' | null) => ({ clave: String(Math.random()), nombre: 'T', calidad: '1080p', veredicto })

  it('sin torrents en eMuwarez no hay conclusión que dar', () => {
    expect(conclusionDuplicados([])).toBeNull()
  })

  it('una calidad igual a alguna es un duplicado, aunque otras sean peores', () => {
    const c = conclusionDuplicados([fila('peor'), fila('igual')])!
    expect(c.nivel).toBe('duplicado')
    expect(c.texto).toContain('duplicado')
  })

  it('mejor que todo es un posible trump y manda revisar las reglas', () => {
    const c = conclusionDuplicados([fila('mejor'), fila('mejor')])!
    expect(c).toMatchObject({ nivel: 'trump', clase: 'mejor' })
    expect(c.texto).toContain('reglas de trumps')
  })

  it('mejor que unos y peor que otros no es un trump claro', () => {
    expect(conclusionDuplicados([fila('mejor'), fila('peor')])).toMatchObject({ nivel: 'mixto' })
  })

  it('peor que todo se dice como rechazo probable', () => {
    expect(conclusionDuplicados([fila('peor')])).toMatchObject({ nivel: 'peor', clase: 'peor' })
  })

  it('si falta alguna comparación, la conclusión se dice parcial y no afirma «peor que todo»', () => {
    const peor = conclusionDuplicados([fila('peor'), fila(null)])!
    expect(peor.nivel).toBe('peor')
    expect(peor.texto).toContain('parcial')
    expect(peor.texto).not.toContain('que ya hay')
    expect(conclusionDuplicados([fila('mejor'), fila(null)])!.texto).toContain('parcial')
    expect(conclusionDuplicados([fila('peor')])!.texto).not.toContain('parcial')
  })

  it('sin nada comparable no afirma nada', () => {
    expect(conclusionDuplicados([fila(null)])).toMatchObject({ nivel: 'sin-comparar', clase: null })
  })
})
