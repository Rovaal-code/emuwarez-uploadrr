/**
 * Cuándo Biblioteca tiene que pedir TODOS los niveles y no solo la raíz.
 *
 * La lista enseña el árbol: películas y series arriba, y sus temporadas y
 * capítulos colgando. Para eso se pide `parent_id = 0`, o sea solo lo que no
 * cuelga de nada. Pero hay filtros que no se pueden resolver así, y entonces
 * hay que pedir la biblioteca en plano.
 */

/** Los tipos que NUNCA son raíz: siempre cuelgan de algo. */
const TIPOS_QUE_CUELGAN = new Set(['season', 'episode'])

export interface FiltrosActivos {
  searchProvider?: string
  searchQuality?: string
  searchSource?: string
  filterEmu?: string
  filterAporte?: string
  filterType?: string
}

export function necesitaTodosLosNiveles(f: FiltrosActivos): boolean {
  // Proveedor y calidad se calculan sumando lo que hay por debajo, así que
  // pidiendo solo la raíz se escondería una temporada cuyos capítulos son
  // todos, por ejemplo, de Netflix dentro de una serie de varios proveedores.
  if (f.searchProvider || f.searchQuality || f.searchSource || f.filterEmu || f.filterAporte) return true

  // Y filtrar por Temporada o Episodio pidiendo solo la raíz no devuelve nada,
  // porque una temporada nunca es raíz. La tabla salía vacía y parecía que no
  // tenías ninguna.
  return TIPOS_QUE_CUELGAN.has(f.filterType ?? '')
}
