export function sameNumberRecord(left: Record<string, number>, right: Record<string, number>): boolean {
  const leftKeys = Object.keys(left)
  const rightKeys = Object.keys(right)
  return leftKeys.length === rightKeys.length && leftKeys.every(key => left[key] === right[key])
}

export function compactClue(text: string): string {
  const firstIdea = text.split(/[;.(]/, 1)[0].split(/, dont |, qui |, où /i, 1)[0].trim()
  if (firstIdea.length <= 19) return firstIdea
  const words = firstIdea.split(/\s+/)
  let compact = ''
  for (const word of words) {
    if (`${compact} ${word}`.trim().length > 17) break
    compact = `${compact} ${word}`.trim()
  }
  return `${compact || firstIdea.slice(0, 17)}…`
}
