import { useRef, useLayoutEffect } from 'react'

// Monospace one-liner (torrent name / internal title / expected name) that
// shrinks its font JUST ENOUGH to fit the whole string on one line — filling
// the box, never smaller than needed — down to `min`px. If the string already
// fits at `max`, it stays at `max` (e.g. a short title keeps full size).
export function FitText({ text, max = 13, min = 8 }: { text: string; max?: number; min?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    // Guard on the measured width: setting the font changes el's HEIGHT, which
    // re-fires the ResizeObserver — but the available WIDTH is unchanged, so we
    // skip and avoid an infinite measure→resize loop. A real container resize
    // changes the width and does re-fit.
    let lastAvail = -1
    const fit = () => {
      // `el` is width:100%, so clientWidth is the container's content width
      // (excludes padding) and is NOT affected by our font changes.
      const avail = el.clientWidth
      if (avail <= 0 || avail === lastAvail) return
      lastAvail = avail
      el.style.fontSize = `${max}px`
      const natural = el.scrollWidth // full text width at max font, one line
      if (natural <= avail) return   // fits at max → keep it big
      // Proportional shrink: the largest size whose text width ≤ avail. The −1
      // guards sub-pixel rounding so it never clips into an ellipsis.
      const size = Math.max(min, (max * (avail - 1)) / natural)
      el.style.fontSize = `${size}px`
    }
    fit()
    // Re-measure once layout has fully settled (modal open, fonts, etc.), since
    // the first synchronous pass can read a transient width.
    const raf = requestAnimationFrame(fit)
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    let cancelled = false
    if (document.fonts?.ready) document.fonts.ready.then(() => { if (!cancelled) { lastAvail = -1; fit() } })
    return () => { cancelled = true; cancelAnimationFrame(raf); ro.disconnect() }
  }, [text, max, min])
  return (
    <div ref={ref} style={{ fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', width: '100%', minWidth: 0 }}>
      {text}
    </div>
  )
}
