export const PLAYER_NAME_MIN_LENGTH = 3
export const PLAYER_NAME_MAX_LENGTH = 16

export type PlayerNameValidation = {
  valid: boolean
  normalized: string
  error?: string
}

const RESERVED_MARKERS = ['admin', 'administrateur', 'moderateur', 'moderation', 'support', 'systeme', 'motman', 'officiel']
const UNAMBIGUOUS_BLOCKED_MARKERS = [
  'nazi', 'hitler', 'penis', 'porno', 'pornographie', 'encule', 'salope', 'putain',
  'negro', 'negre', 'bamboula', 'bougnoule', 'youpin', 'chintok',
]
const SHORT_BLOCKED_WORDS = ['bite', 'vagin', 'chatte', 'couille', 'sexe', 'pute']

export function normalizePlayerName(value: string): string {
  return value.normalize('NFKC').trim().replace(/\s+/g, ' ')
}

function canonicalName(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('fr')
    .replace(/[4@]/g, 'a')
    .replace(/3/g, 'e')
    .replace(/[1!]/g, 'i')
    .replace(/0/g, 'o')
    .replace(/[5$]/g, 's')
    .replace(/7/g, 't')
}

export function validatePlayerName(value: string): PlayerNameValidation {
  const normalized = normalizePlayerName(value)
  const length = Array.from(normalized).length
  if (length < PLAYER_NAME_MIN_LENGTH) return { valid: false, normalized, error: `Au moins ${PLAYER_NAME_MIN_LENGTH} caractères.` }
  if (length > PLAYER_NAME_MAX_LENGTH) return { valid: false, normalized, error: `${PLAYER_NAME_MAX_LENGTH} caractères maximum.` }
  if (!/^[\p{L}\p{N}](?:[\p{L}\p{N} _'’\-]*[\p{L}\p{N}])?$/u.test(normalized)) {
    return { valid: false, normalized, error: 'Lettres, chiffres, espace, tiret ou apostrophe uniquement.' }
  }
  if (/([ _'’\-])\1/u.test(normalized)) return { valid: false, normalized, error: 'Évite les séparateurs répétés.' }
  if (/\d{6,}/.test(normalized) || /(?:https?|www|discord|telegram|snapchat|instagram|tiktok|gmail|hotmail|outlook)/i.test(normalized)) {
    return { valid: false, normalized, error: 'Les coordonnées et liens ne sont pas autorisés.' }
  }

  const canonical = canonicalName(normalized)
  const compact = canonical.replace(/[^a-z0-9]/g, '')
  const literalCompact = normalized.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('fr').replace(/[^a-z0-9]/g, '')
  const tokens = canonical.split(/[^a-z0-9]+/).filter(Boolean)
  if (RESERVED_MARKERS.some(marker => compact.includes(marker))) {
    return { valid: false, normalized, error: 'Ce pseudo peut être confondu avec un compte officiel.' }
  }
  if (UNAMBIGUOUS_BLOCKED_MARKERS.some(marker => compact.includes(marker)) ||
    SHORT_BLOCKED_WORDS.some(word => tokens.includes(word) || compact === word || new RegExp(`^${word}\\d{1,3}$`).test(compact) || new RegExp(`^${word}\\d{1,3}$`).test(literalCompact))) {
    return { valid: false, normalized, error: 'Choisis un pseudo respectueux.' }
  }
  return { valid: true, normalized }
}
