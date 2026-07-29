import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { LoaderCircle } from 'lucide-react'
import { startAdaptivePolling } from './adaptivePolling'
import type { GridDifficulty } from './generator'
import { subscribeToMenuUpdates, type MenuRealtimeStatus, type MenuWakeupScope } from './menuRealtime'
import { createSoloMatch, type MatchPace } from './matches'
import { loadPlayerIdentity, type GuestIdentity } from './playerIdentity'
import { RankedReadyOverlay } from './RankedReadyOverlay'
import {
  cancelRankedSearch,
  EMPTY_RANKED_MATCHMAKING,
  loadRankedMatchmaking,
  respondToRankedReady,
  startRankedSearch,
  type RankedMatchmakingState,
} from './rankedMatchmaking'

const MenuApp = lazy(() => import('./Menu').then(module => ({ default: module.MenuApp })))
const MultiplayerGameScreen = lazy(() => import('./MultiplayerGame').then(module => ({ default: module.MultiplayerGameScreen })))

function AppLoading({ label = 'Préparation de MotMan…' }: { label?: string }) {
  return <main className="app-loading" role="status"><LoaderCircle /><span>{label}</span></main>
}

export function App() {
  const [matchId, setMatchId] = useState<string | null>(() => {
    const match = location.hash.match(/^#partie=([^&]+)$/)
    return match ? decodeURIComponent(match[1]) : null
  })
  const [ranked, setRanked] = useState<RankedMatchmakingState>(EMPTY_RANKED_MATCHMAKING)
  const [rankedBusy, setRankedBusy] = useState(false)
  const [rankedError, setRankedError] = useState<string | null>(null)
  const [playerId, setPlayerId] = useState(() => loadPlayerIdentity().playerId)
  const rankedRef = useRef(ranked)
  const rankedPollingRef = useRef<ReturnType<typeof startAdaptivePolling> | null>(null)
  rankedRef.current = ranked

  const openMatch = useCallback((nextMatchId: string) => {
    history.replaceState(null, '', `#partie=${encodeURIComponent(nextMatchId)}`)
    setMatchId(nextMatchId)
  }, [])
  const exitMatch = useCallback(() => {
    history.replaceState(null, '', '#jouer')
    setMatchId(null)
  }, [])
  const returnHome = useCallback(() => {
    history.replaceState(null, '', '#accueil')
    setMatchId(null)
  }, [])
  const startSolo = useCallback(async (difficulty: GridDifficulty, pace: MatchPace) => {
    const match = await createSoloMatch(difficulty, pace)
    openMatch(match.id)
  }, [openMatch])

  useEffect(() => {
    const syncIdentity = (event: Event) => {
      const next = (event as CustomEvent<GuestIdentity>).detail
      if (next?.playerId) setPlayerId(next.playerId)
    }
    window.addEventListener('motman:identity', syncIdentity)
    return () => window.removeEventListener('motman:identity', syncIdentity)
  }, [])

  useEffect(() => {
    let active = true
    const polling = startAdaptivePolling({
      task: async () => {
        try {
          const next = await loadRankedMatchmaking()
          if (!active) return
          setRanked(next)
          setRankedError(null)
          if (next.status === 'started' && next.matchId && next.matchId !== matchId) openMatch(next.matchId)
        } catch {
          // A guest without a remote session can still browse the local menu.
        }
      },
      delay: visibility => {
        const status = rankedRef.current.status
        if (status === 'ready' || status === 'accepted') return visibility === 'hidden' ? 3_000 : 2_000
        if (status === 'searching') return visibility === 'hidden' ? 15_000 : 8_000
        return visibility === 'hidden' ? 60_000 : 20_000
      },
    })
    rankedPollingRef.current = polling
    return () => {
      active = false
      if (rankedPollingRef.current === polling) rankedPollingRef.current = null
      polling.stop()
    }
  }, [matchId, openMatch])

  useEffect(() => subscribeToMenuUpdates(playerId, scope => {
    window.dispatchEvent(new CustomEvent('motman:menu-wakeup', {
      detail: { scope, status: 'connected' satisfies MenuRealtimeStatus },
    }))
    rankedPollingRef.current?.wake()
  }, status => {
    window.dispatchEvent(new CustomEvent('motman:menu-wakeup', {
      detail: { scope: 'all' satisfies MenuWakeupScope, status },
    }))
    if (status === 'connected') rankedPollingRef.current?.wake()
  }), [playerId])

  const beginRankedSearch = useCallback(async () => {
    if (rankedBusy) return
    setRankedBusy(true)
    setRankedError(null)
    try { setRanked(await startRankedSearch()) }
    catch (reason) { setRankedError(reason instanceof Error ? reason.message : 'Recherche classée impossible.') }
    finally { setRankedBusy(false) }
  }, [rankedBusy])

  const stopRankedSearch = useCallback(async () => {
    if (rankedBusy) return
    setRankedBusy(true)
    setRankedError(null)
    try { setRanked(await cancelRankedSearch()) }
    catch (reason) { setRankedError(reason instanceof Error ? reason.message : 'Annulation impossible.') }
    finally { setRankedBusy(false) }
  }, [rankedBusy])

  const answerRankedReady = useCallback(async (decision: 'accept' | 'decline') => {
    const ready = rankedRef.current.ready
    if (!ready || rankedBusy) return
    setRankedBusy(true)
    setRankedError(null)
    try {
      const next = await respondToRankedReady(ready.id, decision)
      setRanked(next)
      if (next.status === 'started' && next.matchId) openMatch(next.matchId)
    } catch (reason) {
      setRankedError(reason instanceof Error ? reason.message : 'Réponse classée impossible.')
    } finally {
      setRankedBusy(false)
    }
  }, [openMatch, rankedBusy])

  return <>
    {matchId ? <Suspense fallback={<AppLoading label="Préparation du duel…" />}>
      <MultiplayerGameScreen matchId={matchId} onExit={exitMatch} onHome={returnHome} />
    </Suspense> : <Suspense fallback={<AppLoading />}>
      <MenuApp
        onStartSolo={startSolo}
        onStartMatch={openMatch}
        ranked={ranked}
        rankedBusy={rankedBusy}
        rankedError={rankedError}
        startRanked={beginRankedSearch}
        cancelRanked={stopRankedSearch}
      />
    </Suspense>}
    <RankedReadyOverlay
      state={ranked}
      busy={rankedBusy}
      error={rankedError}
      accept={() => void answerRankedReady('accept')}
      decline={() => void answerRankedReady('decline')}
    />
  </>
}
