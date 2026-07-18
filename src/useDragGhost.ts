import { useCallback, useEffect, useRef } from 'react'

/**
 * Moves the lifted letter outside React's render cycle. Pointer events can fire
 * far more often than the screen refreshes; updating the DOM once per frame
 * keeps the whole crossword board immobile and responsive on older phones.
 */
export function useDragGhost() {
  const ghostRef = useRef<HTMLDivElement | null>(null)
  const frameRef = useRef<number | null>(null)
  const pointRef = useRef({ x: 0, y: 0, previousX: 0 })

  const flush = useCallback(() => {
    frameRef.current = null
    const ghost = ghostRef.current
    if (!ghost) return
    const { x, y, previousX } = pointRef.current
    const tilt = Math.max(-5, Math.min(5, (x - previousX) * .22))
    ghost.style.left = `${x}px`
    ghost.style.top = `${y}px`
    ghost.style.rotate = `${tilt}deg`
    pointRef.current.previousX = x
  }, [])

  const moveGhost = useCallback((x: number, y: number) => {
    pointRef.current.x = x
    pointRef.current.y = y
    if (frameRef.current === null) frameRef.current = window.requestAnimationFrame(flush)
  }, [flush])

  const stopGhost = useCallback(() => {
    if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current)
    frameRef.current = null
    if (ghostRef.current) ghostRef.current.style.rotate = '0deg'
  }, [])

  useEffect(() => stopGhost, [stopGhost])

  return { ghostRef, moveGhost, stopGhost }
}
