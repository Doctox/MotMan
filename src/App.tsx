import { lazy, Suspense, useState } from 'react'
import { LoaderCircle } from 'lucide-react'
import type { GridDifficulty } from './generator'
import { createSoloMatch, type MatchPace } from './matches'

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

  const openMatch = (nextMatchId: string) => {
    history.replaceState(null, '', `#partie=${encodeURIComponent(nextMatchId)}`)
    setMatchId(nextMatchId)
  }
  const exitMatch = () => {
    history.replaceState(null, '', '#jouer')
    setMatchId(null)
  }
  const returnHome = () => {
    history.replaceState(null, '', '#accueil')
    setMatchId(null)
  }
  const startSolo = async (difficulty: GridDifficulty, pace: MatchPace) => {
    const match = await createSoloMatch(difficulty, pace)
    openMatch(match.id)
  }

  if (matchId) return <Suspense fallback={<AppLoading label="Préparation du duel…" />}>
    <MultiplayerGameScreen matchId={matchId} onExit={exitMatch} onHome={returnHome} />
  </Suspense>
  return <Suspense fallback={<AppLoading />}>
    <MenuApp onStartSolo={startSolo} onStartMatch={openMatch} />
  </Suspense>
}
