import { LEVEL_TITLE_REWARDS, type FeatherRewardBreakdown } from './progressionRewards'

export const MAX_PLAYER_LEVEL = 50

export type ExperienceMode = 'solo' | 'multiplayer'
export type ExperienceOutcome = 'win' | 'draw' | 'loss' | 'abandon' | 'opponent-abandoned'

export type ExperienceBreakdown = {
  productiveTurns: number
  productiveXp: number
  completionXp: number
  resultXp: number
  total: number
}

export type ExperienceAward = {
  id: string
  mode: ExperienceMode
  outcome: ExperienceOutcome
  breakdown: ExperienceBreakdown
  levelBefore: number
  levelAfter: number
  xpAfter: number
  xpGoalAfter: number
  plumesEarned?: number
  featherBreakdown?: Partial<FeatherRewardBreakdown>
  /**
   * Bonus du défi du jour RÉELLEMENT crédité pour ce match (0 sinon). Il ne
   * vient pas de `experience_awards` mais de `economy_transactions`
   * (kind='daily-completion'), remonté par account-api. Jamais calculé côté
   * client : afficher un montant non versé serait mentir au joueur.
   */
  dailyBonusPlumes?: number
  unlockedTitles?: PlayerTitle[]
  createdAt: string
}

export type PlayerTitle = {
  id: string
  name: string
  description: string
  unlockType: 'level' | 'ranked' | 'special'
  requiredValue: number
  unlocked: boolean
  unlockedAt: string | null
}

export type PlayerProgress = {
  version: 4
  playerId: string
  level: number
  xp: number
  lifetimeXp: number
  rankedPoints: number
  rankedMatches: number
  rankedWins: number
  rankedLosses: number
  rankedDraws: number
  rankedPeakPoints: number
  wins: number
  losses: number
  activeMatchIds: string[]
  invitationIds: string[]
  equippedTitleId: string | null
  titles: PlayerTitle[]
  experienceAwards: ExperienceAward[]
}

const STORAGE_KEY = 'motman-progress-v1'

export function experienceGoalForLevel(level: number): number {
  if (level >= MAX_PLAYER_LEVEL) return 0
  return 100 + Math.max(0, level - 1) * 15
}

function lifetimeXpAtLevel(level: number): number {
  let total = 0
  for (let current = 1; current < Math.min(level, MAX_PLAYER_LEVEL); current += 1) total += experienceGoalForLevel(current)
  return total
}

function createPlayerProgress(playerId: string): PlayerProgress {
  return {
    version: 4,
    playerId,
    level: 1,
    xp: 0,
    lifetimeXp: 0,
    rankedPoints: 0,
    rankedMatches: 0,
    rankedWins: 0,
    rankedLosses: 0,
    rankedDraws: 0,
    rankedPeakPoints: 0,
    wins: 0,
    losses: 0,
    activeMatchIds: [],
    invitationIds: [],
    equippedTitleId: 'premiers-mots',
    titles: localTitlesForLevel(1),
    experienceAwards: [],
  }
}

function localTitlesForLevel(level: number): PlayerTitle[] {
  return LEVEL_TITLE_REWARDS.map(title => ({
    id: title.id,
    name: title.name,
    description: title.description,
    unlockType: 'level',
    requiredValue: title.level,
    unlocked: level >= title.level,
    unlockedAt: null,
  }))
}

function migratePlayerProgress(value: unknown, playerId: string): PlayerProgress | null {
  if (!value || typeof value !== 'object') return null
  const stored = value as Partial<PlayerProgress> & { version?: number }
  if (stored.playerId !== playerId) return null
  if (typeof stored.level !== 'number' || typeof stored.xp !== 'number') return null
  const level = Math.min(MAX_PLAYER_LEVEL, Math.max(1, Math.floor(stored.level)))
  const xpGoal = experienceGoalForLevel(level)
  const xp = level === MAX_PLAYER_LEVEL ? 0 : Math.min(Math.max(0, Math.floor(stored.xp)), Math.max(0, xpGoal - 1))
  const titles = Array.isArray(stored.titles) ? stored.titles : localTitlesForLevel(level)
  const unlockedTitleIds = new Set(titles.filter(title => title.unlocked).map(title => title.id))
  return {
    version: 4,
    playerId,
    level,
    xp,
    lifetimeXp: typeof stored.lifetimeXp === 'number' ? Math.max(0, Math.floor(stored.lifetimeXp)) : lifetimeXpAtLevel(level) + xp,
    rankedPoints: typeof stored.rankedPoints === 'number' ? stored.rankedPoints : 0,
    rankedMatches: typeof stored.rankedMatches === 'number' ? Math.max(0, Math.floor(stored.rankedMatches)) : 0,
    rankedWins: typeof stored.rankedWins === 'number' ? Math.max(0, Math.floor(stored.rankedWins)) : 0,
    rankedLosses: typeof stored.rankedLosses === 'number' ? Math.max(0, Math.floor(stored.rankedLosses)) : 0,
    rankedDraws: typeof stored.rankedDraws === 'number' ? Math.max(0, Math.floor(stored.rankedDraws)) : 0,
    rankedPeakPoints: typeof stored.rankedPeakPoints === 'number' ? Math.max(0, Math.floor(stored.rankedPeakPoints)) : 0,
    wins: typeof stored.wins === 'number' ? stored.wins : 0,
    losses: typeof stored.losses === 'number' ? stored.losses : 0,
    activeMatchIds: Array.isArray(stored.activeMatchIds) ? stored.activeMatchIds : [],
    invitationIds: Array.isArray(stored.invitationIds) ? stored.invitationIds : [],
    equippedTitleId: stored.equippedTitleId && unlockedTitleIds.has(stored.equippedTitleId) ? stored.equippedTitleId : titles.find(title => title.unlocked)?.id ?? null,
    titles,
    experienceAwards: stored.version && stored.version >= 2 && Array.isArray(stored.experienceAwards) ? stored.experienceAwards.slice(-200) : [],
  }
}

export function savePlayerProgress(progress: PlayerProgress): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(progress))
  window.dispatchEvent(new CustomEvent<PlayerProgress>('motman:progress', { detail: progress }))
}

export function loadPlayerProgress(playerId: string): PlayerProgress {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored) as { version?: number }
      const migrated = migratePlayerProgress(parsed, playerId)
      if (migrated) {
        if (parsed.version !== 4) savePlayerProgress(migrated)
        return migrated
      }
    }
  } catch {
    // Les anciennes données de démonstration ou corrompues sont remplacées.
  }

  const progress = createPlayerProgress(playerId)
  savePlayerProgress(progress)
  return progress
}

// NOTE (nettoyage 2026-08-05) : `awardExperience()` et `calculateExperience()`
// ont été retirés — chemin MORT (jamais appelé) qui exposait une fausse formule
// d'économie (`plumesEarned = ceil(XP/4)`). La progression réelle est calculée
// CÔTÉ SERVEUR (edge function match-api → calculateFeatherReward → RPC
// server_award_progress). Le champ `plumesEarned` du type `ExperienceAward` est
// CONSERVÉ : il reste alimenté par le serveur (account-api → feather_amount) et
// affiché par ExperienceReward.tsx.
