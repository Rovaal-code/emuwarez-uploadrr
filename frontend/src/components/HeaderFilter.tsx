import { useState, useRef, useEffect, useLayoutEffect, useId } from 'react'
import { createPortal } from 'react-dom'
import { useTooltip } from './Tooltip'
import { medir, anchoVentana, altoVentana } from '../utils/uiScale'
import { resumenFiltro, siguienteSeleccion, siguienteExclusion, opcionesQueCoinciden, EXCLUIDO } from '../utils/filtroColumna'

export interface FilterOption { value: string; label: string }

// Its own component (not inlined in the .map() below) so useTooltip's hook
// call is legal — the option list is a plain callback invoked once per row,
// not a separate component instance.
//
// Con selección múltiple cada opción es una casilla de verdad: antes era un
// botón con una ✓ que solo salía al marcarlo, y nada decía que se pudiera
// elegir más de uno. Un <input type="checkbox"> se ve como tal, se marca con
// la barra espaciadora y el lector de pantalla lo anuncia como casilla.
// «Desmarcar todo» (la opción de valor '') se queda como botón: quita el
// filtro, no es un valor más.
//
// Con `onOcultar` la casilla lleva al lado un botón que oculta ese valor: la
// fila queda tachada y todo lo que lo tenga desaparece de la tabla.
function FilterOptionButton({ option, selected, oculta, multiple, onClick, onOcultar, disabled = false }: {
  option: FilterOption; selected: boolean; oculta: boolean; multiple: boolean; onClick: () => void; onOcultar?: () => void
  disabled?: boolean
}) {
  const { triggerProps, tooltipNode } = useTooltip(option.label)
  if (multiple) {
    return (
      <div className="hf-fila">
        <label className={`hf-option hf-check${selected ? ' selected' : ''}${oculta ? ' hf-oculta' : ''}`} {...triggerProps}>
          <input type="checkbox" checked={selected} onChange={onClick} />
          <span>{option.label}</span>
          {tooltipNode}
        </label>
        {onOcultar && (
          <button
            type="button"
            className={`hf-ocultar${oculta ? ' on' : ''}`}
            onClick={onOcultar}
            aria-pressed={oculta}
            aria-label={`Ocultar ${option.label}`}
            title={oculta ? 'Dejar de ocultar' : 'Ocultar'}
          >⊘</button>
        )}
      </div>
    )
  }
  return (
    <button
      type="button"
      className={`hf-option${selected ? ' selected' : ''}`}
      onClick={onClick}
      disabled={disabled}
      {...triggerProps}
    >
      {option.label}
      {tooltipNode}
    </button>
  )
}

// Excel-style column-header filter: the column title with a small dropdown
// caret; clicking opens a menu of options. When a filter is active the title
// (and caret) turn blue so it's obvious a filter is applied.
//
// Toda la cabecera es el botón, no solo la flecha: la flecha medía 16 px y era
// lo único que abría el menú, así que pinchar en el nombre de la columna no
// hacía nada. El <th> que la contiene pierde su relleno (components.css,
// `th:has(> .hf-trigger)`) para que el botón ocupe la celda entera.
//
// Con `value` como lista es de selección múltiple: cada opción se marca o
// desmarca sin cerrar el menú, y la de valor '' («Desmarcar todo») las quita.
export function HeaderFilter<T extends string | string[]>({ label, value, options, onChange, ocultable }: {
  label: string
  value: T
  options: FilterOption[]
  onChange: (v: T) => void
  // Cada opción puede ocultarse, además de marcarse (solo con selección múltiple).
  ocultable?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const [texto, setTexto] = useState('')
  const btnRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const menuId = useId()
  const multiple = Array.isArray(value)
  const elegidos: string[] = Array.isArray(value) ? value : value ? [value] : []
  const active = elegidos.length > 0
  const accent = 'var(--text-accent)'
  const resumen = resumenFiltro(elegidos, options)
  // Con muchas opciones (los grupos de release son cientos) se busca escribiendo.
  const buscador = options.length > 10
  const visibles = opcionesQueCoinciden(options, texto)
  const { triggerProps: caretTip, tooltipNode: caretTooltip } = useTooltip(
    active ? `Filtrado: ${resumen}` : multiple ? 'Filtrar (puedes marcar varios)' : 'Filtrar',
  )
  const cerrar = (devolverFoco: boolean) => {
    setOpen(false)
    if (devolverFoco) btnRef.current?.focus()
  }
  const elegir = (v: string) => {
    if (!multiple) {
      onChange(v as T)
      cerrar(true)
      return
    }
    const sig = siguienteSeleccion(elegidos, v)
    if (sig !== elegidos) onChange(sig as T)
  }
  const ocultar = (v: string) => onChange(siguienteExclusion(elegidos, v) as T)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: PointerEvent) => {
      const t = e.target as Node
      if (menuRef.current?.contains(t) || btnRef.current?.contains(t)) return
      setOpen(false)
    }
    // Escape devuelve el foco a la cabecera: si no, quien usa el teclado se
    // queda con el foco en una casilla que acaba de desaparecer.
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') cerrar(true) }
    document.addEventListener('pointerdown', onDoc)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('pointerdown', onDoc)
      document.removeEventListener('keydown', onEsc)
    }
  }, [open])

  const toggle = () => {
    // medir() y no getBoundingClientRect(): lo que sale de aquí acaba en un
    // style.top/left, que el zoom del body vuelve a escalar. Ver utils/uiScale.
    const r = btnRef.current ? medir(btnRef.current) : null
    if (r) setPos({ top: r.bottom + 4, left: r.left })
    setTexto('')
    setOpen(o => !o)
  }

  // Longer option labels (provider names, eMuwarez authors/sources — all
  // unbounded strings from the backend) could otherwise push the menu past
  // the right/bottom edge of the viewport, since it's positioned from the
  // button alone with no clamping. Re-clamp once the menu has real
  // dimensions to measure (before paint, so there's no visible jump).
  //
  // Al abrir, el foco pasa a la primera opción: el menú vive en un portal al
  // final del body, y con el tabulador no se llegaría a él desde la cabecera.
  useLayoutEffect(() => {
    if (!open) return
    const menu = menuRef.current
    const btn = btnRef.current
    if (!menu || !btn) return
    const menuRect = medir(menu)
    const btnRect = medir(btn)
    const maxLeft = anchoVentana() - menuRect.width - 8
    const maxTop = altoVentana() - menuRect.height - 8
    setPos({
      left: Math.max(8, Math.min(btnRect.left, maxLeft)),
      top: Math.max(8, Math.min(btnRect.bottom + 4, maxTop)),
    })
    menu.querySelector<HTMLElement>('input, button')?.focus({ preventScroll: true })
  }, [open])

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className={`hf-trigger${active ? ' active' : ''}`}
        onClick={e => { e.stopPropagation(); toggle() }}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={active ? `Filtrar ${label} (filtrado: ${resumen})` : `Filtrar ${label}`}
        style={{ color: active ? accent : undefined }}
        {...caretTip}
      >
        <span>{label}</span>
        <span aria-hidden className="hf-caret" style={{ color: active ? accent : undefined }}>▼</span>
        {multiple && elegidos.length > 1 && <span aria-hidden className="hf-count">{elegidos.length}</span>}
        {/* Con el menú abierto taparía el buscador. */}
        {!open && caretTooltip}
      </button>

      {open && createPortal(
        <div
          ref={menuRef}
          id={menuId}
          role="dialog"
          aria-label={`Filtrar ${label}`}
          onClick={e => e.stopPropagation()}
          className="menores-filtro-panel"
          style={{ top: pos.top, left: pos.left }}
        >
          {buscador && (
            <input
              type="search"
              name="buscar-valor"
              autoComplete="off"
              className="form-input hf-search"
              placeholder="Buscar…"
              aria-label={`Buscar en ${label}`}
              value={texto}
              onChange={e => setTexto(e.target.value)}
            />
          )}
          {multiple && <div className="hf-hint">{ocultable ? 'Marca uno o varios · ⊘ oculta' : 'Marca uno o varios'}</div>}
          {visibles.map(o => (
            <FilterOptionButton
              key={o.value || '__all__'}
              // En selección múltiple la opción '' no elige «Todos»: desmarca
              // lo marcado. Llamarla «Todos» al lado de casillas confundía.
              option={multiple && o.value === '' ? { ...o, label: 'Desmarcar todo' } : o}
              // «Desmarcar todo» no es una opción elegida: sin nada marcado se apaga en vez de salir resaltada.
              selected={o.value === '' ? !multiple && !active : elegidos.includes(o.value)}
              disabled={multiple && o.value === '' && !active}
              oculta={elegidos.includes(EXCLUIDO + o.value)}
              onOcultar={ocultable && multiple && o.value !== '' ? () => ocultar(o.value) : undefined}
              // «Desmarcar todo» no es una casilla sino el botón que lo quita: con
              // nada elegido saldría marcada y desmarcarla no haría nada.
              multiple={multiple && o.value !== ''}
              onClick={() => elegir(o.value)}
            />
          ))}
          {texto.trim() && visibles.every(o => o.value === '') && <div className="hf-hint hf-empty">Sin coincidencias</div>}
        </div>,
        document.body,
      )}
    </>
  )
}
