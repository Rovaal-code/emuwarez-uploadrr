import { useState, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'

// Custom hover tooltip styled like the app's cards (not the native browser
// title box). Rendered in a fixed-position portal so it is never clipped by
// table/overflow containers. Reusable anywhere a hover explanation is needed.

export function useTooltip(content: React.ReactNode, maxWidth = 260) {
  const ref = useRef<HTMLElement | null>(null)
  const [show, setShow] = useState(false)
  const [pos, setPos] = useState({ top: 0, left: 0, above: true })

  const open = useCallback(() => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const above = r.top > 140                       // flip below if near the top
    setPos({ top: above ? r.top : r.bottom, left: r.left + r.width / 2, above })
    setShow(true)
  }, [])
  const close = useCallback(() => setShow(false), [])

  const triggerProps = {
    ref: ref as React.Ref<never>,
    onMouseEnter: open,
    onMouseLeave: close,
    onFocus: open,
    onBlur: close,
  }

  const tooltipNode = show && content != null
    ? createPortal(
        <div
          role="tooltip"
          style={{
            position: 'fixed',
            top: pos.top,
            left: pos.left,
            transform: `translate(-50%, ${pos.above ? 'calc(-100% - 8px)' : '8px'})`,
            maxWidth,
            zIndex: 2000,
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 10,
            boxShadow: 'var(--shadow-modal, 0 10px 30px rgba(0,0,0,0.4))',
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
