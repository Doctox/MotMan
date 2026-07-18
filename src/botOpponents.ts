export type BotSkill = 'beginner' | 'regular' | 'expert'

export type BotPersona = {
  displayName: string
  level: number
  skill: BotSkill
  avatarId: string
  frameId: string
}

export type BotTuning = {
  accuracy: number
  minLetters: number
  maxLetters: number
}

export const BOT_NAMES = ['Léa', 'Hugo', 'Inès', 'Nathan', 'Zoé', 'Lucas', 'Manon', 'Adam', 'Jade', 'Théo', 'Clara', 'Noé', 'Lina', 'Gabriel'] as const
export const BOT_AVATAR_IDS = ['amina', 'malik', 'mei', 'kenji', 'ines', 'nael', 'camille', 'alex'] as const
export const BOT_FRAME_IDS = ['cadre-ivoire', 'cadre-sauge', 'cadre-terracotta', 'cadre-encre', 'cadre-laiton'] as const

function hash(text: string): number {
  let value = 2166136261
  for (const character of text) value = Math.imul(value ^ character.charCodeAt(0), 16777619)
  return value >>> 0
}

export function createBotPersona(seed: string, preferredSkill?: BotSkill): BotPersona {
  const skillRoll = hash(`${seed}:skill`) % 100
  const skill: BotSkill = preferredSkill ?? (skillRoll < 35 ? 'beginner' : skillRoll < 85 ? 'regular' : 'expert')
  const range = skill === 'beginner' ? [6, 17] : skill === 'regular' ? [18, 34] : [35, 48]
  const level = range[0] + hash(`${seed}:level`) % (range[1] - range[0] + 1)
  const displayName = BOT_NAMES[hash(`${seed}:name`) % BOT_NAMES.length]
  const avatarId = BOT_AVATAR_IDS[hash(`${seed}:avatar`) % BOT_AVATAR_IDS.length]
  const frameId = BOT_FRAME_IDS[hash(`${seed}:frame`) % BOT_FRAME_IDS.length]
  return { displayName, level, skill, avatarId, frameId }
}

export function botTuning(persona: BotPersona): BotTuning {
  if (persona.skill === 'beginner') return { accuracy: 56, minLetters: 1, maxLetters: 1 }
  if (persona.skill === 'regular') return { accuracy: 74, minLetters: 1, maxLetters: 2 }
  return { accuracy: 90, minLetters: 2, maxLetters: 3 }
}
