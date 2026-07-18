export type ProgressionMode = 'solo' | 'multiplayer'
export type ProgressionOutcome = 'win' | 'draw' | 'loss' | 'abandon' | 'opponent-abandoned'
export type RewardRarity = 'commun' | 'singulier' | 'rare' | 'precieux' | 'exceptionnel' | 'legendaire'

export type FeatherRewardBreakdown = {
  base: number
  noHint: number
  noReroll: number
  fullRack: number
  total: number
}

export const RARITY_ORDER: readonly RewardRarity[] = [
  'commun', 'singulier', 'rare', 'precieux', 'exceptionnel', 'legendaire',
]

export const LEVEL_TITLE_REWARDS = [
  { id: 'premiers-mots', name: 'Premiers mots', description: 'Les premières lettres de votre aventure.', level: 1 },
  { id: 'plume-curieuse', name: 'Plume curieuse', description: 'Toujours prêt à chercher le mot juste.', level: 5 },
  { id: 'amoureux-des-mots', name: 'Amoureux des mots', description: 'Les mots sont devenus un terrain de jeu.', level: 10 },
  { id: 'esprit-lettre', name: 'Esprit lettré', description: 'Une pensée fine et un vocabulaire sûr.', level: 15 },
  { id: 'plume-affutee', name: 'Plume affûtée', description: 'Chaque définition trouve sa réponse.', level: 20 },
  { id: 'tisseur-de-mots', name: 'Tisseur de mots', description: 'Les croisements n’ont presque plus de secrets.', level: 25 },
  { id: 'virtuose-des-lettres', name: 'Virtuose des lettres', description: 'Les lettres s’accordent avec élégance.', level: 30 },
  { id: 'maitre-des-mots', name: 'Maître des mots', description: 'Une maîtrise patiente et redoutable.', level: 35 },
  { id: 'sage-du-lexique', name: 'Sage du lexique', description: 'Un grand voyage au cœur du français.', level: 40 },
  { id: 'gardien-des-mots', name: 'Gardien des mots', description: 'Les mots peuvent compter sur vous.', level: 45 },
  { id: 'legende-de-motman', name: 'Légende de MotMan', description: 'Le plus haut titre de la progression.', level: 50 },
] as const

export function calculateFeatherReward({
  mode,
  outcome,
  totalProductiveTurns = 0,
  hintUsed,
  rerollUsed,
  rackCompletions = 0,
}: {
  mode: ProgressionMode
  outcome: ProgressionOutcome
  totalProductiveTurns?: number
  hintUsed: boolean
  rerollUsed: boolean
  rackCompletions?: number
}): FeatherRewardBreakdown {
  const base = outcome === 'abandon' ? 0
    : outcome === 'opponent-abandoned' ? Math.min(160, Math.max(0, Math.floor(totalProductiveTurns)) * 10)
      : mode === 'solo'
        ? outcome === 'win' ? 80 : outcome === 'draw' ? 40 : 20
        : outcome === 'win' ? 160 : outcome === 'draw' ? 80 : 50

  if (base === 0) return { base: 0, noHint: 0, noReroll: 0, fullRack: 0, total: 0 }

  const noHint = hintUsed ? 0 : 5
  const noReroll = rerollUsed ? 0 : 5
  const fullRack = Math.max(0, Math.floor(rackCompletions)) * 5
  return { base, noHint, noReroll, fullRack, total: base + noHint + noReroll + fullRack }
}

export function basketRarityWeights(pity: number): Record<RewardRarity, number> {
  const step = Math.max(0, Math.min(20, Math.floor(pity)))
  return {
    commun: Math.max(12, 50 - step * 2.4),
    singulier: Math.max(14, 28 - step * 0.7),
    rare: 14 + step * 1.35,
    precieux: 5 + step * 0.72,
    exceptionnel: 2.5 + step * 0.31,
    legendaire: 0.5 + step * 0.12,
  }
}

export function basketRarityProbabilities(
  pity: number,
  availableRarities: Iterable<RewardRarity> = RARITY_ORDER,
): Record<RewardRarity, number> {
  const available = new Set(availableRarities)
  const weights = basketRarityWeights(pity)
  const total = RARITY_ORDER.reduce((sum, rarity) => sum + (available.has(rarity) ? weights[rarity] : 0), 0)
  return RARITY_ORDER.reduce<Record<RewardRarity, number>>((result, rarity) => {
    result[rarity] = total > 0 && available.has(rarity) ? weights[rarity] / total * 100 : 0
    return result
  }, { commun: 0, singulier: 0, rare: 0, precieux: 0, exceptionnel: 0, legendaire: 0 })
}
