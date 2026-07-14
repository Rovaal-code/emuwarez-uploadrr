import { useState, useCallback } from 'react'
import { createPortal } from 'react-dom'

// Custom hover tooltip styled like the app's cards (opaque surface, not the
// native browser title box). Rendered in a fixed-position portal just below
// the cursor, so it is never clipped by table/overflow containers.

export function useTooltip(content: React.ReactNode, maxWidth = 460) {
  const [show, setShow] = useState(false)
  const [pt, setPt] = useState({ x: 0, y: 0 })

  const track = useCallback((e: React.MouseEvent) => setPt({ x: e.clientX, y: e.clientY }), [])
  const open = useCallback((e: React.MouseEvent) => { setPt({ x: e.clientX, y: e.clientY }); setShow(true) }, [])
  const close = useCallback(() => setShow(false), [])

  const triggerProps = {
    onMouseEnter: open,
    onMouseMove: track,
    onMouseLeave: close,
  }

  const tooltipNode = show && content != null
    ? createPortal(
        <div
          role="tooltip"
          style={{
            position: 'fixed',
            top: pt.y + 14,          // just below the cursor
            // Centre under the cursor, but clamp so a wide tooltip near a screen
            // edge (e.g. the top-right sync buttons) stays fully on screen.
            left: Math.min(
              Math.max(pt.x, maxWidth / 2 + 8),
              (typeof window !== 'undefined' ? window.innerWidth : 1280) - maxWidth / 2 - 8,
            ),
            transform: 'translateX(-50%)',
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
