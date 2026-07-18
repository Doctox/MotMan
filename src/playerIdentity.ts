import { validatePlayerName } from './playerNamePolicy'

export type GuestIdentity = {
  version: 1 | 2
  playerId: string
  displayName: string
  accountType: 'guest' | 'account'
  friendCode?: string
  createdAt: string
}

const STORAGE_KEY = 'motman-player-v1'

function randomGuestNumber(): number {
  const values = new Uint16Array(1)
  crypto.getRandomValues(values)
  return 1000 + values[0] % 9000
}

function newPlayerId(): string {
  if (typeof crypto.randomUUID === 'function') return `guest_${crypto.randomUUID()}`
  const values = new Uint32Array(4)
  crypto.getRandomValues(values)
  return `guest_${[...values].map(value => value.toString(16).padStart(8, '0')).join('')}`
}

export function createGuestIdentity(): GuestIdentity {
  return {
    version: 1,
    playerId: newPlayerId(),
    displayName: `Invité ${randomGuestNumber()}`,
    accountType: 'guest',
    createdAt: new Date().toISOString(),
  }
}

function isGuestIdentity(value: unknown): value is GuestIdentity {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<GuestIdentity>
  return (candidate.version === 1 || candidate.version === 2) && (candidate.accountType === 'guest' || candidate.accountType === 'account') &&
    typeof candidate.playerId === 'string' && (candidate.playerId.startsWith('guest_') || /^[0-9a-f-]{36}$/i.test(candidate.playerId)) &&
    typeof candidate.displayName === 'string' && candidate.displayName.trim().length > 0 &&
    typeof candidate.createdAt === 'string'
}

export function loadPlayerIdentity(): GuestIdentity {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed: unknown = JSON.parse(stored)
      if (isGuestIdentity(parsed)) {
        const validation = validatePlayerName(parsed.displayName)
        if (validation.valid) {
          const identity = validation.normalized === parsed.displayName ? parsed : { ...parsed, displayName: validation.normalized }
          if (identity !== parsed) savePlayerIdentity(identity)
          return identity
        }
        const repaired = { ...parsed, displayName: `Invité ${randomGuestNumber()}` }
        savePlayerIdentity(repaired)
        return repaired
      }
    }
  } catch {
    // A malformed local profile is replaced by a fresh guest identity.
  }
  const identity = createGuestIdentity()
  savePlayerIdentity(identity)
  return identity
}

export function savePlayerIdentity(identity: GuestIdentity): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(identity))
  window.dispatchEvent(new CustomEvent<GuestIdentity>('motman:identity', { detail: identity }))
}

export function updateGuestName(identity: GuestIdentity, displayName: string): GuestIdentity {
  const validation = validatePlayerName(displayName)
  if (!validation.valid) return identity
  const updated = { ...identity, displayName: validation.normalized }
  savePlayerIdentity(updated)
  return updated
}

export function playerInitials(displayName: string): string {
  const words = displayName.trim().split(/\s+/).filter(Boolean)
  if (!words.length) return 'IN'
  if (words.length === 1 || /^\d+$/.test(words[1])) return words[0].slice(0, 2).toUpperCase()
  return `${words[0][0]}${words[1][0]}`.toUpperCase()
}

export function shortPlayerId(playerId: string): string {
  return playerId.replace(/^guest_/, '').split('-')[0].slice(0, 8).toUpperCase()
}
