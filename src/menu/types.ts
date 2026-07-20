import type { GridDifficulty } from '../generator'
import type { MatchPace } from '../matches'

export type MenuPage = 'home' | 'play' | 'ranking' | 'profile' | 'shop'
export type Theme = 'light' | 'dark' | 'system'

export type MenuAppProps = {
  onStartSolo: (difficulty: GridDifficulty, pace: MatchPace) => Promise<void>
  onStartMatch: (matchId: string) => void
}
