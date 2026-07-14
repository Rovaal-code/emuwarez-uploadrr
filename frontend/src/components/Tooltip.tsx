import { useState, useCallback, useRef, useLayoutEffect } from 'react'
import { createPortal } from 'react-dom'

// Custom hover tooltip styled like the app's cards (opaque surface, not the
// native browser title box). Rendered in a fixed-position portal just below
// the cursor, so it is never clipped by table/overflow containers.

export function useTooltip(content: React.ReactNode, maxWidth = 460) {
  const [show, setShow] = useState(false)
  const [pt, setPt] = useState({ x: 0, y: 0 })
  const ref = useRef<HTMLDivElement>(null)

  const track = useCallback((e: React.MouseEvent) => setPt({ x: e.clientX, y: e.clientY }), [])
  const open = useCallback((e: React.MouseEvent) => { setPt({ x: e.clientX, y: e.clientY }); setShow(true) }, [])
  const close = useCallback(() => setShow(false), [])

  // Clamp using the REAL rendered width (not the max), so a narrow tooltip can
  // still reach the right edge instead of leaving a gap.
  useLayoutEffect(() => {
    const el = ref.current
    if (!show || !el) return
    const half = el.offsetWidth / 2
    const clamped = Math.min(Math.max(pt.x, half + 6), window.innerWidth - half - 6)
    el.style.left = `${clamped}px`
  }, [show, pt.x, pt.y])

  const triggerProps = {
    onMouseEnter: open,
    onMouseMove: track,
    onMouseLeave: close,
  }

  const tooltipNode = show && content != null
    ? createPortal(
        <div
          ref={ref}
          role="tooltip"
          style={{
            position: 'fixed',
            top: pt.y + 14,          // just below the cursor
            left: pt.x,              // centred under the cursor; useLayoutEffect
            transform: 'translateX(-50%)',  // clamps it to the viewport by real width
            maxWidth,
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
            // Hard cap of 3 lines: the box never grows beyond that; longer text
            // is truncated with "…". At maxWidth most texts fit in ~2 lines.
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
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
