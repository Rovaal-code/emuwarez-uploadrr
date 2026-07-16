// Make the drag image an opaque, full-size clone of the row being dragged, so
// it looks like the real card moving instead of the browser's shrunk/translucent
// default ghost.
export function setFullSizeDragImage(e: React.DragEvent<HTMLElement>) {
  const el = e.currentTarget
  const rect = el.getBoundingClientRect()
  const clone = el.cloneNode(true) as HTMLElement
  clone.style.position = 'fixed'
  clone.style.top = '-10000px'
  clone.style.left = '0'
  clone.style.width = `${rect.width}px`
  clone.style.margin = '0'
  clone.style.opacity = '1'
  clone.style.pointerEvents = 'none'
  clone.style.boxShadow = '0 8px 24px rgba(0,0,0,0.45)'
  document.body.appendChild(clone)
  e.dataTransfer.setDragImage(clone, e.clientX - rect.left, e.clientY - rect.top)
  e.dataTransfer.effectAllowed = 'move'
  // The browser snapshots the clone synchronously; drop it right after.
  setTimeout(() => clone.remove(), 0)
}
