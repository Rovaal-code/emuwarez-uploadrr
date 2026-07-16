import { useRef, useLayoutEffect } from 'react'

// Monospace one-liner (torrent name / internal title / expected name) that
// shrinks its font so the whole string fits on a single line instead of
// wrapping, down to `min`px.
export function FitText({ text, max = 13, min = 8 }: { text: string; max?: number; min?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    const parent = el?.parentElement
    if (!el || !parent) return
    const fit = () => {
      // `el` is width:100%, so its clientWidth is the real available width
      // (the container's CONTENT box, i.e. excluding the container's padding) —
      // and it doesn't shrink-wrap to the text. Using the parent's clientWidth
      // instead would over-count by the padding and let the text overflow.
      const avail = el.clientWidth
      if (avail <= 0) return
      el.style.fontSize = `${max}px`
      if (el.scrollWidth <= avail) return          // fits at max
      // Binary-search the LARGEST font size in [min, max] that fits on one line
      // (2px margin so sub-pixel rounding never clips it with an ellipsis).
      let lo = min, hi = max
      for (let i = 0; i < 14; i++) {
        const mid = (lo + hi) / 2
        el.style.fontSize = `${mid}px`
        if (el.scrollWidth <= avail - 2) lo = mid
        else hi = mid
      }
      el.style.fontSize = `${lo}px`
    }
    fit()
    // Observe the PARENT (not `el`) so changing the font — which alters el's
    // height — doesn't retrigger the observer in a loop.
    const ro = new ResizeObserver(fit)
    ro.observe(parent)
    return () => ro.disconnect()
  }, [text, max, min])
  return (
    <div ref={ref} style={{ fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', width: '100%', minWidth: 0 }}>
      {text}
    </div>
  )
}
