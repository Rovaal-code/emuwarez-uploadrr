import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Simple countdown cooldown. Call `start(seconds)` to begin; `remaining`
 * ticks down to 0 once per second and `active` is true while it runs.
 *
 * Used to throttle "Probar conexión" buttons on the client so they cannot
 * hammer the real eMuwarez server between the backend's own 1/minute limit.
 */
export function useCooldown() {
  const [remaining, setRemaining] = useState(0)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (remaining <= 0) {
      if (timer.current) {
        clearInterval(timer.current)
        timer.current = null
      }
      return
    }
    if (!timer.current) {
      timer.current = setInterval(() => {
        setRemaining((r) => (r <= 1 ? 0 : r - 1))
      }, 1000)
    }
    return () => {
      if (timer.current) {
        clearInterval(timer.current)
        timer.current = null
      }
    }
  }, [remaining])

  const start = useCallback((seconds: number) => {
    setRemaining((r) => Math.max(r, Math.ceil(seconds)))
  }, [])

  return { remaining, active: remaining > 0, start }
}
