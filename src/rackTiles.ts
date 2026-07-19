export type RackTile = { id: string; letter: string }

/**
 * Give every physical tile its own stable identity, including duplicate letters.
 * The position is part of the id because a rack can legitimately contain A, A.
 */
export function createMatchRackTiles(letters: readonly string[], turnNumber: number): RackTile[] {
  return letters.map((letter, index) => ({
    id: `duel-${turnNumber}-${index}-${letter}`,
    letter,
  }))
}
