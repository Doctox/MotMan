export type PollVisibility = 'visible' | 'hidden'

type AdaptivePollingOptions = {
  task: () => void | Promise<void>
  delay: (visibility: PollVisibility) => number
  immediate?: boolean
}

/**
 * Runs one request at a time and adapts its cadence when the app is hidden.
 * Becoming visible or coming back online triggers an immediate refresh.
 */
export function startAdaptivePolling({ task, delay, immediate = true }: AdaptivePollingOptions): () => void {
  let stopped = false
  let running = false
  let runAgain = false
  let timer: number | null = null

  const visibility = (): PollVisibility => document.visibilityState === 'hidden' ? 'hidden' : 'visible'

  const clearTimer = () => {
    if (timer !== null) window.clearTimeout(timer)
    timer = null
  }

  const schedule = () => {
    clearTimer()
    if (stopped) return
    const wait = delay(visibility())
    if (!Number.isFinite(wait) || wait < 0) return
    timer = window.setTimeout(() => void run(), wait)
  }

  const run = async () => {
    if (stopped) return
    if (running) {
      runAgain = true
      return
    }
    clearTimer()
    running = true
    try {
      await task()
    } finally {
      running = false
      if (stopped) return
      if (runAgain) {
        runAgain = false
        void run()
      } else schedule()
    }
  }

  const wake = () => {
    if (document.visibilityState === 'hidden') {
      schedule()
      return
    }
    clearTimer()
    void run()
  }

  document.addEventListener('visibilitychange', wake)
  window.addEventListener('online', wake)
  if (immediate) void run()
  else schedule()

  return () => {
    stopped = true
    clearTimer()
    document.removeEventListener('visibilitychange', wake)
    window.removeEventListener('online', wake)
  }
}
