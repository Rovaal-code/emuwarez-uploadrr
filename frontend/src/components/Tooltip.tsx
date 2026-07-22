import { useState, useCallback, useRef, useLayoutEffect, useEffect } from 'react'
import { createPortal } from 'react-dom'

// Custom hover tooltip styled like the app's cards (opaque surface, not the
// native browser title box). Rendered in a fixed-position portal just below
// the cursor, so it is never clipped by table/overflow containers.

// Hover dwell before a tooltip appears (ms). The box shows only after the
// cursor has rested on the target for this long.
const HOVER_DELAY_MS = 1000

export function useTooltip(content: React.ReactNode, maxWidth = 460) {
  const [show, setShow] = useState(false)
  const [pt, setPt] = useState({ x: 0, y: 0 })
  const ref = useRef<HTMLDivElement>(null)
  const timer = useRef<number | null>(null)

  const track = useCallback((e: React.MouseEvent) => setPt({ x: e.clientX, y: e.clientY }), [])
  const open = useCallback((e: React.MouseEvent) => {
    setPt({ x: e.clientX, y: e.clientY })
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setShow(true), HOVER_DELAY_MS)
  }, [])
  const close = useCallback(() => {
    if (timer.current) { window.clearTimeout(timer.current); timer.current = null }
    setShow(false)
  }, [])

  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current) }, [])

  // `max-content` capped at maxWidth wraps long text, but leaves the box as wide
  // as the cap even when the wrapped lines are shorter. So after it wraps, we
  // measure the LONGEST actually-rendered line and shrink the box to it — the
  // box then hugs the text on every line. Then clamp the position on screen.
  useLayoutEffect(() => {
    const el = ref.current
    if (!show || !el) return
    el.style.width = 'max-content'
    const range = document.createRange()
    range.selectNodeContents(el)
    let longest = 0
    for (const r of range.getClientRects()) longest = Math.max(longest, r.width)
    if (longest > 0) {
      // + horizontal padding (24px) + border (2px)
      el.style.width = `${Math.ceil(longest) + 26}px`
    }
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
            transform: 'translateX(-50%)',  // then clamps it onto the screen
            width: 'max-content',    // hug the text; cap at maxWidth
            maxWidth,
            whiteSpace: 'normal',
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

// Drop-in replacement for a plain element with a native `title=` attribute —
// same tag/className/style/onClick, just with the app's own styled tooltip
// instead of the browser's default box. Exists so a title-link rendered
// inside a `.map()` (where a hook can't be called directly) still gets one:
// this is a real component instance per row, so its own useTooltip() call
// is perfectly legal.
export function HoverTitle({ as = 'div', className, style, onClick, onMouseDown, onMouseUp, tip, children }: {
  as?: 'div' | 'span'
  className?: string
  style?: React.CSSProperties
  onClick?: (e: React.MouseEvent) => void
  onMouseDown?: (e: React.MouseEvent) => void
  onMouseUp?: (e: React.MouseEvent) => void
  tip: string
  children: React.ReactNode
}) {
  const { triggerProps, tooltipNode } = useTooltip(tip)
  const Tag = as as 'div'
  return (
    <Tag className={className} style={style} onClick={onClick} onMouseDown={onMouseDown} onMouseUp={onMouseUp} {...triggerProps}>
      {children}
      {tooltipNode}
    </Tag>
  )
}
