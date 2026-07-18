import { grantPlumes } from './cosmetics'
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
  version: 3
  playerId: string
  level: number
  xp: number
  lifetimeXp: number
  rankedPoints: number
  rankedDivision: null
  wins: number
  losses: number
  activeMatchIds: string[]
  invitationIds: string[]
  equippedTitleId: string | null
  titles: PlayerTitle[]
  experienceAwards: ExperienceAward[]
}

export type ExperienceGrant = {
  award: ExperienceAward
  progress: PlayerProgress
  applied: boolean
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
    version: 3,
    playerId,
    level: 1,
    xp: 0,
    lifetimeXp: 0,
    rankedPoints: 0,
    rankedDivision: null,
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
    version: 3,
    playerId,
    level,
    xp,
    lifetimeXp: typeof stored.lifetimeXp === 'number' ? Math.max(0, Math.floor(stored.lifetimeXp)) : lifetimeXpAtLevel(level) + xp,
    rankedPoints: typeof stored.rankedPoints === 'number' ? stored.rankedPoints : 0,
    rankedDivision: null,
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
        if (parsed.version !== 2) savePlayerProgress(migrated)
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

export function calculateExperience(mode: ExperienceMode, outcome: ExperienceOutcome, productiveTurns: number): ExperienceBreakdown {
  const normalizedTurns = Math.max(0, Math.floor(productiveTurns))
  if (outcome === 'abandon') return { productiveTurns: normalizedTurns, productiveXp: 0, completionXp: 0, resultXp: 0, total: 0 }
  const productiveXp = normalizedTurns * (mode === 'solo' ? 1 : 2)
  const completed = outcome === 'win' || outcome === 'draw' || outcome === 'loss'
  const completionXp = completed ? mode === 'solo' ? 5 : 10 : 0
  const resultTable = mode === 'solo'
    ? { win: 10, draw: 6, loss: 3 }
    : { win: 20, draw: 12, loss: 6 }
  const resultXp = completed ? resultTable[outcome] : 0
  return { productiveTurns: normalizedTurns, productiveXp, completionXp, resultXp, total: productiveXp + completionXp + resultXp }
}

export function awardExperience({ playerId, awardId, mode, outcome, productiveTurns }: {
  playerId: string
  awardId: string
  mode: ExperienceMode
  outcome: ExperienceOutcome
  productiveTurns: number
}): ExperienceGrant {
  const progress = loadPlayerProgress(playerId)
  const existing = progress.experienceAwards.find(award => award.id === awardId)
  if (existing) return { award: existing, progress, applied: false }

  const breakdown = calculateExperience(mode, outcome, productiveTurns)
  const levelBefore = progress.level
  let level = progress.level
  let xp = progress.xp
  let remaining = breakdown.total
  while (remaining > 0 && level < MAX_PLAYER_LEVEL) {
    const goal = experienceGoalForLevel(level)
    const applied = Math.min(remaining, goal - xp)
    xp += applied
    remaining -= applied
    if (xp >= goal) { level += 1; xp = 0 }
  }
  const award: ExperienceAward = {
    id: awardId,
    mode,
    outcome,
    breakdown,
    levelBefore,
    levelAfter: level,
    xpAfter: level === MAX_PLAYER_LEVEL ? 0 : xp,
    xpGoalAfter: experienceGoalForLevel(level),
    plumesEarned: breakdown.total > 0 ? Math.max(1, Math.ceil(breakdown.total / 4)) : 0,
    createdAt: new Date().toISOString(),
  }
  const next: PlayerProgress = {
    ...progress,
    level,
    xp: level === MAX_PLAYER_LEVEL ? 0 : xp,
    lifetimeXp: progress.lifetimeXp + breakdown.total,
    wins: progress.wins + (outcome === 'win' || outcome === 'opponent-abandoned' ? 1 : 0),
    losses: progress.losses + (outcome === 'loss' || outcome === 'abandon' ? 1 : 0),
    titles: localTitlesForLevel(level),
    experienceAwards: [...progress.experienceAwards, award].slice(-200),
  }
  savePlayerProgress(next)
  grantPlumes(playerId, `xp:${awardId}`, award.plumesEarned ?? 0)
  return { award, progress: next, applied: true }
}
