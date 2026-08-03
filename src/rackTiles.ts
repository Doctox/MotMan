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

export function reconcileRackPlacements(
  placements: Readonly<Record<number, RackTile>>,
  rackLetters: readonly string[],
  turnNumber: number,
): Record<number, RackTile> {
  const available = createMatchRackTiles(rackLetters, turnNumber)
  const reconciled: Record<number, RackTile> = {}
  for (const [cellIndex, placement] of Object.entries(placements)) {
    const nextIndex = available.findIndex(tile => tile.letter === placement.letter)
    if (nextIndex < 0) continue
    reconciled[Number(cellIndex)] = available.splice(nextIndex, 1)[0]
  }
  return reconciled
}
