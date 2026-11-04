export interface EntradaIndice { id: string; titulo: string }

// Salto a cada tarjeta de Configuración, con un buscador que filtra las tarjetas.
export function IndiceSecciones({ entradas, activa, consulta, onConsulta, onSaltar }: {
  entradas: EntradaIndice[]
  activa: string
  consulta: string
  onConsulta: (c: string) => void
  onSaltar: (id: string) => void
}) {
  return (
    <aside className="aj-indice">
      <input
        type="search"
        className="form-input aj-indice__buscar"
        value={consulta}
        onChange={e => onConsulta(e.target.value)}
        placeholder="Buscar ajuste"
        aria-label="Buscar en Configuración"
        autoComplete="off"
      />
      <nav aria-label="Secciones de Configuración">
        <ul className="aj-indice__lista">
          {entradas.map(e => (
            <li key={e.id}>
              <button
                type="button"
                className={`aj-indice__enlace${e.id === activa ? ' activa' : ''}`}
                aria-current={e.id === activa ? 'true' : undefined}
                onClick={() => onSaltar(e.id)}
              >
                {e.titulo}
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  )
}
