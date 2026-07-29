import { assetUrl } from './assetUrl'

export const RANKED_PLACEMENT_MATCHES = 5
export const RANKED_READY_SECONDS = 30

export type RankedDivisionId =
  | 'unranked'
  | 'bronze'
  | 'silver'
  | 'gold'
  | 'platinum'
  | 'diamond'
  | 'master'
  | 'legend'

export type RankedDivision = {
  id: RankedDivisionId
  label: string
  minimum: number
  image: string
}

export const RANKED_DIVISIONS: readonly RankedDivision[] = [
  { id: 'bronze', label: 'Bronze', minimum: 0, image: '/assets/ranks/rank-bronze.png' },
  { id: 'silver', label: 'Argent', minimum: 1100, image: '/assets/ranks/rank-silver.png' },
  { id: 'gold', label: 'Or', minimum: 1300, image: '/assets/ranks/rank-gold.png' },
  { id: 'platinum', label: 'Platine', minimum: 1500, image: '/assets/ranks/rank-platinum.png' },
  { id: 'diamond', label: 'Diamant', minimum: 1700, image: '/assets/ranks/rank-diamond.png' },
  { id: 'master', label: 'Maître', minimum: 1900, image: '/assets/ranks/rank-master.png' },
  { id: 'legend', label: 'Légende', minimum: 2100, image: '/assets/ranks/rank-legend.png' },
] as const

export const UNRANKED_DIVISION: RankedDivision = {
  id: 'unranked',
  label: 'Non classé',
  minimum: 0,
  image: '/assets/ranks/rank-unranked.png',
}

export function rankedDivision(points: number, matches: number): RankedDivision {
  if (matches < RANKED_PLACEMENT_MATCHES) return UNRANKED_DIVISION
  const safePoints = Math.max(0, Math.floor(points))
  return [...RANKED_DIVISIONS].reverse().find(division => safePoints >= division.minimum) ?? RANKED_DIVISIONS[0]
}

export function nextRankedDivision(points: number, matches: number): RankedDivision | null {
  if (matches < RANKED_PLACEMENT_MATCHES) return RANKED_DIVISIONS[0]
  return RANKED_DIVISIONS.find(division => division.minimum > points) ?? null
}

export function rankedPlacementLabel(matches: number): string {
  const completed = Math.min(RANKED_PLACEMENT_MATCHES, Math.max(0, Math.floor(matches)))
  return completed < RANKED_PLACEMENT_MATCHES
    ? `${completed}/${RANKED_PLACEMENT_MATCHES} placements`
    : 'Classement établi'
}

export function rankImage(division: RankedDivision): string {
  return assetUrl(division.image)
}
