import { useRef, useLayoutEffect } from 'react'

// Monospace one-liner (torrent name / internal title / expected name) that
// shrinks its font so the whole string fits on a single line instead of
// wrapping, down to `min`px.
export function FitText({ text, max = 13, min = 8 }: { text: string; max?: number; min?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const fit = () => {
      el.style.fontSize = `${max}px`
      if (el.clientWidth === 0 || el.scrollWidth <= el.clientWidth) return  // fits at max
      // Binary-search the LARGEST font size in [min, max] that still fits on one
      // line, so it fills the box instead of shrinking too far (a single
      // proportional estimate undershoots).
      let lo = min, hi = max
      for (let i = 0; i < 14; i++) {
        const mid = (lo + hi) / 2
        el.style.fontSize = `${mid}px`
        if (el.scrollWidth <= el.clientWidth) lo = mid
        else hi = mid
      }
      el.style.fontSize = `${lo}px`
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [text, max, min])
  return (
    <div ref={ref} style={{ fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
      {text}
    </div>
  )
}
