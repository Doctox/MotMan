import { useEffect, useState } from 'react'
import type { MatchState } from '../matches'

const ASYNC_TURN_DURATION_SECONDS = 24 * 60 * 60

function turnClockLabel(seconds: number, async: boolean): string {
  if (!async) return String(Math.min(45, seconds))
  const visibleSeconds = Math.min(ASYNC_TURN_DURATION_SECONDS, seconds)
  if (visibleSeconds >= 3_600) return `${Math.ceil(visibleSeconds / 3_600)}h`
  if (visibleSeconds >= 60) return `${Math.ceil(visibleSeconds / 60)}m`
  return `${visibleSeconds}s`
}

type TurnPhase = { started: boolean; expired: boolean; urgent: boolean }

function phaseAt(match: MatchState | null, instant = Date.now()): TurnPhase {
  if (!match || match.status !== 'active') return { started: false, expired: false, urgent: false }
  const startsAt = new Date(match.turnStartedAt).getTime()
  const endsAt = new Date(match.turnEndsAt).getTime()
  const started = instant >= startsAt
  const expired = instant >= endsAt
  return { started, expired, urgent: match.pace === 'realtime' && started && !expired && endsAt - instant <= 10_000 }
}

export function useTurnPhase(match: MatchState | null): TurnPhase {
  const [phase, setPhase] = useState<TurnPhase>(() => phaseAt(match))
  useEffect(() => {
    const update = () => {
      const next = phaseAt(match)
      setPhase(current => current.started === next.started && current.expired === next.expired && current.urgent === next.urgent ? current : next)
    }
    update()
    if (!match || match.status !== 'active') return
    const now = Date.now()
    const startsAt = new Date(match.turnStartedAt).getTime()
    const endsAt = new Date(match.turnEndsAt).getTime()
    const boundaries = [startsAt, match.pace === 'realtime' ? endsAt - 10_000 : 0, endsAt]
      .filter(boundary => boundary > now)
      .map(boundary => window.setTimeout(update, boundary - now + 8))
    return () => boundaries.forEach(timer => window.clearTimeout(timer))
  }, [match?.id, match?.pace, match?.status, match?.turnEndsAt, match?.turnNumber, match?.turnStartedAt])
  return phase
}

export function TurnTimer({ match, resolving, started }: { match: MatchState; resolving: boolean; started: boolean }) {
  const labelAt = () => {
    if (match.status !== 'active' || resolving || !started) return '—'
    const seconds = Math.max(0, Math.ceil((new Date(match.turnEndsAt).getTime() - Date.now()) / 1_000))
    return turnClockLabel(seconds, match.pace === 'async')
  }
  const [label, setLabel] = useState(labelAt)
  useEffect(() => {
    const update = () => setLabel(current => {
      const next = labelAt()
      return current === next ? current : next
    })
    update()
    if (match.status !== 'active' || resolving || !started) return
    const timer = window.setInterval(update, 250)
    return () => window.clearInterval(timer)
  }, [match.pace, match.status, match.turnEndsAt, match.turnNumber, resolving, started])
  return <span className="turn-timer">{label}</span>
}
