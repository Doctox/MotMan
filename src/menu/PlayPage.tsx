import { useState, type ReactNode } from 'react'
import { BarChart3, ChevronRight, Clock3, History, Hourglass, Play, Swords, Trophy, UserPlus, Users } from 'lucide-react'
import type { GridDifficulty } from '../generator'
import { matchHistoryDateLabel, matchHistoryResultLabel, matchHistoryTone } from '../matchHistory'
import type { MatchHistoryEntry, MatchLobbyState, MatchPace } from '../matches'
import { playerInitials, type GuestIdentity } from '../playerIdentity'
import type { SocialState } from '../social'
import { Avatar, SocialPortrait, presenceLabel } from './MenuChrome'
import { asyncTimeLeft, matchOpponent } from './HomePage'

function SoonButton({ icon, title, subtitle, onClick }: { icon: ReactNode; title: string; subtitle: string; onClick: () => void }) {
  return <button type="button" className="mm-mode-row" onClick={onClick}><span className="mm-mode-icon">{icon}</span><span><strong>{title}</strong><small>{subtitle}</small></span><ChevronRight /></button>
}

function MatchmakingRow({ icon, title, subtitle, searching, disabled, start, cancel }: { icon: ReactNode; title: string; subtitle: string; searching: boolean; disabled: boolean; start: () => void; cancel: () => void }) {
  return <div className={`mm-matchmaking-row ${searching ? 'is-searching' : ''}`}>
    <button type="button" className="mm-mode-row" disabled={disabled} onClick={start}>
      <span className="mm-mode-icon">{icon}</span>
      <span><strong>{searching ? 'Recherche en cours' : title}</strong><small>{searching ? subtitle : subtitle}</small></span>
      {searching ? <span className="mm-search-pulse"><i /><i /><i /></span> : <ChevronRight />}
    </button>
    {searching ? <button type="button" className="mm-search-cancel" onClick={cancel}>Annuler</button> : null}
  </div>
}

type PlaySectionId = 'solo' | 'multiplayer' | 'normal' | 'ranked' | 'friends'

function PlayAccordion({ id, icon, title, open, toggle, children }: {
  id: PlaySectionId
  icon: ReactNode
  title: string
  open: boolean
  toggle: (id: PlaySectionId) => void
  children: ReactNode
}) {
  return <section className={`mm-play-accordion ${open ? 'is-open' : ''}`} id={`mm-${id}-accordion`}>
    <button
      type="button"
      className="mm-panel-heading"
      aria-expanded={open}
      aria-controls={`mm-${id}-options`}
      onClick={() => toggle(id)}
    >
      <span className="mm-dark-icon">{icon}</span>
      <h2>{title}</h2>
      <ChevronRight className="mm-accordion-chevron" />
    </button>
    <div className="mm-accordion-body" id={`mm-${id}-options`} aria-hidden={!open} inert={!open}>
      <div className="mm-panel-options">{children}</div>
    </div>
  </section>
}

const SOLO_LEVELS: Array<{ id: GridDifficulty; label: string; available: boolean }> = [
  { id: 'easy', label: 'Facile', available: true },
  { id: 'normal', label: 'Normal', available: true },
  { id: 'hard', label: 'Difficile', available: true },
]

function RecentMatchHistory({ matches, visible }: { matches: MatchHistoryEntry[]; visible: boolean }) {
  return <div className={`mm-recent-history ${visible ? 'is-visible' : ''}`} aria-hidden={!visible} inert={!visible}>
    <section className="mm-recent-history-card" aria-label="Historique des cinq derniers matchs">
      <header><span><History /></span><div><h2>Derniers matchs</h2><small>Vos cinq résultats les plus récents</small></div></header>
      {matches.length ? <div className="mm-recent-match-list">
        {matches.slice(0, 5).map(match => {
          const tone = matchHistoryTone(match.outcome)
          const opponentName = match.opponentName ?? (match.mode === 'solo' ? 'Adversaire solo' : 'Adversaire')
          return <article className="mm-recent-match-row" key={match.id}>
            <span className={`mm-recent-outcome ${tone}`}>{tone === 'won' ? 'V' : tone === 'drawn' ? 'N' : 'D'}</span>
            <span className="mm-recent-match-copy"><strong>{opponentName}</strong><small>{matchHistoryResultLabel(match.outcome)} · {match.mode === 'solo' ? 'Solo' : 'Multijoueur'} · {match.pace === 'async' ? 'Illimité' : 'Limité'}</small></span>
            <span className="mm-recent-match-score"><b>{match.score}<i>–</i>{match.opponentScore}</b><small>{matchHistoryDateLabel(match.completedAt)}</small></span>
          </article>
        })}
      </div> : <div className="mm-recent-history-empty"><History /><strong>Aucun match terminé</strong><small>Vos prochaines parties apparaîtront ici.</small></div>}
    </section>
  </div>
}

export function PlayPage({ identity, onStartSolo, soon, social, lobby, invite, cancelInvite, searchMatch, cancelSearch, resumeMatch, openFriends }: {
  identity: GuestIdentity
  onStartSolo: (difficulty: GridDifficulty, pace: MatchPace) => Promise<void>
  soon: () => void
  social: SocialState
  lobby: MatchLobbyState
  invite: (friendId: string, pace: MatchPace) => Promise<void>
  cancelInvite: (invitationId: string) => Promise<void>
  searchMatch: (pace: MatchPace) => Promise<void>
  cancelSearch: (pace: MatchPace) => Promise<void>
  resumeMatch: (matchId: string) => void
  openFriends: () => void
}) {
  const [difficulty, setDifficulty] = useState<GridDifficulty | null>(null)
  const [soloPace, setSoloPace] = useState<MatchPace | null>(null)
  const [friendPace, setFriendPace] = useState<MatchPace>('realtime')
  const [openSection, setOpenSection] = useState<PlaySectionId | null>(null)
  const [openMultiplayerSection, setOpenMultiplayerSection] = useState<PlaySectionId | null>(null)
  const [matchBusy, setMatchBusy] = useState<string | null>(null)
  const [searchBusy, setSearchBusy] = useState<MatchPace | null>(null)
  const [showActiveMatches, setShowActiveMatches] = useState(false)
  const [soloBusy, setSoloBusy] = useState(false)
  const [soloError, setSoloError] = useState<string | null>(null)
  const selectedLevel = SOLO_LEVELS.find(level => level.id === difficulty)
  const realtimeSearching = lobby.searches.some(search => search.pace === 'realtime')
  const asyncSearching = lobby.searches.some(search => search.pace === 'async')
  const asyncMatches = lobby.active.filter(match => match.mode === 'normal' && match.pace === 'async')

  const beginSearch = async (pace: MatchPace) => {
    setSearchBusy(pace)
    try { await searchMatch(pace) } finally { setSearchBusy(null) }
  }

  const stopSearch = async (pace: MatchPace) => {
    setSearchBusy(pace)
    try { await cancelSearch(pace) } finally { setSearchBusy(null) }
  }

  const toggleSection = (id: PlaySectionId) => {
    const next = openSection === id ? null : id
    setOpenSection(next)
    if (next === 'solo') setOpenMultiplayerSection(null)
    if (id === 'multiplayer') setOpenMultiplayerSection(null)
    if (!next) return
    window.requestAnimationFrame(() => {
      document.getElementById(`mm-${id}-accordion`)?.scrollIntoView({
        behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
        block: 'nearest',
      })
    })
  }

  const toggleMultiplayerSection = (id: PlaySectionId) => {
    setOpenMultiplayerSection(current => current === id ? null : id)
    setOpenSection('multiplayer')
  }

  return <div className="mm-page mm-play-page">
    <PlayAccordion id="solo" icon={<Play />} title="Solo" open={openSection === 'solo'} toggle={toggleSection}>
      <div className="mm-solo-options">
        <span>Niveau du bot</span>
        <div className="mm-difficulty-choice" role="group" aria-label="Choisir le niveau du bot">
          {SOLO_LEVELS.map(level => <button type="button" className={difficulty === level.id ? 'active' : ''} aria-pressed={difficulty === level.id} aria-label={level.label} disabled={!level.available} onClick={() => setDifficulty(level.id)} key={level.id}>{level.label}</button>)}
        </div>
        {difficulty ? <div className="mm-solo-pace-step">
          <span>Rythme</span>
          <div className="mm-solo-pace-choice" role="group" aria-label="Choisir le rythme de la partie solo">
            <button type="button" className={soloPace === 'realtime' ? 'active' : ''} aria-label="Temps limité, 45 secondes par tour" aria-pressed={soloPace === 'realtime'} onClick={() => setSoloPace('realtime')}><Clock3 /><span><strong>Temps limité</strong><small>45 s par tour</small></span></button>
            <button type="button" className={soloPace === 'async' ? 'active' : ''} aria-label="Temps illimité, 24 heures par tour" aria-pressed={soloPace === 'async'} onClick={() => setSoloPace('async')}><Hourglass /><span><strong>Temps illimité</strong><small>24 h par tour</small></span></button>
          </div>
        </div> : null}
        {soloError ? <p className="mm-social-error" role="alert">{soloError}</p> : null}
        <button type="button" className="mm-start-solo" disabled={!selectedLevel?.available || !soloPace || soloBusy} onClick={() => {
          if (!difficulty || !soloPace || soloBusy) return
          setSoloBusy(true); setSoloError(null)
          void onStartSolo(difficulty, soloPace).catch(reason => setSoloError(reason instanceof Error ? reason.message : 'Partie indisponible.')).finally(() => setSoloBusy(false))
        }}>{soloBusy ? 'Préparation…' : 'Jouer'} <ChevronRight /></button>
      </div>
    </PlayAccordion>

    <PlayAccordion id="multiplayer" icon={<Swords />} title="Multijoueur" open={openSection === 'multiplayer'} toggle={toggleSection}>
      <div className="mm-multiplayer-menu">
    <PlayAccordion id="normal" icon={<Trophy />} title="Normal" open={openMultiplayerSection === 'normal'} toggle={toggleMultiplayerSection}>
      <MatchmakingRow icon={<Clock3 />} title="Temps limité" subtitle={realtimeSearching ? 'Un adversaire est recherché…' : '45 s par tour'} searching={realtimeSearching} disabled={searchBusy !== null} start={() => void beginSearch('realtime')} cancel={() => void stopSearch('realtime')} />
      <MatchmakingRow icon={<Hourglass />} title="Temps illimité" subtitle={asyncSearching ? 'Vous pouvez revenir plus tard' : '24 h par tour'} searching={asyncSearching} disabled={searchBusy !== null} start={() => void beginSearch('async')} cancel={() => void stopSearch('async')} />
      <button type="button" className="mm-mode-row" aria-expanded={showActiveMatches} onClick={() => setShowActiveMatches(current => !current)}><span className="mm-mode-icon"><Users /></span><span><strong>Parties en cours</strong><small>Reprenez quand vous voulez</small></span><b className="mm-count">{asyncMatches.length}</b></button>
      {showActiveMatches ? <div className="mm-active-match-list">
        {asyncMatches.length ? asyncMatches.map(match => <button type="button" className="mm-active-match-row" onClick={() => resumeMatch(match.id)} key={match.id}>
          <Avatar label={playerInitials(matchOpponent(match, identity.playerId))} small />
          <span><strong>{matchOpponent(match, identity.playerId)}</strong><small>{match.currentPlayerId === identity.playerId ? 'À vous' : 'En attente'} · {asyncTimeLeft(match)}</small></span>
          <ChevronRight />
        </button>) : <p className="mm-no-active-match">Aucune partie en temps illimité en cours.</p>}
      </div> : null}
    </PlayAccordion>
    <PlayAccordion id="ranked" icon={<BarChart3 />} title="Classé" open={openMultiplayerSection === 'ranked'} toggle={toggleMultiplayerSection}>
      <SoonButton icon={<Clock3 />} title="Temps limité" subtitle="45 s par tour · Bientôt" onClick={soon} />
      <SoonButton icon={<Hourglass />} title="Temps illimité" subtitle="24 h par tour · Bientôt" onClick={soon} />
    </PlayAccordion>
    <PlayAccordion id="friends" icon={<Users />} title="Amis" open={openMultiplayerSection === 'friends'} toggle={toggleMultiplayerSection}>
      <div className="mm-friend-pace-step">
        <span>Rythme de la partie</span>
        <div className="mm-solo-pace-choice mm-friend-pace-choice" role="group" aria-label="Choisir le rythme de la partie entre amis">
          <button type="button" className={friendPace === 'realtime' ? 'active' : ''} aria-label="Amis, temps limité, 45 secondes par tour" aria-pressed={friendPace === 'realtime'} onClick={() => setFriendPace('realtime')}><Clock3 /><span><strong>Temps limité</strong><small>45 s par tour</small></span></button>
          <button type="button" className={friendPace === 'async' ? 'active' : ''} aria-label="Amis, temps illimité, 24 heures par tour" aria-pressed={friendPace === 'async'} onClick={() => setFriendPace('async')}><Hourglass /><span><strong>Temps illimité</strong><small>24 h par tour</small></span></button>
        </div>
      </div>
      {lobby.outgoing.map(invitation => <div className="mm-match-friend-row waiting" key={invitation.id}>
        <Avatar label={playerInitials(invitation.guest?.displayName ?? 'A')} small />
        <span><strong>{invitation.guest?.displayName ?? 'Votre ami'}</strong><small>{invitation.pace === 'async' ? 'Temps illimité' : 'Temps limité'} · Invitation envoyée…</small></span>
        <button type="button" disabled={matchBusy !== null} onClick={async () => { setMatchBusy(invitation.id); await cancelInvite(invitation.id); setMatchBusy(null) }}>Annuler</button>
      </div>)}
          {social.friends.length ? social.friends.map(friend => {
        const alreadyInvited = lobby.outgoing.some(invitation => invitation.guestId === friend.playerId)
        return <div className="mm-match-friend-row" key={friend.playerId}>
          <span className="mm-home-friend-avatar"><SocialPortrait user={friend} small /><i className={friend.activity} /></span>
          <span><strong>{friend.displayName}</strong><small>{presenceLabel(friend.activity)}</small></span>
          <button type="button" disabled={friendPace === 'realtime' && (!friend.online || friend.activity === 'playing') || alreadyInvited || matchBusy !== null} onClick={async () => { setMatchBusy(friend.playerId); await invite(friend.playerId, friendPace); setMatchBusy(null) }}>{alreadyInvited ? 'Envoyée' : friendPace === 'realtime' && friend.activity === 'playing' ? 'En jeu' : 'Inviter'}</button>
        </div>
          }) : <button type="button" className="mm-match-add-friend" onClick={openFriends}><UserPlus /><span><strong>Ajouter un ami</strong><small>Ajoutez un joueur avec son code ami.</small></span><ChevronRight /></button>}
        </PlayAccordion>
      </div>
    </PlayAccordion>
    <RecentMatchHistory matches={lobby.recent} visible={openSection === null} />
  </div>
}
