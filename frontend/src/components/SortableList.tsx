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

  // FLIP: animate each row from its previous position to the new one.
  useLayoutEffect(() => {
    nodeRefs.current.forEach((node, id) => {
      const prev = prevRects.current.get(id)
      if (prev) {
        const cur = node.getBoundingClientRect()
        const dy = prev.top - cur.top
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
    const map = new Map<string, DOMRect>()
    nodeRefs.current.forEach((node, id) => map.set(id, node.getBoundingClientRect()))
    prevRects.current = map
  }, [ids])

  function reorder(targetId: string) {
    if (!draggingId || draggingId === targetId) return
    const list = [...ids]
    const from = list.indexOf(draggingId)
    const to = list.indexOf(targetId)
    if (from < 0 || to < 0) return
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
            onDragEnter={() => reorder(id)}
            onDragOver={e => e.preventDefault()}
            onDragEnd={() => { setDraggingId(null); setGrabbedId(null) }}
          >
            {renderRow(id, index, { dragging: grabbedId === id || draggingId === id, handleProps })}
          </div>
        )
      })}
    </div>
  )
}
