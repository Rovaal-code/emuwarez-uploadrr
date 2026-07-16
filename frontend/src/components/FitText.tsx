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
      const avail = el.clientWidth
      const full = el.scrollWidth
      if (full > avail && avail > 0) {
        el.style.fontSize = `${Math.max(min, Math.floor((max * avail) / full))}px`
      }
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
