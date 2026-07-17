import { useRef, useLayoutEffect } from 'react'

// Monospace one-liner (torrent name / internal title / expected name) that
// shrinks its font JUST ENOUGH to fit the whole string on one line — filling
// the box, never smaller than needed — down to `min`px. If the string already
// fits at `max`, it stays at `max` (e.g. a short title keeps full size).
//
// Confirmed correct with a live diagnostic readout on a real 85-char torrent
// name: avail=648.8px, and even at the floor (min=8px) the text measured
// 649px — i.e. this component was already filling ~100% of the space it
// actually has. The container's own width (the modal), not this fitting
// logic, is what determines how big the text can get on one line — see
// UploadWizardModal's 960px comment.
export function FitText({ text, max = 13, min = 8 }: { text: string; max?: number; min?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    // Guard on the measured width: setting the font changes el's HEIGHT, which
    // re-fires the ResizeObserver — but the available WIDTH is unchanged, so we
    // skip and avoid an infinite measure→resize loop. A real container resize
    // changes the width and does re-fit. Sub-pixel jitter (<0.5px) between two
    // reads of the same settled layout is treated as "unchanged" too.
    let lastAvail = -1
    const fit = () => {
      // getBoundingClientRect gives a precise, fractional content-box width —
      // `el` has no border/padding of its own (width:100% of its parent), so
      // this is exactly the space available for text.
      const avail = el.getBoundingClientRect().width
      if (avail <= 0 || Math.abs(avail - lastAvail) < 0.5) return
      lastAvail = avail
      // 1px safety margin: `scrollWidth` is an integer (rounded) layout
      // measurement, but the browser's actual sub-pixel glyph paint can come
      // out a hair wider than that rounded value — a font size that measures
      // as "exactly touching" the boundary can then clip into "…" at paint
      // time. 1px absorbs that without being a big enough buffer to visibly
      // under-size the text.
      const target = avail - 1
      el.style.fontSize = `${max}px`
      if (el.scrollWidth <= target) return // fits at max → keep it big
      // Binary-search the LARGEST font that actually MEASURES as fitting. We
      // measure each candidate (scrollWidth) rather than estimate from a ratio:
      // monospace glyph advances don't scale perfectly linearly, so an estimate
      // can overflow by a sub-pixel and get clipped into an ellipsis. Measuring
      // guarantees the final size shows the whole string, no "…".
      let lo = min, hi = max
      for (let i = 0; i < 18; i++) {
        const mid = (lo + hi) / 2
        el.style.fontSize = `${mid}px`
        if (el.scrollWidth <= target) lo = mid
        else hi = mid
      }
      el.style.fontSize = `${lo}px`
    }
    fit()
    // A couple of re-checks catch layout that's still settling after the
    // first frame — each is a cheap no-op once the width has stabilized.
    const raf = requestAnimationFrame(fit)
    const timers = [50, 150, 300].map(ms => window.setTimeout(fit, ms))
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    let cancelled = false
    if (document.fonts?.ready) document.fonts.ready.then(() => { if (!cancelled) { lastAvail = -1; fit() } })
    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      timers.forEach(clearTimeout)
      ro.disconnect()
    }
  }, [text, max, min])
  return (
    <div ref={ref} style={{ fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', width: '100%', minWidth: 0 }}>
      {text}
    </div>
  )
}
