import { useState, useCallback, useRef, useLayoutEffect } from 'react'
import { createPortal } from 'react-dom'

// Custom hover tooltip styled like the app's cards (opaque surface, not the
// native browser title box). Rendered in a fixed-position portal just below
// the cursor, so it is never clipped by table/overflow containers.

export function useTooltip(content: React.ReactNode, maxWidth = 460) {
  const [show, setShow] = useState(false)
  const [pt, setPt] = useState({ x: 0, y: 0 })
  // Once measured, the box gets an EXPLICIT width so its size is fixed: it wraps
  // to the same 2 lines no matter where on screen it lands. Without this, moving
  // the box near a screen edge shrinks the space available to it and the browser
  // re-wraps the text into many narrow lines.
  const [width, setWidth] = useState<number | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  const track = useCallback((e: React.MouseEvent) => setPt({ x: e.clientX, y: e.clientY }), [])
  const open = useCallback((e: React.MouseEvent) => { setPt({ x: e.clientX, y: e.clientY }); setShow(true) }, [])
  const close = useCallback(() => { setShow(false); setWidth(null) }, [])

  // First render happens in "measure mode" (anchored top-left with full room, so
  // the text wraps to its natural width, capped at maxWidth) and is hidden. We
  // read that natural width here and freeze it; every later render uses it.
  useLayoutEffect(() => {
    if (!show) return
    const el = ref.current
    if (el && width == null) setWidth(el.offsetWidth)
  }, [show, width])

  const triggerProps = {
    onMouseEnter: open,
    onMouseMove: track,
    onMouseLeave: close,
  }

  // Centre under the cursor, then clamp by the (now fixed) half-width so the box
  // stays fully on screen without ever changing size or re-wrapping.
  const half = (width ?? maxWidth) / 2
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1280
  const left = Math.min(Math.max(pt.x, half + 6), vw - half - 6)

  const tooltipNode = show && content != null
    ? createPortal(
        <div
          ref={ref}
          role="tooltip"
          style={{
            position: 'fixed',
            top: pt.y + 14,          // just below the cursor
            // measure mode: anchored at x=8 with full room; display mode: centred
            left: width == null ? 8 : left,
            transform: width == null ? 'none' : 'translateX(-50%)',
            width: width ?? undefined,     // fixed once measured → never re-wraps
            maxWidth,
            visibility: width == null ? 'hidden' : 'visible',
            zIndex: 2000,
            background: 'var(--bg-surface, #0f1420)',   // opaque
            border: '1px solid var(--border)',
            borderRadius: 10,
            boxShadow: 'var(--shadow-modal, 0 10px 30px rgba(0,0,0,0.45))',
            padding: '10px 12px',
            fontSize: 12.5,
            lineHeight: 1.45,
            color: 'var(--text-secondary)',
            textAlign: 'left',
            whiteSpace: 'normal',
            pointerEvents: 'none',
          }}
        >
          {content}
        </div>,
        document.body,
      )
    : null

  return { triggerProps, tooltipNode }
}

export function Tooltip({ content, children, style, maxWidth }: {
  content: React.ReactNode
  children: React.ReactNode
  style?: React.CSSProperties
  maxWidth?: number
}) {
  const { triggerProps, tooltipNode } = useTooltip(content, maxWidth)
  return (
    <span {...triggerProps} style={{ display: 'inline-flex', alignItems: 'center', ...style }}>
      {children}
      {tooltipNode}
    </span>
  )
}
