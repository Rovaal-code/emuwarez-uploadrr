/**
 * Cuándo Biblioteca tiene que pedir TODOS los niveles y no solo la raíz.
 *
 * La lista enseña un árbol: películas y series arriba, y sus temporadas y
 * capítulos colgando. Para eso se pide `parent_id = 0`, o sea solo lo que no
 * cuelga de nada.
 *
 * Pero en cuanto filtras, ese recorte MIENTE. Los desplegables ofrecen los
 * valores que existen en TODA la biblioteca (estilo Excel: solo lo que ocurre
 * de verdad, ver services/library.py::library_filter_values), así que ofrecen
 * cosas que solo pasan por debajo de la raíz. Al elegirlas se pedían las filas
 * que tuvieran ese valor Y además fueran raíz — a menudo ninguna, y la tabla
 * salía vacía como si no tuvieras nada.
 *
 * Medido en la auditoría de tablas, con una biblioteca de 11 elementos:
 *
 *   Tipo = Episodio           solo raíz 0   todos los niveles 4
 *   Petición = Sin petición   solo raíz 0   todos los niveles 4
 *   Petición = No compatible  solo raíz 0   todos los niveles 1
 *   Español = Sí              solo raíz 1   todos los niveles 5
 *   buscar "T2E1"             solo raíz 0   todos los niveles 1
 *
 * La regla, por tanto, es una y no una lista de casos: si hay CUALQUIER filtro
 * puesto, se pide en plano. El árbol es la vista de partida, no una que haya
 * que conservar mientras buscas algo concreto. Escrito como "algún filtro
 * activo" y no enumerando los que aplanan, porque enumerarlos es justo lo que
 * hizo que se olvidaran cinco.
 *
 * LA BÚSQUEDA ES LA EXCEPCIÓN, y por una razón distinta a todas las de arriba.
 * Los desplegables ofrecen valores que solo ocurren por debajo de la raíz; el
 * cajón de buscar no: los títulos de temporadas y capítulos llevan dentro el de
 * su serie, así que buscar "One Piece" acierta en los tres niveles a la vez.
 * En plano eso son la serie, sus temporadas y todos sus capítulos como filas
 * hermanas — cientos de filas para un único contenido. Buscar sigue mirando la
 * biblioteca entera, pero el acierto sube hasta su serie
 * (services/library.py::_build_library_filter), que es donde se busca el
 * contenido; lo de dentro se ve expandiéndola, como en cualquier otro momento.
 */

// Las columnas con selección múltiple llegan como lista; vacía = sin filtro.
type Valor = string | string[]

export interface FiltrosActivos {
  search?: string
  filterType?: Valor
  filterStatus?: Valor
  filterInstanceId?: Valor
  filterRequest?: Valor
  filterSpanish?: Valor
  searchProvider?: Valor
  searchQuality?: Valor
  searchSource?: Valor
  searchGroup?: Valor
  filterEmu?: Valor
  filterAporte?: Valor
}

export function hayAlgunFiltro(f: FiltrosActivos): boolean {
  return Object.values(f).some(v => (Array.isArray(v) ? v.length > 0 : !!v))
}

/** Con algo filtrado hay que mirar la biblioteca entera, no solo la raíz.
 *  Buscar no cuenta: el backend ya sube el acierto hasta su serie, así que la
 *  vista sigue siendo el árbol. */
export function necesitaTodosLosNiveles(f: FiltrosActivos): boolean {
  const { search: _buscar, ...resto } = f
  return hayAlgunFiltro(resto)
}
