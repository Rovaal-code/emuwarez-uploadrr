import { useRef, useLayoutEffect, useState } from 'react'

// Binary-searches the LARGEST font size in [min,max] that makes `el`'s own
// text content fit on one line within `el`'s current width — mutates
// el.style.fontSize as it measures (that's how it's measured) and returns the
// chosen size. Pure w.r.t. everything except that one element's style.
function measureFitSize(el: HTMLElement, min: number, max: number): number {
  const avail = el.getBoundingClientRect().width
  if (avail <= 0) return max
  // 1px safety margin: `scrollWidth` is an integer (rounded) layout
  // measurement, but the browser's actual sub-pixel glyph paint can come out
  // a hair wider than that rounded value — a font size that measures as
  // "exactly touching" the boundary can then clip at paint time.
  const target = avail - 1
  el.style.fontSize = `${max}px`
  if (el.scrollWidth <= target) return max // fits at max → keep it big
  // Measure each candidate (scrollWidth) rather than estimate from a ratio:
  // monospace glyph advances don't scale perfectly linearly, so an estimate
  // can overflow by a sub-pixel and get clipped. Measuring guarantees the
  // final size shows the whole string, no "…".
  let lo = min, hi = max
  for (let i = 0; i < 18; i++) {
    const mid = (lo + hi) / 2
    el.style.fontSize = `${mid}px`
    if (el.scrollWidth <= target) lo = mid
    else hi = mid
  }
  el.style.fontSize = `${lo}px`
  return lo
}

const textStyle: React.CSSProperties = {
  // overflowX:auto (not hidden+ellipsis): if even `min` doesn't fully
  // eliminate overflow, the leftover scrolls into view instead of being
  // silently clipped behind a "…".
  fontFamily: 'monospace', whiteSpace: 'nowrap', overflowX: 'auto', overflowY: 'hidden', width: '100%', minWidth: 0,
}

// Monospace one-liner (torrent name / internal title / expected name) that
// shrinks its font JUST ENOUGH to fit the whole string on one line — filling
// the box, never smaller than needed — down to `min`px. If the string already
// fits at `max`, it stays at `max` (e.g. a short title keeps full size).
//
// `showSizeControls` adds a small −/+/↺ next to the text so a size that still
// looks wrong after the automatic fit can be dialed in by hand.
export function FitText({
  text, max = 13, min = 8, showSizeControls = false,
}: { text: string; max?: number; min?: number; showSizeControls?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const autoSizeRef = useRef(max)
  const [manualSize, setManualSize] = useState<number | null>(null)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    if (manualSize != null) {
      el.style.fontSize = `${manualSize}px`
      return
    }
    // Guard on the measured width: setting the font changes el's HEIGHT, which
    // re-fires the ResizeObserver — but the available WIDTH is unchanged, so we
    // skip and avoid an infinite measure→resize loop. Sub-pixel jitter
    // (<0.5px) between two reads of the same settled layout is "unchanged".
    let lastAvail = -1
    const fit = () => {
      const avail = el.getBoundingClientRect().width
      if (avail <= 0 || Math.abs(avail - lastAvail) < 0.5) return
      lastAvail = avail
      autoSizeRef.current = measureFitSize(el, min, max)
    }
    // No synchronous fit() here: right after mount, sibling content in the
    // same modal (other fields, async sections) can still be settling its own
    // layout, so a measurement taken THIS early can read a container width
    // that's temporarily too generous — briefly showing an oversized font
    // that then visibly shrinks once a later check corrects it (seen live: a
    // torrent name flashing 13px before settling at its real fitted size).
    // Waiting one frame (rAF) for the first real measurement avoids that.
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

  const textNode = <div ref={ref} style={textStyle}>{text}</div>

  if (!showSizeControls) return textNode

  return (
    <div style={{ width: '100%', minWidth: 0 }}>
      {textNode}
      <SizeControls value={manualSize} auto={autoSizeRef.current} onChange={setManualSize} />
    </div>
  )
}

export interface FitTextPairItem {
  label: string
  text: string
  labelStyle?: React.CSSProperties
}

// Fits TWO lines to a SHARED font size: whichever line needs to be smaller
// (usually the longer one — e.g. the torrent name has spaces/punctuation the
// dotted internal title doesn't) determines the size for BOTH, so a pair of
// related previews never renders at two subtly different sizes. Each item's
// own natural fit is measured independently, then the smaller of the two
// wins and is applied to both — since the smaller one already guarantees the
// other (which needed less room) fits too. Renders each item's own label
// above its text (so this is a drop-in for "label / value / label / value"),
// with a single shared size-control row at the end.
export function FitTextPair({
  items, max = 13, min = 8, showSizeControls = false,
}: {
  items: [FitTextPairItem, FitTextPairItem]
  max?: number
  min?: number
  showSizeControls?: boolean
}) {
  const refA = useRef<HTMLDivElement>(null)
  const refB = useRef<HTMLDivElement>(null)
  const autoSizeRef = useRef(max)
  const [manualSize, setManualSize] = useState<number | null>(null)

  useLayoutEffect(() => {
    const elA = refA.current
    const elB = refB.current
    if (!elA || !elB) return
    if (manualSize != null) {
      elA.style.fontSize = `${manualSize}px`
      elB.style.fontSize = `${manualSize}px`
      return
    }
    let lastAvailA = -1
    let lastAvailB = -1
    const fit = () => {
      const availA = elA.getBoundingClientRect().width
      const availB = elB.getBoundingClientRect().width
      if (availA <= 0 || availB <= 0) return
      if (Math.abs(availA - lastAvailA) < 0.5 && Math.abs(availB - lastAvailB) < 0.5) return
      lastAvailA = availA
      lastAvailB = availB
      const sizeA = measureFitSize(elA, min, max)
      const sizeB = measureFitSize(elB, min, max)
      const shared = Math.min(sizeA, sizeB)
      elA.style.fontSize = `${shared}px`
      elB.style.fontSize = `${shared}px`
      autoSizeRef.current = shared
    }
    // No synchronous fit() here — see FitText's comment: measuring before
    // sibling layout has settled can read a too-generous width and briefly
    // show an oversized font that then visibly shrinks a beat later.
    const raf = requestAnimationFrame(fit)
    const timers = [50, 150, 300].map(ms => window.setTimeout(fit, ms))
    const ro = new ResizeObserver(fit)
    ro.observe(elA)
    ro.observe(elB)
    let cancelled = false
    if (document.fonts?.ready) document.fonts.ready.then(() => {
      if (!cancelled) { lastAvailA = -1; lastAvailB = -1; fit() }
    })
    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      timers.forEach(clearTimeout)
      ro.disconnect()
    }
  }, [items[0].text, items[1].text, max, min, manualSize])

  return (
    <div style={{ width: '100%', minWidth: 0 }}>
      <div style={items[0].labelStyle}>{items[0].label}</div>
      <div ref={refA} style={textStyle}>{items[0].text}</div>
      <div style={{ ...items[1].labelStyle, marginTop: 10 }}>{items[1].label}</div>
      <div ref={refB} style={textStyle}>{items[1].text}</div>
      {showSizeControls && <SizeControls value={manualSize} auto={autoSizeRef.current} onChange={setManualSize} />}
    </div>
  )
}

function SizeControls({ value, auto, onChange }: {
  value: number | null
  auto: number
  onChange: (updater: (s: number | null) => number | null) => void
}) {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginTop: 4 }}>
      <button
        type="button"
        onClick={() => onChange(s => Math.max(4, Math.round((s ?? auto) - 1)))}
        title="Reducir tamaño de letra"
        style={debugBtnStyle}
      >−</button>
      <button
        type="button"
        onClick={() => onChange(s => Math.min(40, Math.round((s ?? auto) + 1)))}
        title="Aumentar tamaño de letra"
        style={debugBtnStyle}
      >+</button>
      {value != null && (
        <button type="button" onClick={() => onChange(() => null)} title="Volver al ajuste automático" style={debugBtnStyle}>↺</button>
      )}
      <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
        {value != null ? `${value}px (manual)` : `${auto.toFixed(1)}px (auto)`}
      </span>
    </div>
  )
}

const debugBtnStyle: React.CSSProperties = {
  fontSize: 11, lineHeight: 1, padding: '2px 6px', borderRadius: 4,
  border: '1px solid var(--border)', background: 'rgba(255,255,255,0.04)',
  color: 'var(--text-secondary)', cursor: 'pointer',
}
