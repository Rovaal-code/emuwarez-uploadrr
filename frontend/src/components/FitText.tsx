import { useRef, useLayoutEffect, useState } from 'react'

// Monospace one-liner (torrent name / internal title / expected name) that
// shrinks its font JUST ENOUGH to fit the whole string on one line — filling
// the box, never smaller than needed — down to `min`px. If the string already
// fits at `max`, it stays at `max` (e.g. a short title keeps full size). If it
// still doesn't fit even at `min` (an especially long name in a narrow box),
// the leftover scrolls horizontally rather than shrinking further or being
// clipped with "…" — callers that want to guarantee no scroll at all should
// pass a low enough `min` (down to 8) to accept a smaller font instead.
//
// `showSizeControls` adds a small −/+/↺ next to the text so a size that still
// looks wrong after the automatic fit can be dialed in by hand — a debugging
// aid while we track down what "the right size" actually looks like here,
// not meant as a permanent per-user setting.
export function FitText({
  text, max = 13, min = 8, showSizeControls = false,
}: { text: string; max?: number; min?: number; showSizeControls?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const autoSizeRef = useRef(max)
  const [manualSize, setManualSize] = useState<number | null>(null)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return

    // Manual override: skip the fit algorithm entirely, pin the size as-is.
    if (manualSize != null) {
      el.style.fontSize = `${manualSize}px`
      return
    }

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
      if (el.scrollWidth <= target) { autoSizeRef.current = max; return } // fits at max → keep it big
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
      autoSizeRef.current = lo
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
  }, [text, max, min, manualSize])

  const textNode = (
    // overflowX:auto (not hidden+ellipsis): with a raised `min`, the fit can
    // legitimately stop short of eliminating all overflow for an especially
    // long string — the leftover scrolls into view instead of being silently
    // clipped behind a "…".
    <div ref={ref} style={{ fontFamily: 'monospace', whiteSpace: 'nowrap', overflowX: 'auto', overflowY: 'hidden', width: '100%', minWidth: 0 }}>
      {text}
    </div>
  )

  if (!showSizeControls) return textNode

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, width: '100%', minWidth: 0 }}>
      {textNode}
      <div style={{ display: 'flex', gap: 2, flexShrink: 0 }}>
        <button
          type="button"
          onClick={() => setManualSize(s => Math.max(4, Math.round((s ?? autoSizeRef.current) - 1)))}
          title="Reducir tamaño de letra"
          style={debugBtnStyle}
        >−</button>
        <button
          type="button"
          onClick={() => setManualSize(s => Math.min(40, Math.round((s ?? autoSizeRef.current) + 1)))}
          title="Aumentar tamaño de letra"
          style={debugBtnStyle}
        >+</button>
        {manualSize != null && (
          <button type="button" onClick={() => setManualSize(null)} title="Volver al ajuste automático" style={debugBtnStyle}>↺</button>
        )}
        <span style={{ fontSize: 10, color: 'var(--text-muted)', alignSelf: 'center' }}>
          {manualSize != null ? `${manualSize}px (manual)` : `${autoSizeRef.current.toFixed(1)}px (auto)`}
        </span>
      </div>
    </div>
  )
}

const debugBtnStyle: React.CSSProperties = {
  fontSize: 11, lineHeight: 1, padding: '2px 6px', borderRadius: 4,
  border: '1px solid var(--border)', background: 'rgba(255,255,255,0.04)',
  color: 'var(--text-secondary)', cursor: 'pointer',
}
