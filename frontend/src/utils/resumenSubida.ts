// Los textos del paso Resumen del asistente de subida: lo que se va a mandar a eMuwarez, dicho con las
// mismas palabras en una película, un pack y una tanda. Funciones puras: el estado y las peticiones están en
// components/asistente/useResumen.ts.
import type { EmuComparison } from '../api/library'
import type { UploadCheck } from '../api/uploads'
import { formatBytes, formatNumero } from './format'
import { MODOS_PISTAS, normalizarModo, tocaElFichero, type ModoPistas } from './modoPistas'

export type Veredicto = 'mejor' | 'igual' | 'peor'

export interface FilaYaHay { clave: string; nombre: string; calidad: string; veredicto: Veredicto | null }

// Lo que el catálogo local sabe de lo que se sube. `sinNada`: cuántos de los `total` elementos no están.
export type YaHay =
  | { estado: 'cargando' }
  | { estado: 'error' }
  | { estado: 'sin-catalogo' }
  | { estado: 'listo'; filas: FilaYaHay[]; sinNada: number; total: number }

const plural = (n: number, uno: string, varios: string) => `${formatNumero(n)} ${n === 1 ? uno : varios}`

const unidos = (partes: (string | null | undefined | false)[]) => partes.filter(Boolean).join(' · ')

export function textoFicheros(c: { capitulosEnPack?: number | null; esPack?: boolean; elementos?: number; capitulos?: boolean; bytes: number | null }): string {
  const tamano = c.bytes ? formatBytes(c.bytes) : null
  if (c.esPack) {
    const n = c.capitulosEnPack
    return unidos([n ? `${plural(n, 'capítulo', 'capítulos')} en una carpeta` : 'Pack de temporada en una carpeta', tamano])
  }
  if (c.elementos && c.elementos > 1) {
    return unidos([plural(c.elementos, c.capitulos ? 'capítulo' : 'temporada', c.capitulos ? 'capítulos' : 'temporadas'), tamano])
  }
  return unidos(['1 fichero', tamano])
}

export function textoCategoria(esSerie: boolean, source?: string | null, resolucion?: string | null): string {
  return unidos([esSerie ? 'Serie' : 'Película', source, resolucion])
}

// `cambian`: pistas con algún cambio (los del servidor más lo editado a mano); `aMano`: las editadas a mano.
export function textoPistas(modo: string | null | undefined, cambian: number | null, aMano: number): string {
  const m: ModoPistas = normalizarModo(modo)
  if (!tocaElFichero(m)) return 'Sin cambios (Ninguno) · el original no se toca'
  const etiqueta = MODOS_PISTAS.find(x => x.value === m)?.label ?? m
  return unidos([
    etiqueta,
    cambian == null ? null : cambian === 0 ? 'ya están como se piden' : `${plural(cambian, 'pista cambia', 'pistas cambian')}`,
    aMano > 0 && `${plural(aMano, 'editada', 'editadas')} a mano`,
  ])
}

// El tipo de enlace que dijo la comprobación «Se puede preparar la carpeta de subida» («…/uploads (enlace duro)»).
export function tipoDeEnlace(checks: UploadCheck[] | undefined): 'duro' | 'simbólico' | null {
  const mensaje = checks?.find(c => c.id === 'carpeta_subida' && c.status === 'ok')?.message
  const m = /\(enlace (duro|simbólico)\)/.exec(mensaje ?? '')
  return m ? (m[1] as 'duro' | 'simbólico') : null
}

export function textoCopia(enlace: 'duro' | 'simbólico' | null, modo: string | null | undefined): { texto: string; nota: string | null } {
  const texto = enlace
    ? `Enlace ${enlace} en la carpeta de subidas · sin espacio extra`
    : 'Se decide al preparar los ficheros'
  const nota = tocaElFichero(normalizarModo(modo))
    ? 'Si un original lo comparte otro torrent, sus ediciones van a una copia reflink: solo ocupa lo que cambia.'
    : null
  return { texto, nota }
}

export interface PeticionResumen { texto: string; aviso: boolean }

export function textoPeticion(c: {
  enlazada: { titulo: string; puntos: number | null } | null
  // La que la ficha dice tener abierta cuando la subida no la enlaza.
  sinEnlazar: string | null
  // Una tanda: a cuántos de sus elementos alcanza la enlazada.
  cubre?: { cuantos: number; de: number }
  alcance: string
}): PeticionResumen {
  if (c.enlazada) {
    const pts = c.enlazada.puntos != null ? ` · ${formatNumero(c.enlazada.puntos)} pts` : ''
    const parte = c.cubre && c.cubre.cuantos < c.cubre.de ? ` en ${c.cubre.cuantos} de ${c.cubre.de}` : ''
    return { texto: `Cubre «${c.enlazada.titulo}»${parte}${pts}`, aviso: false }
  }
  if (c.sinEnlazar) {
    return { texto: `Hay una abierta («${c.sinEnlazar}») que esta subida no cubre. Para cubrirla, sube desde Peticiones.`, aviso: true }
  }
  return { texto: `Ninguna abierta para ${c.alcance}`, aviso: false }
}

const calidad = (r: string | null, s: string | null) => unidos([r, s]).replace(' · ', ' ')

// De las comparaciones con el catálogo local (una por elemento; null si falló esa petición) a lo que enseña la tabla.
export function resumirComparaciones(comparaciones: (EmuComparison | null)[]): YaHay {
  if (comparaciones.length === 0 || comparaciones.some(c => c == null)) return { estado: 'error' }
  const disponibles = (comparaciones as EmuComparison[]).filter(c => c.available)
  if (disponibles.length === 0) return { estado: 'sin-catalogo' }
  const filas: FilaYaHay[] = disponibles.flatMap((c, i) => c.matches.map((m, j) => ({
    clave: `${i}-${j}`, nombre: m.name, calidad: calidad(m.resolution, m.source), veredicto: m.veredicto ?? null,
  })))
  return {
    estado: 'listo', filas, total: disponibles.length,
    sinNada: disponibles.filter(c => c.matches.length === 0).length,
  }
}

export type NivelDuplicado = 'duplicado' | 'trump' | 'mixto' | 'peor' | 'sin-comparar'

// La conclusión de la tabla «En eMuwarez ya hay», en una frase: qué dicen los veredictos de lo tuyo frente a cada torrent.
// No es un permiso: eMuwarez tiene sus reglas de trumps y solo ellas deciden si una subida se acepta.
export function conclusionDuplicados(filas: FilaYaHay[]): { nivel: NivelDuplicado; clase: Veredicto | null; texto: string } | null {
  if (filas.length === 0) return null
  const cuenta = (v: Veredicto) => filas.filter(f => f.veredicto === v).length
  const mejor = cuenta('mejor'), igual = cuenta('igual'), peor = cuenta('peor')
  // Si algún torrent no se pudo comparar, lo que sigue solo vale para los que sí.
  const parcial = filas.some(f => f.veredicto === null)
  const nota = parcial ? ' Alguna comparación falta: la conclusión es parcial.' : ''
  if (mejor + igual + peor === 0) {
    return { nivel: 'sin-comparar', clase: null, texto: 'No se pudo comparar la calidad con lo que ya hay: revisa a mano si sería un duplicado.' }
  }
  if (igual > 0) {
    return { nivel: 'duplicado', clase: 'igual', texto: `Ya ${igual === 1 ? 'hay 1 torrent' : `hay ${formatNumero(igual)} torrents`} con tu misma calidad: la subida sería un duplicado.` }
  }
  if (mejor > 0 && peor === 0) {
    return { nivel: 'trump', clase: 'mejor', texto: `Tu copia mejora ${mejor === 1 ? 'el torrent que hay' : `los ${formatNumero(mejor)} torrents que hay`}: puede ser un trump. Revisa las reglas de trumps antes de subir.${nota}` }
  }
  if (mejor > 0) {
    return { nivel: 'mixto', clase: 'igual', texto: `Tu copia mejora ${formatNumero(mejor)} y empeora ${formatNumero(peor)} de lo que hay: no es un trump claro.${nota}` }
  }
  return { nivel: 'peor', clase: 'peor', texto: `Tu copia es peor que todo lo ${parcial ? 'comparado' : 'que ya hay'}: eMuwarez probablemente la rechace.${nota}` }
}
