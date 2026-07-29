import { useEffect, useMemo, useState } from 'react'
import { Check, Clock3, ShieldX, Swords } from 'lucide-react'
import { rankImage, rankedDivision } from './ranked'
import type { RankedMatchmakingState } from './rankedMatchmaking'
import { useDialogFocus } from './useDialogFocus'

function secondsUntil(expiresAt: string, now: number): number {
  return Math.max(0, Math.ceil((new Date(expiresAt).getTime() - now) / 1000))
}

export function RankedReadyOverlay({
  state,
  busy,
  error,
  accept,
  decline,
}: {
  state: RankedMatchmakingState
  busy: boolean
  error: string | null
  accept: () => void
  decline: () => void
}) {
  const ready = state.ready
  const [now, setNow] = useState(Date.now())
  const dialogRef = useDialogFocus<HTMLElement>(() => undefined)

  useEffect(() => {
    if (!ready) return
    setNow(Date.now())
    const interval = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(interval)
  }, [ready?.id])

  const seconds = ready ? secondsUntil(ready.expiresAt, now) : 0
  const division = useMemo(
    () => rankedDivision(state.progress.points, state.progress.matches),
    [state.progress.matches, state.progress.points],
  )
  if (!ready) return null

  return <div className="ranked-ready-layer" role="presentation">
    <section ref={dialogRef} className="ranked-ready-dialog" role="dialog" aria-modal="true" aria-labelledby="ranked-ready-title" tabIndex={-1}>
      <div className="ranked-ready-emblems" aria-hidden="true">
        <img src={rankImage(division)} alt="" />
        <Swords />
        <span>{ready.opponent?.avatarId ? <span className="ranked-ready-opponent-avatar">{ready.opponent.displayName.slice(0, 1)}</span> : ready.opponent?.displayName.slice(0, 1) ?? '?'}</span>
      </div>
      <small>Partie classée · 45 s par tour</small>
      <h2 id="ranked-ready-title">Adversaire trouvé !</h2>
      <p><strong>{ready.opponent?.displayName ?? 'Votre adversaire'}</strong> est prêt à rejoindre l’arène.</p>
      {ready.pausedMatchId ? <p className="ranked-ready-pause-note">Votre partie normale est mise en pause. Elle reprendra intacte si le match classé ne démarre pas.</p> : null}
      <div className={`ranked-ready-countdown ${seconds <= 8 ? 'urgent' : ''}`} aria-live="polite"><Clock3 /><b>{seconds}</b><span>secondes</span></div>
      {state.status === 'accepted' ? <div className="ranked-ready-waiting"><Check />Accepté · En attente de l’autre joueur</div> : <div className="ranked-ready-actions">
        <button type="button" className="ranked-ready-decline" disabled={busy} onClick={decline}><ShieldX />Quitter</button>
        <button type="button" className="ranked-ready-accept" disabled={busy || seconds === 0} onClick={accept}><Check />Rejoindre</button>
      </div>}
      {error ? <p className="ranked-ready-error" role="alert">{error}</p> : null}
    </section>
  </div>
}

export function RankedMatchPausedOverlay({
  opponentName,
  expiresAt,
}: {
  opponentName: string
  expiresAt: string
}) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(interval)
  }, [expiresAt])
  const seconds = secondsUntil(expiresAt, now)
  return <div className="ranked-match-paused" role="status" aria-live="polite">
    <section>
      <Clock3 />
      <h2>Partie en pause</h2>
      <p>{opponentName} confirme une partie classée.</p>
      <strong>{seconds > 0 ? `Reprise ou résultat dans ${seconds} s` : 'Synchronisation en cours…'}</strong>
    </section>
  </div>
}
