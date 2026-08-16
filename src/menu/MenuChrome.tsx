import type { ReactNode } from 'react'
import { BarChart3, Gamepad2, Home, Settings, User } from 'lucide-react'
import { assetUrl } from '../assetUrl'
import { CosmeticPortrait } from '../CosmeticPortrait'
import { playerInitials } from '../playerIdentity'
import type { PlayerProgress } from '../playerProgress'
import { nextRankedDivision, rankImage, rankedDivision, rankedPlacementLabel, RANKED_PLACEMENT_MATCHES } from '../ranked'
import type { SocialUser } from '../social'
import type { MenuPage } from './types'
import { DailyStreakChip } from './DailyChallenge'

function Brand() {
  return <div className="mm-brand"><img src={assetUrl('/assets/motman-logo-v2.webp')} alt="MotMan" /></div>
}

export function Avatar({ label = 'A', small = false }: { label?: string; small?: boolean }) {
  return <span className={`mm-avatar ${small ? 'small' : ''}`} aria-hidden="true">{label}</span>
}

export function SocialPortrait({ user, small = false }: { user: Pick<SocialUser, 'displayName' | 'avatarId' | 'frameId' | 'animationId'>; small?: boolean }) {
  return user.avatarId ? <CosmeticPortrait avatarId={user.avatarId} frameId={user.frameId ?? 'cadre-ivoire'} animationId={user.animationId} alt="" small={small} />
    : <Avatar label={playerInitials(user.displayName)} small={small} />
}

export function presenceLabel(activity: 'offline' | 'online' | 'playing'): string {
  return activity === 'playing' ? 'En jeu' : activity === 'online' ? 'En ligne' : 'Hors ligne'
}

export function AppHeader({ onSettings }: { onMenu?: () => void; onSettings: () => void }) {
  return <header className="mm-header">
    <DailyStreakChip />
    <Brand />
    <button className="mm-icon-button" type="button" aria-label="Paramètres" onClick={onSettings}><Settings /></button>
  </header>
}

export function BottomNav({ page, setPage }: { page: MenuPage; setPage: (page: MenuPage) => void }) {
  const activePage = page === 'shop' ? 'profile' : page
  const items: Array<[MenuPage, string, ReactNode]> = [
    ['home', 'Accueil', <Home />], ['play', 'Jouer', <Gamepad2 />],
    ['ranking', 'Classement', <BarChart3 />], ['profile', 'Profil', <User />],
  ]
  return <nav className="mm-bottom-nav" aria-label="Navigation principale">
    {items.map(([id, label, icon]) => <button key={id} type="button" className={activePage === id ? 'active' : ''} aria-current={activePage === id ? 'page' : undefined} onClick={() => setPage(id)}>{icon}<span>{label}</span></button>)}
  </nav>
}

export function RankProgress({ progress, compact = false }: { progress: PlayerProgress; compact?: boolean }) {
  const division = rankedDivision(progress.rankedPoints, progress.rankedMatches)
  const next = nextRankedDivision(progress.rankedPoints, progress.rankedMatches)
  const placementProgress = Math.min(100, progress.rankedMatches / RANKED_PLACEMENT_MATCHES * 100)
  const rankProgress = next && progress.rankedMatches >= RANKED_PLACEMENT_MATCHES
    ? Math.min(100, Math.max(0, (progress.rankedPoints - division.minimum) / (next.minimum - division.minimum) * 100))
    : next ? placementProgress : 100
  return <section className={`mm-rank-progress ${progress.rankedMatches < RANKED_PLACEMENT_MATCHES ? 'mm-rank-progress-empty' : ''} ${compact ? 'compact' : ''}`} aria-label="Progression classée">
    <img className="mm-rank-image" src={rankImage(division)} alt={`Rang ${division.label}`} />
    <div className="mm-rank-copy"><strong>{division.label}</strong><span>{progress.rankedMatches < RANKED_PLACEMENT_MATCHES ? rankedPlacementLabel(progress.rankedMatches) : `${progress.rankedPoints} pt`}</span></div>
    <div className="mm-progress"><small>{next ? progress.rankedMatches < RANKED_PLACEMENT_MATCHES ? 'Terminez vos placements' : `${next.minimum - progress.rankedPoints} pt avant ${next.label}` : 'Rang maximum'}</small><i><b style={{ width: `${rankProgress}%` }} /></i></div>
  </section>
}

