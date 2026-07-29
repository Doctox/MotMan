import { ChevronRight, Feather, Gamepad2, UserPlus } from 'lucide-react'
import { CosmeticPortrait } from '../CosmeticPortrait'
import type { PlayerCosmetics } from '../cosmetics'
import type { MatchLobbyState, MatchState } from '../matches'
import { playerInitials, type GuestIdentity } from '../playerIdentity'
import { experienceGoalForLevel, MAX_PLAYER_LEVEL, type PlayerProgress } from '../playerProgress'
import { rankImage, rankedDivision, rankedPlacementLabel } from '../ranked'
import type { SocialState } from '../social'
import { Avatar, SocialPortrait, presenceLabel } from './MenuChrome'

const frenchNumber = new Intl.NumberFormat('fr-FR')

export function matchOpponent(match: MatchState, playerId: string): string {
  return match.players.find(player => player.playerId !== playerId)?.displayName ?? 'Adversaire'
}

export function asyncTimeLeft(match: MatchState): string {
  const remaining = Math.max(0, new Date(match.turnEndsAt).getTime() - Date.now())
  return remaining >= 3_600_000
    ? `${Math.ceil(remaining / 3_600_000)} h`
    : `${Math.max(1, Math.ceil(remaining / 60_000))} min`
}

function activeMatchLabel(match: MatchState): string {
  if (match.mode === 'solo') return `Solo · Bot ${match.difficulty === 'easy' ? 'facile' : match.difficulty === 'hard' ? 'difficile' : 'normal'}`
  if (match.mode === 'friend') return 'Duel ami'
  return 'Match normal'
}

export function HomePage({ identity, progress, cosmetics, social, lobby, play, openFriends, resumeMatch }: { identity: GuestIdentity; progress: PlayerProgress; cosmetics: PlayerCosmetics; social: SocialState; lobby: MatchLobbyState; play: () => void; openFriends: () => void; resumeMatch: (matchId: string) => void }) {
  const firstRequest = social.incoming[0]
  const presenceWeight = { offline: 0, online: 1, playing: 2 }
  const visibleFriends = [...social.friends].sort((left, right) => presenceWeight[right.activity] - presenceWeight[left.activity]).slice(0, 3)
  const xpGoal = experienceGoalForLevel(progress.level)
  const xpPercent = progress.level >= MAX_PLAYER_LEVEL ? 100 : Math.min(100, progress.xp / xpGoal * 100)
  const currentRank = rankedDivision(progress.rankedPoints, progress.rankedMatches)
  const currentMatches = lobby.active
    .filter(match => match.pace === 'async')
    .sort((left, right) => {
      const leftTurn = left.currentPlayerId === identity.playerId ? 0 : 1
      const rightTurn = right.currentPlayerId === identity.playerId ? 0 : 1
      return leftTurn - rightTurn || new Date(left.turnEndsAt).getTime() - new Date(right.turnEndsAt).getTime()
    })
  return <div className="mm-page mm-home-page">
    <section className="mm-home-profile-card">
      <CosmeticPortrait avatarId={cosmetics.equippedAvatarId} frameId={cosmetics.equippedFrameId} animationId={cosmetics.equippedAnimationId} alt="Votre avatar" />
      <div className="mm-home-profile-copy">
        <div className="mm-home-profile-heading">
          <h1>{identity.displayName}</h1>
          <span className="mm-home-feathers" aria-label={`${frenchNumber.format(cosmetics.plumes)} plumes`}><Feather aria-hidden="true" /><b>{frenchNumber.format(cosmetics.plumes)}</b></span>
        </div>
        <span>Niveau {progress.level}</span><small>Rang actuel</small>
        <strong className="mm-home-rank"><img src={rankImage(currentRank)} alt="" />{currentRank.label}</strong>
        {progress.rankedMatches < 5 ? <em>{rankedPlacementLabel(progress.rankedMatches)}</em> : null}
      </div>
      <div className="mm-home-xp"><span>{progress.level >= MAX_PLAYER_LEVEL ? 'Niveau max' : `${progress.xp} / ${xpGoal} XP`}</span><i><b style={{ width: `${xpPercent}%` }} /></i></div>
    </section>
    <section className="mm-attention">
      <header className="mm-attention-heading">
        <h2>{currentMatches.length > 1 ? 'Parties en cours' : 'Partie en cours'}</h2>
        {currentMatches.length ? <span aria-label={`${currentMatches.length} parties en cours`}>{currentMatches.length}</span> : null}
      </header>
      {currentMatches.length ? <div className="mm-home-active-match-list">
        {currentMatches.map(match => {
          const opponentName = matchOpponent(match, identity.playerId)
          const myTurn = match.currentPlayerId === identity.playerId
          return <button type="button" className={`mm-current-match-card ${myTurn ? 'is-my-turn' : ''}`} onClick={() => resumeMatch(match.id)} key={match.id}>
            <Avatar label={playerInitials(opponentName)} small />
            <span>
              <strong>{opponentName}</strong>
              <small>{myTurn ? 'À vous de jouer' : 'Tour adverse'} · {asyncTimeLeft(match)}</small>
              <em>{activeMatchLabel(match)}</em>
            </span>
            <ChevronRight />
          </button>
        })}
      </div> : <div className="mm-empty-home-card">
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
