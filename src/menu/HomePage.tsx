import { ChevronRight, Feather, Gamepad2, UserPlus } from 'lucide-react'
import { CosmeticPortrait } from '../CosmeticPortrait'
import type { PlayerCosmetics } from '../cosmetics'
import type { MatchLobbyState, MatchState } from '../matches'
import { playerInitials, type GuestIdentity } from '../playerIdentity'
import { experienceGoalForLevel, MAX_PLAYER_LEVEL, type PlayerProgress } from '../playerProgress'
import type { SocialState } from '../social'
import { Avatar, SocialPortrait, presenceLabel } from './MenuChrome'

const frenchNumber = new Intl.NumberFormat('fr-FR')

export function matchOpponent(match: MatchState, playerId: string): string {
  return match.players.find(player => player.playerId !== playerId)?.displayName ?? 'Adversaire'
}

export function asyncTimeLeft(match: MatchState): string {
  const remaining = Math.max(0, new Date(match.turnEndsAt).getTime() - Date.now())
  const hours = Math.ceil(remaining / 3_600_000)
  return hours >= 1 ? `${hours} h` : `${Math.max(1, Math.ceil(remaining / 60_000))} min`
}

export function HomePage({ identity, progress, cosmetics, social, lobby, play, openFriends, resumeMatch }: { identity: GuestIdentity; progress: PlayerProgress; cosmetics: PlayerCosmetics; social: SocialState; lobby: MatchLobbyState; play: () => void; openFriends: () => void; resumeMatch: (matchId: string) => void }) {
  const firstRequest = social.incoming[0]
  const presenceWeight = { offline: 0, online: 1, playing: 2 }
  const visibleFriends = [...social.friends].sort((left, right) => presenceWeight[right.activity] - presenceWeight[left.activity]).slice(0, 3)
  const xpGoal = experienceGoalForLevel(progress.level)
  const xpPercent = progress.level >= MAX_PLAYER_LEVEL ? 100 : Math.min(100, progress.xp / xpGoal * 100)
  const currentMatch = lobby.active.find(match => match.pace === 'async')
  return <div className="mm-page mm-home-page">
    <section className="mm-home-profile-card">
      <CosmeticPortrait avatarId={cosmetics.equippedAvatarId} frameId={cosmetics.equippedFrameId} animationId={cosmetics.equippedAnimationId} alt="Votre avatar" />
      <div className="mm-home-profile-copy">
        <div className="mm-home-profile-heading">
          <h1>{identity.displayName}</h1>
          <span className="mm-home-feathers" aria-label={`${frenchNumber.format(cosmetics.plumes)} plumes`}><Feather aria-hidden="true" /><b>{frenchNumber.format(cosmetics.plumes)}</b></span>
        </div>
        <span>Niveau {progress.level}</span><small>Rang actuel</small><strong>Non classé</strong>
      </div>
      <div className="mm-home-xp"><span>{progress.level >= MAX_PLAYER_LEVEL ? 'Niveau max' : `${progress.xp} / ${xpGoal} XP`}</span><i><b style={{ width: `${xpPercent}%` }} /></i></div>
    </section>
    <section className="mm-attention">
      <h2>Partie en cours</h2>
      {currentMatch ? <button type="button" className="mm-current-match-card" onClick={() => resumeMatch(currentMatch.id)}>
        <Avatar label={playerInitials(matchOpponent(currentMatch, identity.playerId))} small />
        <span><strong>{matchOpponent(currentMatch, identity.playerId)}</strong><small>{currentMatch.currentPlayerId === identity.playerId ? 'À vous de jouer' : 'Tour adverse'} · {asyncTimeLeft(currentMatch)}</small></span>
        <ChevronRight />
      </button> : <div className="mm-empty-home-card">
        <span className="mm-empty-home-icon"><Gamepad2 /></span>
        <div><strong>Aucune partie en cours</strong><p>Votre prochaine partie apparaîtra ici.</p></div>
        <button type="button" onClick={play}>Jouer <ChevronRight /></button>
      </div>}
    </section>
    {firstRequest ? <button type="button" className="mm-home-friend-request" onClick={openFriends}>
      <SocialPortrait user={firstRequest.user} small />
      <span><strong>{firstRequest.user.displayName}</strong><small>vous envoie une demande d’ami</small></span>
      <b>{social.incoming.length}</b><ChevronRight />
    </button> : null}
    <section className="mm-home-friends">
      <header><h2>Amis</h2><button type="button" onClick={openFriends}><UserPlus />Ajouter</button></header>
      {visibleFriends.length ? <div className="mm-home-friend-list">{visibleFriends.map(friend => <div className="mm-home-friend" key={friend.playerId}>
        <span className="mm-home-friend-avatar"><SocialPortrait user={friend} small /><i className={friend.activity} /></span>
        <span><strong>{friend.displayName}</strong><small>{presenceLabel(friend.activity)}</small></span>
      </div>)}</div> : <button type="button" className="mm-home-add-first" onClick={openFriends}><span><UserPlus /></span><div><strong>Ajouter votre premier ami</strong><small>Jouez bientôt ensemble sur MotMan.</small></div><ChevronRight /></button>}
    </section>
  </div>
}
