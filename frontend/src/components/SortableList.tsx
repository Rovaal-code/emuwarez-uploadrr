import { useLayoutEffect, useRef, useState } from 'react'

// 1×1 transparent GIF used to hide the browser's default (shrunk/translucent)
// drag ghost — the feedback is the in-list illumination + slide instead.
const TRANSPARENT_IMG = typeof Image !== 'undefined'
  ? (() => { const i = new Image(); i.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'; return i })()
  : null

export interface DragHandleProps {
  onMouseDown: () => void
  onMouseUp: () => void
  style: React.CSSProperties
  title: string
}

// A drag-to-reorder list where rows are only grabbable from a handle, the
// grabbed row lights up, the native ghost is hidden, and rows slide to their
// new positions (FLIP animation) as the order changes live under the cursor.
export function SortableList({ ids, onChange, renderRow, gap = 6 }: {
  ids: string[]
  onChange: (ids: string[]) => void
  renderRow: (id: string, index: number, ctx: { dragging: boolean; handleProps: DragHandleProps }) => React.ReactNode
  gap?: number
}) {
  const [grabbedId, setGrabbedId] = useState<string | null>(null)
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const nodeRefs = useRef<Map<string, HTMLElement>>(new Map())
  const prevRects = useRef<Map<string, DOMRect>>(new Map())
  const prevIds = useRef<string[]>(ids)

  // FLIP: animate each row from its previous position to the new one — but ONLY
  // when the ORDER actually changed. Otherwise an unrelated re-render that
  // shifts the whole list (e.g. a save button appearing above it) would look
  // like a reorder and slide every row.
  useLayoutEffect(() => {
    const orderChanged = prevIds.current.length !== ids.length
      || prevIds.current.some((v, i) => v !== ids[i])
    if (orderChanged) {
      nodeRefs.current.forEach((node, id) => {
        const prev = prevRects.current.get(id)
        if (prev) {
          const dy = prev.top - node.getBoundingClientRect().top
          if (dy) {
            node.style.transition = 'none'
            node.style.transform = `translateY(${dy}px)`
            requestAnimationFrame(() => {
              node.style.transition = 'transform 170ms ease'
              node.style.transform = ''
            })
          }
        }
      })
    }
    // Always refresh the baseline so the next reorder measures from where the
    // rows currently are (even after a plain layout shift).
    const map = new Map<string, DOMRect>()
    nodeRefs.current.forEach((node, id) => map.set(id, node.getBoundingClientRect()))
    prevRects.current = map
    prevIds.current = ids
  }, [ids])

  // Reorder only once the cursor crosses the target row's midpoint in the
  // direction of travel. Without this, moving over an adjacent row ping-pongs
  // (the moved row lands under the cursor and immediately triggers a move back).
  function handleDragOver(e: React.DragEvent<HTMLDivElement>, targetId: string) {
    e.preventDefault()
    if (!draggingId || draggingId === targetId) return
    const from = ids.indexOf(draggingId)
    const to = ids.indexOf(targetId)
    if (from < 0 || to < 0) return
    const rect = e.currentTarget.getBoundingClientRect()
    const past = (e.clientY - rect.top) / rect.height  // 0 = top … 1 = bottom
    if (to > from && past < 0.5) return  // going down, not past the midpoint yet
    if (to < from && past > 0.5) return  // going up, not past the midpoint yet
    const list = [...ids]
    list.splice(from, 1)
    list.splice(to, 0, draggingId)
    onChange(list)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap }}>
      {ids.map((id, index) => {
        const handleProps: DragHandleProps = {
          onMouseDown: () => setGrabbedId(id),
          onMouseUp: () => setGrabbedId(null),
          style: { cursor: 'grab', userSelect: 'none' },
          title: 'Arrastrar para reordenar',
        }
        return (
          <div
            key={id}
            ref={n => { if (n) nodeRefs.current.set(id, n); else nodeRefs.current.delete(id) }}
            draggable={grabbedId === id}
            onDragStart={e => {
              setDraggingId(id)
              if (TRANSPARENT_IMG) e.dataTransfer.setDragImage(TRANSPARENT_IMG, 0, 0)
              e.dataTransfer.effectAllowed = 'move'
            }}
            onDragOver={e => handleDragOver(e, id)}
            onDragEnd={() => { setDraggingId(null); setGrabbedId(null) }}
          >
            {renderRow(id, index, { dragging: grabbedId === id || draggingId === id, handleProps })}
          </div>
        )
      })}
    </div>
  )
}
