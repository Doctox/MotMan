import type { GridDifficulty } from '../generator'
import type { MatchPace } from '../matches'
import type { RankedMatchmakingState } from '../rankedMatchmaking'

export type MenuPage = 'home' | 'play' | 'ranking' | 'profile' | 'shop'
export type Theme = 'light' | 'dark' | 'system'

export type MenuAppProps = {
  onStartSolo: (difficulty: GridDifficulty, pace: MatchPace) => Promise<void>
  onStartMatch: (matchId: string) => void
  ranked: RankedMatchmakingState
  rankedBusy: boolean
  rankedError: string | null
  startRanked: () => Promise<void>
  cancelRanked: () => Promise<void>
}
