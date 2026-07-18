import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import {
  ArrowLeft, Ban, BarChart3, Check, ChevronRight, Clock3, Copy, Gamepad2, Settings, Home,
  Hourglass, LogIn, Moon, Music2, Pencil, Play, Shield, Sun, Swords,
  Trophy, User, UserMinus, UserPlus, Users, Vibrate, Volume2, X, Menu as MenuIcon,
  Feather, FileText, ShoppingBasket,
} from 'lucide-react'
import './menu.css'
import { assetUrl } from './assetUrl'
import type { GridDifficulty } from './generator'
import {
  loadPlayerIdentity, playerInitials, shortPlayerId,
  type GuestIdentity,
} from './playerIdentity'
import { experienceGoalForLevel, MAX_PLAYER_LEVEL, loadPlayerProgress, type PlayerProgress } from './playerProgress'
import {
  EMPTY_SOCIAL_STATE, loadSocialState, registerSocialProfile, respondToFriendRequest,
  reportPlayer, sendFriendRequest, updateFriend, type SocialState, type SocialUser,
} from './social'
import {
  cancelMatchInvitation, cancelNormalSearch, createInstantMatch, EMPTY_MATCH_LOBBY, loadMatchLobby,
  respondToMatchInvitation, searchNormalMatch, type MatchInvitation, type MatchLobbyState, type MatchPace, type MatchState,
} from './matches'
import { useSensoryPreferences } from './sensoryPreferences'
import { useDialogFocus } from './useDialogFocus'
import { getAnimation, getAvatar, getFrame, loadPlayerCosmetics, type PlayerCosmetics } from './cosmetics'
import { CosmeticPortrait } from './CosmeticPortrait'
import { PLAYER_NAME_MAX_LENGTH, validatePlayerName } from './playerNamePolicy'
import { startAdaptivePolling } from './adaptivePolling'
import {
  authenticateWithGoogle, createPlayerAccount, finishPlayerAccount, loginPlayerAccount, logoutPlayerAccount,
  consumePasswordRecovery, recoverPlayerAccount, subscribePasswordRecovery, updateServerProfile, type AuthResponse,
} from './auth'

export type MenuPage = 'home' | 'play' | 'ranking' | 'profile' | 'shop'
type Theme = 'light' | 'dark' | 'system'

const LazyShopPage = lazy(() => import('./ShopPage').then(module => ({ default: module.ShopPage })))
const LazyLegalPanel = lazy(() => import('./LegalPanel').then(module => ({ default: module.LegalPanel })))

function useResolvedTheme(theme: Theme) {
  useEffect(() => {
    localStorage.setItem('motman-theme', theme)
    const systemTheme = matchMedia('(prefers-color-scheme: dark)')
    const applyTheme = () => {
      document.documentElement.dataset.theme = theme === 'system'
        ? (systemTheme.matches ? 'dark' : 'light')
        : theme
    }
    applyTheme()
    if (theme !== 'system') return
    systemTheme.addEventListener('change', applyTheme)
    return () => systemTheme.removeEventListener('change', applyTheme)
  }, [theme])
}

function sameState<T>(left: T, right: T): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

type MenuAppProps = {
  onStartSolo: (difficulty: GridDifficulty, pace: MatchPace) => Promise<void>
  onStartMatch: (matchId: string) => void
}

function Brand() {
  return <div className="mm-brand"><img src={assetUrl('/assets/motman-logo-v2.webp')} alt="MotMan" /></div>
}

function Avatar({ label = 'A', small = false }: { label?: string; small?: boolean }) {
  return <span className={`mm-avatar ${small ? 'small' : ''}`} aria-hidden="true">{label}</span>
}

function SocialPortrait({ user, small = false }: { user: Pick<SocialUser, 'displayName' | 'avatarId' | 'frameId' | 'animationId'>; small?: boolean }) {
  return user.avatarId ? <CosmeticPortrait avatarId={user.avatarId} frameId={user.frameId ?? 'cadre-ivoire'} animationId={user.animationId} alt="" small={small} />
    : <Avatar label={playerInitials(user.displayName)} small={small} />
}

function presenceLabel(activity: 'offline' | 'online' | 'playing'): string {
  return activity === 'playing' ? 'En jeu' : activity === 'online' ? 'En ligne' : 'Hors ligne'
}

function AppHeader({ onMenu, onSettings }: { onMenu: () => void; onSettings: () => void }) {
  return <header className="mm-header">
    <button className="mm-header-round" type="button" aria-label="Ouvrir le menu" onClick={onMenu}><MenuIcon /></button>
    <Brand />
    <button className="mm-icon-button" type="button" aria-label="Paramètres" onClick={onSettings}><Settings /></button>
  </header>
}

function BottomNav({ page, setPage }: { page: MenuPage; setPage: (page: MenuPage) => void }) {
  const activePage = page === 'shop' ? 'profile' : page
  const items: Array<[MenuPage, string, ReactNode]> = [
    ['home', 'Accueil', <Home />], ['play', 'Jouer', <Gamepad2 />],
    ['ranking', 'Classement', <BarChart3 />], ['profile', 'Profil', <User />],
  ]
  return <nav className="mm-bottom-nav" aria-label="Navigation principale">
    {items.map(([id, label, icon]) => <button key={id} type="button" className={activePage === id ? 'active' : ''} aria-current={activePage === id ? 'page' : undefined} onClick={() => setPage(id)}>{icon}<span>{label}</span></button>)}
  </nav>
}

function RankProgress({ progress, compact = false }: { progress: PlayerProgress; compact?: boolean }) {
  return <section className={`mm-rank-progress mm-rank-progress-empty ${compact ? 'compact' : ''}`} aria-label="Progression classée">
    <span className="mm-unranked-badge"><Trophy /></span>
    <div className="mm-rank-copy"><strong>Non classé</strong><span>{progress.rankedPoints} pt</span></div>
    <div className="mm-progress"><small>Aucune partie classée</small><i><b /></i></div>
  </section>
}

function matchOpponent(match: MatchState, playerId: string): string {
  return match.players.find(player => player.playerId !== playerId)?.displayName ?? 'Adversaire'
}

function asyncTimeLeft(match: MatchState): string {
  const remaining = Math.max(0, new Date(match.turnEndsAt).getTime() - Date.now())
  const hours = Math.ceil(remaining / 3_600_000)
  return hours >= 1 ? `${hours} h` : `${Math.max(1, Math.ceil(remaining / 60_000))} min`
}

function HomePage({ identity, progress, cosmetics, social, lobby, play, openFriends, resumeMatch }: { identity: GuestIdentity; progress: PlayerProgress; cosmetics: PlayerCosmetics; social: SocialState; lobby: MatchLobbyState; play: () => void; openFriends: () => void; resumeMatch: (matchId: string) => void }) {
  const firstRequest = social.incoming[0]
  const presenceWeight = { offline: 0, online: 1, playing: 2 }
  const visibleFriends = [...social.friends].sort((left, right) => presenceWeight[right.activity] - presenceWeight[left.activity]).slice(0, 3)
  const xpGoal = experienceGoalForLevel(progress.level)
  const xpPercent = progress.level >= MAX_PLAYER_LEVEL ? 100 : Math.min(100, progress.xp / xpGoal * 100)
  const currentMatch = lobby.active.find(match => match.pace === 'async')
  return <div className="mm-page mm-home-page">
    <section className="mm-home-profile-card">
      <CosmeticPortrait avatarId={cosmetics.equippedAvatarId} frameId={cosmetics.equippedFrameId} animationId={cosmetics.equippedAnimationId} alt="Votre avatar" />
      <div className="mm-home-profile-copy"><h1>{identity.displayName}</h1><span>Niveau {progress.level}</span><small>Rang actuel</small><strong>Non classé</strong></div>
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

type PlaySectionId = 'solo' | 'normal' | 'ranked' | 'friends'

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

function PlayPage({ identity, onStartSolo, soon, social, lobby, invite, cancelInvite, searchMatch, cancelSearch, resumeMatch, openFriends }: {
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
    if (!next) return
    window.requestAnimationFrame(() => {
      document.getElementById(`mm-${id}-accordion`)?.scrollIntoView({
        behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
        block: 'nearest',
      })
    })
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
    <PlayAccordion id="normal" icon={<Trophy />} title="Normal" open={openSection === 'normal'} toggle={toggleSection}>
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
    <PlayAccordion id="ranked" icon={<BarChart3 />} title="Classé" open={openSection === 'ranked'} toggle={toggleSection}>
      <SoonButton icon={<Clock3 />} title="Temps limité" subtitle="45 s par tour · Bientôt" onClick={soon} />
      <SoonButton icon={<Hourglass />} title="Temps illimité" subtitle="24 h par tour · Bientôt" onClick={soon} />
    </PlayAccordion>
    <PlayAccordion id="friends" icon={<Users />} title="Amis" open={openSection === 'friends'} toggle={toggleSection}>
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
      }) : <button type="button" className="mm-match-add-friend" onClick={openFriends}><UserPlus /><span><strong>Ajouter un ami</strong><small>Ajoutez votre femme avec son code ami.</small></span><ChevronRight /></button>}
    </PlayAccordion>
  </div>
}

function MatchInvitationPanel({ invitation, busy, accept, decline }: {
  invitation: MatchInvitation
  busy: boolean
  accept: () => void
  decline: () => void
}) {
  const hostName = invitation.host?.displayName ?? 'Un ami'
  const isAsync = invitation.pace === 'async'
  const dialogRef = useDialogFocus<HTMLElement>()
  return <div className="mm-modal-layer mm-match-invite-layer" role="presentation">
    <section ref={dialogRef} className="mm-match-invite" role="dialog" aria-modal="true" aria-label="Invitation à jouer" tabIndex={-1}>
      <span className="mm-match-emblem"><Swords /></span>
      <small>Invitation à jouer</small>
      <h2>{hostName} vous défie</h2>
      <div className="mm-match-rule">{isAsync ? <Hourglass /> : <Clock3 />}<span><strong>{isAsync ? 'Temps illimité' : 'Temps limité'}</strong><small>{isAsync ? '24 heures par tour' : '45 secondes par tour'}</small></span></div>
      <div className="mm-match-invite-actions"><button type="button" className="secondary" disabled={busy} onClick={decline}>Refuser</button><button type="button" data-dialog-autofocus disabled={busy} onClick={accept}>{busy ? 'Connexion…' : 'Accepter'}</button></div>
    </section>
  </div>
}

function MatchWaitingPanel({ invitation, busy, cancel }: { invitation: MatchInvitation; busy: boolean; cancel: () => void }) {
  const isAsync = invitation.pace === 'async'
  return <section className="mm-live-activity" role="region" aria-live="polite" aria-label="Invitation en attente">
    <span className="mm-live-activity-icon"><Avatar label={playerInitials(invitation.guest?.displayName ?? 'A')} small /><i /></span>
    <span className="mm-live-activity-copy"><small>Invitation envoyée</small><strong>{invitation.guest?.displayName ?? 'Votre ami'}</strong><em>{isAsync ? 'Temps illimité · 24 h' : 'Temps limité · 45 s'}</em></span>
    <span className="mm-live-activity-dots" aria-hidden="true"><i /><i /><i /></span>
    <button type="button" disabled={busy} onClick={cancel}>{busy ? 'Annulation…' : 'Annuler'}</button>
  </section>
}

function NormalSearchPanel({ busy, cancel }: { busy: boolean; cancel: () => void }) {
  return <section className="mm-live-activity" role="region" aria-live="polite" aria-label="Recherche d’un adversaire">
    <span className="mm-live-activity-icon swords"><Swords /></span>
    <span className="mm-live-activity-copy"><small>Match normal</small><strong>Recherche en cours</strong><em>Temps limité · 45 s</em></span>
    <span className="mm-live-activity-dots" aria-hidden="true"><i /><i /><i /></span>
    <button type="button" disabled={busy} onClick={cancel}>{busy ? 'Annulation…' : 'Annuler'}</button>
  </section>
}

function RankingPage({ identity, progress, cosmetics }: { identity: GuestIdentity; progress: PlayerProgress; cosmetics: PlayerCosmetics }) {
  const [tab, setTab] = useState<'general' | 'friends'>('general')
  return <div className="mm-page mm-ranking-page">
    <RankProgress progress={progress} compact />
    <div className="mm-segmented" role="group" aria-label="Type de classement"><button type="button" className={tab === 'general' ? 'active' : ''} aria-pressed={tab === 'general'} onClick={() => setTab('general')}>Général</button><button type="button" className={tab === 'friends' ? 'active' : ''} aria-pressed={tab === 'friends'} onClick={() => setTab('friends')}>Amis</button></div>
    <section className="mm-leaderboard">
      {tab === 'general' ? <div className="mm-ranking-row you">
        <span className="mm-position">—</span><CosmeticPortrait avatarId={cosmetics.equippedAvatarId} frameId={cosmetics.equippedFrameId} animationId={cosmetics.equippedAnimationId} alt="" small /><strong>{identity.displayName}<small>Vous</small></strong><b>{progress.rankedPoints} <small>pt</small></b>
      </div> : null}
      <div className="mm-empty-ranking"><Trophy /><strong>{tab === 'general' ? 'Pas encore classé' : 'Aucun ami classé'}</strong><span>{tab === 'general' ? 'Terminez une partie classée pour rejoindre le classement.' : 'Le classement de vos amis apparaîtra ici.'}</span></div>
    </section>
  </div>
}

function ProfilePage({ identity, progress, cosmetics, edit, openShop, openAccount }: { identity: GuestIdentity; progress: PlayerProgress; cosmetics: PlayerCosmetics; edit: () => void; openShop: () => void; openAccount: () => void }) {
  const xpGoal = experienceGoalForLevel(progress.level)
  const xpPercent = progress.level >= MAX_PLAYER_LEVEL ? 100 : Math.min(100, progress.xp / xpGoal * 100)
  const equippedTitle = progress.titles.find(title => title.id === progress.equippedTitleId)
  return <div className="mm-page mm-profile-page">
    <section className="mm-profile-hero"><CosmeticPortrait avatarId={cosmetics.equippedAvatarId} frameId={cosmetics.equippedFrameId} animationId={cosmetics.equippedAnimationId} alt="Votre avatar" /><div><h1>{identity.displayName}</h1>{equippedTitle ? <small className="mm-equipped-title">{equippedTitle.name}</small> : null}<button type="button" onClick={edit}><Pencil />Modifier</button></div></section>
    <section className="mm-level"><div><BarChart3 /><strong>Niveau {progress.level}</strong><span>{progress.level >= MAX_PLAYER_LEVEL ? 'Niveau maximum' : `Niveau ${progress.level + 1}`}</span></div><i className="guest-progress"><b style={{ width: `${xpPercent}%` }} /></i><p>{progress.level >= MAX_PLAYER_LEVEL ? <strong>Niveau maximum atteint</strong> : <><strong>{progress.xp}</strong> / {xpGoal} XP</>}</p></section>
    <button type="button" className="mm-grocery-entry" onClick={openShop}>
      <span className="mm-grocery-basket"><ShoppingBasket /></span>
      <span><small>Collection & trouvailles</small><strong>L’Épicerie</strong></span>
      <b><Feather />{cosmetics.plumes}</b><ChevronRight />
    </button>
    <section className="mm-stats"><div><Trophy /><strong>{progress.wins}</strong><span>Victoires</span></div><i /><div><Shield /><strong>{progress.losses}</strong><span>Défaites</span></div></section>
    <button type="button" className="mm-account" onClick={openAccount}><User /><span><strong>{identity.accountType === 'account' ? 'Compte synchronisé' : 'Compte invité'}</strong><small>Code ami {identity.friendCode ?? shortPlayerId(identity.playerId)}</small></span><b>{identity.accountType === 'account' ? 'Gérer' : 'Créer un compte'}</b><ChevronRight /></button>
  </div>
}

function QuickMenu({ page, navigate, close }: { page: MenuPage; navigate: (page: MenuPage) => void; close: () => void }) {
  const items: Array<[MenuPage, string, ReactNode]> = [
    ['home', 'Accueil', <Home />], ['play', 'Jouer', <Gamepad2 />],
    ['ranking', 'Classement', <BarChart3 />], ['profile', 'Profil', <User />],
  ]
  const dialogRef = useDialogFocus<HTMLElement>(close)
  return <div className="mm-modal-layer mm-quick-menu-layer" role="presentation" onMouseDown={event => event.target === event.currentTarget && close()}>
    <section ref={dialogRef} className="mm-quick-menu" role="dialog" aria-modal="true" aria-label="Menu principal" tabIndex={-1}>
      <header><h2>Menu</h2><button type="button" aria-label="Fermer" onClick={close}><X /></button></header>
      <nav>{items.map(([id, label, icon]) => <button type="button" className={page === id ? 'active' : ''} aria-current={page === id ? 'page' : undefined} onClick={() => { navigate(id); close() }} key={id}>{icon}<span>{label}</span><ChevronRight /></button>)}</nav>
    </section>
  </div>
}

function EditGuestPanel({ identity, progress, cosmetics, close, save }: {
  identity: GuestIdentity
  progress: PlayerProgress
  cosmetics: PlayerCosmetics
  close: () => void
  save: (displayName: string, avatarId: string, frameId: string, animationId: string, titleId: string | null) => Promise<void>
}) {
  const [displayName, setDisplayName] = useState(identity.displayName)
  const [avatarId, setAvatarId] = useState(cosmetics.equippedAvatarId)
  const [frameId, setFrameId] = useState(cosmetics.equippedFrameId)
  const [animationId, setAnimationId] = useState(cosmetics.equippedAnimationId)
  const [titleId, setTitleId] = useState<string | null>(progress.equippedTitleId)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nameValidation = validatePlayerName(displayName)
  const normalized = nameValidation.normalized
  const dialogRef = useDialogFocus<HTMLFormElement>(close)
  return <div className="mm-modal-layer" role="presentation" onMouseDown={event => event.target === event.currentTarget && close()}>
    <form ref={dialogRef} className="mm-guest-editor mm-profile-editor" role="dialog" aria-modal="true" aria-label="Modifier le profil invité" tabIndex={-1} onSubmit={event => {
      event.preventDefault()
      if (!nameValidation.valid || busy) return
      setBusy(true); setError(null)
      void save(normalized, avatarId, frameId, animationId, titleId).catch(reason => setError(reason instanceof Error ? reason.message : 'Enregistrement impossible.')).finally(() => setBusy(false))
    }}>
      <header><div><small>Votre identité</small><h2>Modifier le profil</h2></div><button type="button" onClick={close} aria-label="Fermer"><X /></button></header>
      <div className="mm-guest-preview"><CosmeticPortrait avatarId={avatarId} frameId={frameId} animationId={animationId} alt="Aperçu de votre avatar" /><span><strong>{normalized || 'Votre pseudo'}</strong><small>{progress.titles.find(title => title.id === titleId)?.name ?? `ID ${shortPlayerId(identity.playerId)}`}</small></span></div>
      <div className="mm-profile-editor-scroll">
      <label htmlFor="guest-display-name">Pseudo</label>
      <input id="guest-display-name" data-dialog-autofocus value={displayName} maxLength={PLAYER_NAME_MAX_LENGTH} autoComplete="nickname" aria-invalid={!nameValidation.valid} aria-describedby="guest-display-name-help" onChange={event => setDisplayName(event.target.value)} />
      <p id="guest-display-name-help" className={`mm-name-help ${nameValidation.valid ? 'valid' : 'invalid'}`} role="status">
        {nameValidation.valid ? `${Array.from(normalized).length}/${PLAYER_NAME_MAX_LENGTH}` : nameValidation.error}
      </p>
      <fieldset><legend>Avatar</legend><div className="mm-owned-avatar-grid">{cosmetics.ownedAvatarIds.map(id => {
        const avatar = getAvatar(id)
        return <button type="button" className={avatarId === id ? 'active' : ''} aria-pressed={avatarId === id} onClick={() => setAvatarId(id)} key={id}><CosmeticPortrait avatarId={id} frameId="cadre-ivoire" alt={avatar.name} /><span>{avatar.name}</span></button>
      })}</div></fieldset>
      <fieldset><legend>Cadre</legend><div className="mm-owned-frame-grid">{cosmetics.ownedFrameIds.map(id => {
        const frame = getFrame(id)
        return <button type="button" className={frameId === id ? 'active' : ''} aria-pressed={frameId === id} onClick={() => setFrameId(id)} key={id}><CosmeticPortrait avatarId={avatarId} frameId={id} alt={frame.name} /><span>{frame.name}</span></button>
      })}</div></fieldset>
      <fieldset><legend>Animation</legend><div className="mm-owned-animation-grid">{cosmetics.ownedAnimationIds.map(id => {
        const animation = getAnimation(id)
        return <button type="button" className={animationId === id ? 'active' : ''} aria-pressed={animationId === id} onClick={() => setAnimationId(id)} key={id}><CosmeticPortrait avatarId={avatarId} frameId={frameId} animationId={id} alt={animation.name} /><span>{animation.name}</span></button>
      })}</div></fieldset>
      <fieldset><legend>Titre</legend><div className="mm-owned-title-grid">
        <button type="button" className={titleId === null ? 'active' : ''} aria-pressed={titleId === null} onClick={() => setTitleId(null)}><strong>Sans titre</strong><small>Profil épuré</small></button>
        {progress.titles.map(title => <button type="button" disabled={!title.unlocked} className={titleId === title.id ? 'active' : ''} aria-pressed={titleId === title.id} onClick={() => title.unlocked && setTitleId(title.id)} key={title.id}><strong>{title.name}</strong><small>{title.unlocked ? title.description : title.unlockType === 'level' ? `Niveau ${title.requiredValue}` : 'Classement'}</small></button>)}
      </div></fieldset>
      {error ? <p className="mm-account-error" role="alert">{error}</p> : null}
      </div>
      <button className="mm-save-guest" type="submit" disabled={!nameValidation.valid || busy}>{busy ? 'Enregistrement…' : 'Enregistrer'}</button>
    </form>
  </div>
}

function ToggleRow({ icon, label, checked, setChecked }: { icon: ReactNode; label: string; checked: boolean; setChecked: (value: boolean) => void }) {
  return <label className="mm-setting-row"><span>{icon}{label}</span><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} /><i /></label>
}

function FriendsPanel({ identity, social, setSocial, close, notify }: {
  identity: GuestIdentity
  social: SocialState
  setSocial: (state: SocialState) => void
  close: () => void
  notify: (message: string) => void
}) {
  const [friendCode, setFriendCode] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [managedFriend, setManagedFriend] = useState<string | null>(null)
  const [reportTarget, setReportTarget] = useState<SocialUser | null>(null)
  const [reportReason, setReportReason] = useState<'pseudo' | 'comportement' | 'triche' | 'harcelement' | 'autre'>('comportement')
  const [reportDetails, setReportDetails] = useState('')
  const [reportBusy, setReportBusy] = useState(false)
  const ownCode = shortPlayerId(identity.playerId)
  const dialogRef = useDialogFocus<HTMLElement>(close)

  const run = async (key: string, action: () => Promise<SocialState>, success?: string) => {
    setBusy(key)
    setError(null)
    try {
      setSocial(await action())
      if (success) notify(success)
      return true
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Une erreur est survenue.')
      return false
    } finally {
      setBusy(null)
    }
  }

  const submitFriendCode = async (event: FormEvent) => {
    event.preventDefault()
    const sent = await run('add', () => sendFriendRequest(identity.playerId, friendCode), 'Demande envoyée')
    if (sent) setFriendCode('')
  }

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(ownCode)
      notify('Code ami copié')
    } catch {
      notify(`Votre code : ${ownCode}`)
    }
  }

  const submitReport = async (event: FormEvent) => {
    event.preventDefault()
    if (!reportTarget || reportBusy) return
    setReportBusy(true); setError(null)
    try {
      await reportPlayer(reportTarget.playerId, reportReason, reportDetails)
      notify('Signalement transmis à la modération')
      setReportTarget(null); setReportDetails(''); setManagedFriend(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Signalement impossible.')
    } finally { setReportBusy(false) }
  }

  return <div className="mm-modal-layer mm-friends-layer" role="presentation" onMouseDown={event => event.target === event.currentTarget && close()}>
    <section ref={dialogRef} className="mm-friends-panel" role="dialog" aria-modal="true" aria-label="Gestion des amis" aria-busy={busy !== null} tabIndex={-1}>
      <header><button type="button" onClick={close} aria-label="Retour"><ArrowLeft /></button><h2>Amis</h2><span /></header>
      <div className="mm-friends-scroll">
        <section className="mm-friend-code-card">
          <div><small>Votre code ami</small><strong>{ownCode}</strong><p>Votre ami doit ouvrir MotMan sur le même serveur.</p></div>
          <button type="button" onClick={copyCode} aria-label="Copier le code ami"><Copy /></button>
        </section>

        <form className="mm-add-friend" onSubmit={submitFriendCode}>
          <label htmlFor="friend-code">Ajouter un ami</label>
          <div><input id="friend-code" value={friendCode} onChange={event => setFriendCode(event.target.value.toUpperCase().replace(/[^A-F0-9]/g, '').slice(0, 8))} placeholder="CODE AMI" inputMode="text" autoComplete="off" /><button type="submit" disabled={friendCode.length !== 8 || busy !== null}><UserPlus />Ajouter</button></div>
        </form>
        {error ? <p className="mm-social-error" role="alert">{error}</p> : null}

        {social.incoming.length ? <section className="mm-social-section">
          <h3>Demandes reçues <b>{social.incoming.length}</b></h3>
          {social.incoming.map(request => <article className="mm-social-row request" key={request.id}>
            <SocialPortrait user={request.user} small /><span><strong>{request.user.displayName}</strong><small>Souhaite devenir votre ami</small></span>
            <button type="button" className="accept" disabled={busy !== null} onClick={() => void run(request.id, () => respondToFriendRequest(identity.playerId, request.id, 'accept'), 'Ami ajouté')} aria-label={`Accepter ${request.user.displayName}`}><Check /></button>
            <button type="button" className="decline" disabled={busy !== null} onClick={() => void run(request.id, () => respondToFriendRequest(identity.playerId, request.id, 'decline'))} aria-label={`Refuser ${request.user.displayName}`}><X /></button>
          </article>)}
        </section> : null}

        <section className="mm-social-section">
          <h3>Mes amis <b>{social.friends.length}</b></h3>
          {social.friends.length ? social.friends.map(friend => <article className="mm-social-row friend" key={friend.playerId}>
            <span className="mm-home-friend-avatar"><SocialPortrait user={friend} small /><i className={friend.activity} /></span><span><strong>{friend.displayName}</strong><small>{presenceLabel(friend.activity)} · {friend.code}</small></span>
            <button type="button" className="manage" onClick={() => setManagedFriend(current => current === friend.playerId ? null : friend.playerId)} aria-label={`Gérer ${friend.displayName}`}>•••</button>
            {managedFriend === friend.playerId ? <div className="mm-friend-actions">
              <button type="button" disabled={busy !== null} onClick={() => void run(friend.playerId, () => updateFriend(identity.playerId, friend.playerId, 'remove'), 'Ami retiré')}><UserMinus />Retirer</button>
              <button type="button" disabled={busy !== null} onClick={() => setReportTarget(friend)}><Shield />Signaler</button>
              <button type="button" className="danger" disabled={busy !== null} onClick={() => void run(friend.playerId, () => updateFriend(identity.playerId, friend.playerId, 'block'), 'Joueur bloqué')}><Ban />Bloquer</button>
            </div> : null}
          </article>) : <div className="mm-social-empty"><Users /><strong>Votre liste est vide</strong><span>Ajoutez votre premier ami avec son code.</span></div>}
        </section>

        {social.outgoing.length ? <section className="mm-social-section subdued">
          <h3>En attente <b>{social.outgoing.length}</b></h3>
          {social.outgoing.map(request => <article className="mm-social-row" key={request.id}>
            <SocialPortrait user={request.user} small /><span><strong>{request.user.displayName}</strong><small>Demande envoyée</small></span>
            <button type="button" className="text-action" disabled={busy !== null} onClick={() => void run(request.id, () => updateFriend(identity.playerId, request.user.playerId, 'cancel'))}>Annuler</button>
          </article>)}
        </section> : null}

        {social.blocked.length ? <details className="mm-blocked-list"><summary>Joueurs bloqués ({social.blocked.length})</summary>{social.blocked.map(user => <article className="mm-social-row" key={user.playerId}><SocialPortrait user={user} small /><span><strong>{user.displayName}</strong><small>Bloqué</small></span><button type="button" className="text-action" disabled={busy !== null} onClick={() => void run(user.playerId, () => updateFriend(identity.playerId, user.playerId, 'unblock'), 'Joueur débloqué')}>Débloquer</button></article>)}</details> : null}
      </div>
    </section>
    {reportTarget ? <div className="mm-modal-layer mm-report-layer" role="presentation">
      <form className="mm-settings mm-report-panel" role="dialog" aria-modal="true" aria-label={`Signaler ${reportTarget.displayName}`} onSubmit={submitReport}>
        <header><h2>Signaler {reportTarget.displayName}</h2><button type="button" onClick={() => setReportTarget(null)} aria-label="Fermer"><X /></button></header>
        <label htmlFor="report-reason">Motif</label>
        <select id="report-reason" value={reportReason} onChange={event => setReportReason(event.target.value as typeof reportReason)}>
          <option value="pseudo">Pseudo inapproprié</option><option value="comportement">Comportement</option><option value="triche">Triche</option><option value="harcelement">Harcèlement</option><option value="autre">Autre</option>
        </select>
        <label htmlFor="report-details">Précisions facultatives</label>
        <textarea id="report-details" maxLength={500} value={reportDetails} onChange={event => setReportDetails(event.target.value)} placeholder="Décrivez brièvement le problème." />
        <button className="mm-save-guest" type="submit" disabled={reportBusy}>{reportBusy ? 'Envoi…' : 'Envoyer le signalement'}</button>
      </form>
    </div> : null}
  </div>
}

function SettingsPanel({ identity, close, openAccount, openFriends, openLegal, theme, setTheme }: { identity: GuestIdentity; close: () => void; openAccount: () => void; openFriends: () => void; openLegal: () => void; theme: Theme; setTheme: (theme: Theme) => void }) {
  const { preferences, setPreference } = useSensoryPreferences()
  const dialogRef = useDialogFocus<HTMLElement>(close)
  return <div className="mm-modal-layer" role="presentation" onMouseDown={event => event.target === event.currentTarget && close()}>
    <section ref={dialogRef} className="mm-settings" role="dialog" aria-modal="true" aria-label="Paramètres" tabIndex={-1}>
      <header><h2>Paramètres</h2><button type="button" onClick={close} aria-label="Fermer"><X /></button></header>
      <div className="mm-theme-choice" role="group" aria-label="Thème"><button type="button" className={theme === 'light' ? 'active' : ''} aria-pressed={theme === 'light'} onClick={() => setTheme('light')}><Sun />Clair</button><button type="button" className={theme === 'dark' ? 'active' : ''} aria-pressed={theme === 'dark'} onClick={() => setTheme('dark')}><Moon />Sombre</button><button type="button" className={theme === 'system' ? 'active' : ''} aria-pressed={theme === 'system'} onClick={() => setTheme('system')}><Settings />Système</button></div>
      <ToggleRow icon={<Music2 />} label="Musique" checked={preferences.music} setChecked={value => setPreference('music', value)} />
      <ToggleRow icon={<Volume2 />} label="Effets" checked={preferences.effects} setChecked={value => setPreference('effects', value)} />
      <ToggleRow icon={<Vibrate />} label="Vibrations" checked={preferences.vibration} setChecked={value => setPreference('vibration', value)} />
      <button className="mm-settings-link" type="button" onClick={openFriends}><UserPlus /><span>Amis<small>Ajouter · retirer · bloquer</small></span><ChevronRight /></button>
      <button className="mm-settings-link" type="button" onClick={openAccount}><LogIn /><span>{identity.accountType === 'account' ? 'Compte synchronisé' : 'Créer ou retrouver un compte'}<small>{identity.accountType === 'account' ? identity.displayName : 'Sauvegarder votre progression'}</small></span><ChevronRight /></button>
      <button className="mm-settings-link" type="button" onClick={openLegal}><FileText /><span>Informations<small>Confidentialité · conditions · crédits</small></span><ChevronRight /></button>
    </section>
  </div>
}

type AccountMode = 'create' | 'login' | 'recover'

function AccountPanel({ identity, close, apply, notify }: {
  identity: GuestIdentity
  close: () => void
  apply: (response: AuthResponse) => void
  notify: (message: string) => void
}) {
  const [mode, setMode] = useState<AccountMode>('create')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const dialogRef = useDialogFocus<HTMLFormElement>(close)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true); setError(null)
    try {
      if (identity.accountType === 'account') {
        const response = await finishPlayerAccount(password)
        apply(response); notify('Mot de passe enregistré'); close(); return
      }
      if (mode === 'recover') {
        await recoverPlayerAccount(email)
        notify('E-mail de récupération envoyé'); close(); return
      }
      if (mode === 'login') {
        const response = await loginPlayerAccount(email, password)
        apply(response); notify('Compte synchronisé'); close(); return
      }
      const response = await createPlayerAccount(email)
      apply(response)
      notify('Vérifiez votre e-mail pour protéger ce profil')
      close()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Opération impossible.')
    } finally { setBusy(false) }
  }

  const logout = async () => {
    setBusy(true); setError(null)
    try {
      const next = await logoutPlayerAccount()
      apply({ identity: next, progress: loadPlayerProgress(next.playerId), cosmetics: loadPlayerCosmetics(next.playerId) })
      notify('Déconnecté · nouveau profil invité'); close()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Déconnexion impossible.') }
    finally { setBusy(false) }
  }

  const google = async () => {
    setBusy(true); setError(null)
    try { await authenticateWithGoogle() }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Connexion Google indisponible.')
      setBusy(false)
    }
  }

  return <div className="mm-modal-layer" role="presentation" onMouseDown={event => event.target === event.currentTarget && close()}>
    <form ref={dialogRef} className="mm-guest-editor mm-account-panel" role="dialog" aria-modal="true" aria-label="Compte MotMan" tabIndex={-1} onSubmit={submit}>
      <header><div><small>Progression sécurisée</small><h2>{identity.accountType === 'account' ? 'Votre compte' : mode === 'create' ? 'Créer mon compte' : mode === 'login' ? 'Me connecter' : 'Retrouver mon compte'}</h2></div><button type="button" onClick={close} aria-label="Fermer"><X /></button></header>
      <button className="mm-google-auth" type="button" disabled={busy} onClick={() => void google()}><span aria-hidden="true">G</span>{identity.accountType === 'account' ? 'Lier mon compte Google' : 'Continuer avec Google'}</button>
      <div className="mm-account-divider"><span>ou</span></div>
      {identity.accountType === 'account' ? <>
        <div className="mm-account-current"><User /><span><strong>{identity.displayName}</strong><small>Synchronisé sur Android, Apple et PC</small></span></div>
        <label htmlFor="account-password">Définir ou changer le mot de passe</label>
        <input id="account-password" data-dialog-autofocus type="password" minLength={10} maxLength={128} value={password} autoComplete="new-password" onChange={event => setPassword(event.target.value)} />
        <p>10 caractères minimum.</p>
        {error ? <p className="mm-account-error" role="alert">{error}</p> : null}
        <button className="mm-save-guest" type="submit" disabled={busy || password.length < 10}>Enregistrer le mot de passe</button>
        <button className="mm-account-logout" type="button" disabled={busy} onClick={() => void logout()}>Se déconnecter</button>
      </> : <>
        <div className="mm-account-tabs" role="tablist" aria-label="Accès au compte">
          <button type="button" className={mode === 'create' ? 'active' : ''} onClick={() => setMode('create')}>Créer</button>
          <button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>Connexion</button>
          <button type="button" className={mode === 'recover' ? 'active' : ''} onClick={() => setMode('recover')}>Récupérer</button>
        </div>
        <label htmlFor="account-email">E-mail</label>
        <input id="account-email" data-dialog-autofocus type="email" required value={email} autoComplete="email" onChange={event => setEmail(event.target.value)} />
        {mode === 'create' ? <p>Votre profil invité sera conservé. Un lien protégera le compte avant de choisir son mot de passe.</p> : null}
        {mode === 'login' ? <><label htmlFor="account-login-password">Mot de passe</label><input id="account-login-password" type="password" required minLength={10} maxLength={128} value={password} autoComplete="current-password" onChange={event => setPassword(event.target.value)} /></> : null}
        {mode === 'recover' ? <p>Nous enverrons un lien sécurisé pour choisir un nouveau mot de passe.</p> : null}
        {error ? <p className="mm-account-error" role="alert">{error}</p> : null}
        <button className="mm-save-guest" type="submit" disabled={busy || !email.trim() || mode === 'login' && password.length < 10}>{busy ? 'Patientez…' : mode === 'create' ? 'Protéger ce profil' : mode === 'login' ? 'Se connecter' : 'Envoyer le lien'}</button>
      </>}
    </form>
  </div>
}

export function MenuApp({ onStartSolo, onStartMatch }: MenuAppProps) {
  const [page, setPage] = useState<MenuPage>(() => {
    const hash = location.hash.slice(1)
    return hash === 'jouer' ? 'play' : hash === 'classement' ? 'ranking' : hash === 'profil' ? 'profile' : hash === 'epicerie' ? 'shop' : 'home'
  })
  const [quickMenu, setQuickMenu] = useState(false)
  const [settings, setSettings] = useState(false)
  const [legalOpen, setLegalOpen] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
  const [friendsOpen, setFriendsOpen] = useState(false)
  const [editingGuest, setEditingGuest] = useState(false)
  const [identity, setIdentity] = useState<GuestIdentity>(loadPlayerIdentity)
  const [progress, setProgress] = useState<PlayerProgress>(() => loadPlayerProgress(identity.playerId))
  const [cosmetics, setCosmetics] = useState<PlayerCosmetics>(() => loadPlayerCosmetics(identity.playerId))
  const [social, setSocial] = useState<SocialState>(EMPTY_SOCIAL_STATE)
  const [matchLobby, setMatchLobby] = useState<MatchLobbyState>(EMPTY_MATCH_LOBBY)
  const [matchBusy, setMatchBusy] = useState(false)
  const [pendingSearch, setPendingSearch] = useState<MatchPace | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem('motman-theme') as Theme | null) ?? 'light')
  const toastTimer = useRef<number | null>(null)
  const openingMatch = useRef<string | null>(null)

  useResolvedTheme(theme)

  useEffect(() => {
    const syncCosmetics = (event: Event) => {
      const next = (event as CustomEvent<PlayerCosmetics>).detail
      if (next?.playerId === identity.playerId) setCosmetics(next)
    }
    window.addEventListener('motman:cosmetics', syncCosmetics)
    return () => window.removeEventListener('motman:cosmetics', syncCosmetics)
  }, [identity.playerId])

  useEffect(() => () => {
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current)
  }, [])

  useEffect(() => {
    let active = true
    let syncing = false
    const sync = async (register: boolean) => {
      if (syncing) return
      syncing = true
      try {
        const next = register ? await registerSocialProfile(identity, { avatarId: cosmetics.equippedAvatarId, frameId: cosmetics.equippedFrameId, animationId: cosmetics.equippedAnimationId }) : await loadSocialState(identity.playerId)
        if (active) setSocial(current => sameState(current, next) ? current : next)
      } catch {
        // Le jeu reste utilisable si le serveur social local est arrêté.
      } finally { syncing = false }
    }
    void sync(true)
    const stopPolling = startAdaptivePolling({
      task: () => sync(false),
      delay: visibility => visibility === 'hidden' ? 20_000 : 5_000,
      immediate: false,
    })
    return () => { active = false; stopPolling() }
  }, [identity.playerId, identity.displayName, cosmetics.equippedAvatarId, cosmetics.equippedFrameId, cosmetics.equippedAnimationId])

  useEffect(() => {
    let active = true
    let syncing = false
    const sync = async () => {
      if (syncing) return
      syncing = true
      try {
        const next = await loadMatchLobby(identity.playerId)
        if (!active) return
        setMatchLobby(current => sameState(current, next) ? current : next)
        const liveMatch = next.active.find(match => match.pace === 'realtime')
        if (liveMatch && openingMatch.current !== liveMatch.id) {
          openingMatch.current = liveMatch.id
          onStartMatch(liveMatch.id)
        }
        else if (pendingSearch && !next.searches.some(search => search.pace === pendingSearch)) {
          const matched = next.active.find(match => match.mode === 'normal' && match.pace === pendingSearch)
          if (matched && openingMatch.current !== matched.id) {
            openingMatch.current = matched.id
            onStartMatch(matched.id)
          }
          setPendingSearch(null)
        }
      } catch {
        // Le menu reste disponible si le service de partie local est momentanément arrêté.
      } finally { syncing = false }
    }
    const stopPolling = startAdaptivePolling({
      task: sync,
      delay: visibility => visibility === 'hidden' ? pendingSearch ? 5_000 : 15_000 : pendingSearch ? 900 : 2_500,
    })
    return () => { active = false; stopPolling() }
  }, [identity.playerId, onStartMatch, pendingSearch])

  const notify = useCallback((message: string) => {
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current)
    setToast(message)
    toastTimer.current = window.setTimeout(() => {
      setToast(null)
      toastTimer.current = null
    }, 2350)
  }, [])

  useEffect(() => subscribePasswordRecovery(() => {
    if (!consumePasswordRecovery()) return
    setAccountOpen(true)
    notify('Choisissez maintenant votre nouveau mot de passe')
  }), [notify])

  const soon = () => {
    notify('Bientôt dispo')
  }

  const navigate = (nextPage: MenuPage) => {
    setPage(nextPage)
    const hash = nextPage === 'home' ? 'accueil' : nextPage === 'play' ? 'jouer' : nextPage === 'ranking' ? 'classement' : nextPage === 'shop' ? 'epicerie' : 'profil'
    history.replaceState(null, '', `#${hash}`)
  }

  const saveGuestProfile = async (displayName: string, avatarId: string, frameId: string, animationId: string, titleId: string | null) => {
    const response = await updateServerProfile(displayName, avatarId, frameId, animationId, titleId)
    setIdentity(response.identity)
    if (response.progress) setProgress(response.progress)
    if (response.cosmetics) setCosmetics(response.cosmetics)
    setEditingGuest(false)
    notify('Profil enregistré')
  }

  const applyAuthenticatedState = (response: AuthResponse) => {
    setIdentity(response.identity)
    setProgress(response.progress ?? loadPlayerProgress(response.identity.playerId))
    setCosmetics(response.cosmetics ?? loadPlayerCosmetics(response.identity.playerId))
    setSocial(EMPTY_SOCIAL_STATE)
    setMatchLobby(EMPTY_MATCH_LOBBY)
  }

  const inviteFriend = async (friendId: string, pace: MatchPace) => {
    try {
      const next = await createInstantMatch(identity.playerId, friendId, pace)
      setMatchLobby(next)
      if (pace === 'async') notify('Invitation envoyée · Vous pouvez continuer')
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : 'Invitation impossible')
    }
  }

  const cancelInvitation = async (invitationId: string) => {
    setMatchBusy(true)
    try { setMatchLobby(await cancelMatchInvitation(identity.playerId, invitationId)) }
    catch (reason) { notify(reason instanceof Error ? reason.message : 'Annulation impossible') }
    finally { setMatchBusy(false) }
  }

  const beginNormalSearch = async (pace: MatchPace) => {
    setPendingSearch(pace)
    try {
      const result = await searchNormalMatch(identity.playerId, pace)
      setMatchLobby(result.lobby)
      if (result.matchId) {
        setPendingSearch(null)
        openingMatch.current = result.matchId
        onStartMatch(result.matchId)
      } else notify(pace === 'realtime' ? 'Recherche lancée' : 'Recherche en temps illimité enregistrée')
    } catch (reason) {
      setPendingSearch(null)
      notify(reason instanceof Error ? reason.message : 'Recherche impossible')
    }
  }

  const stopNormalSearch = async (pace: MatchPace) => {
    setMatchBusy(true)
    try {
      setMatchLobby(await cancelNormalSearch(identity.playerId, pace))
      if (pendingSearch === pace) setPendingSearch(null)
      notify('Recherche annulée')
    } catch (reason) { notify(reason instanceof Error ? reason.message : 'Annulation impossible') }
    finally { setMatchBusy(false) }
  }

  const answerInvitation = async (invitationId: string, decision: 'accept' | 'decline') => {
    setMatchBusy(true)
    try {
      const next = await respondToMatchInvitation(identity.playerId, invitationId, decision)
      setMatchLobby(next)
      const acceptedMatch = next.active.find(match => match.invitationId === invitationId)
      if (acceptedMatch) {
        openingMatch.current = acceptedMatch.id
        onStartMatch(acceptedMatch.id)
      }
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : 'Cette invitation n’est plus disponible')
    } finally { setMatchBusy(false) }
  }

  const outgoingInvitation = matchLobby.outgoing[0]
  const realtimeSearch = matchLobby.searches.some(search => search.pace === 'realtime')

  return <main className="mm-shell">
    <AppHeader onMenu={() => setQuickMenu(true)} onSettings={() => setSettings(true)} />
    {page === 'home' ? <HomePage identity={identity} progress={progress} cosmetics={cosmetics} social={social} lobby={matchLobby} play={() => navigate('play')} openFriends={() => setFriendsOpen(true)} resumeMatch={onStartMatch} /> : null}
    {page === 'play' ? <PlayPage identity={identity} onStartSolo={onStartSolo} soon={soon} social={social} lobby={matchLobby} invite={inviteFriend} cancelInvite={cancelInvitation} searchMatch={beginNormalSearch} cancelSearch={stopNormalSearch} resumeMatch={onStartMatch} openFriends={() => setFriendsOpen(true)} /> : null}
    {page === 'ranking' ? <RankingPage identity={identity} progress={progress} cosmetics={cosmetics} /> : null}
    {page === 'profile' ? <ProfilePage identity={identity} progress={progress} cosmetics={cosmetics} edit={() => setEditingGuest(true)} openShop={() => navigate('shop')} openAccount={() => setAccountOpen(true)} /> : null}
    {page === 'shop' ? <Suspense fallback={<div className="mm-page mm-shop-page mm-route-loading" role="status">Ouverture de L’Épicerie…</div>}><LazyShopPage cosmetics={cosmetics} setCosmetics={setCosmetics} back={() => navigate('profile')} notify={notify} /></Suspense> : null}
    <BottomNav page={page} setPage={navigate} />
    {quickMenu ? <QuickMenu page={page} navigate={navigate} close={() => setQuickMenu(false)} /> : null}
    {settings ? <SettingsPanel identity={identity} close={() => setSettings(false)} openAccount={() => { setSettings(false); setAccountOpen(true) }} openFriends={() => { setSettings(false); setFriendsOpen(true) }} openLegal={() => { setSettings(false); setLegalOpen(true) }} theme={theme} setTheme={setTheme} /> : null}
    {legalOpen ? <Suspense fallback={null}><LazyLegalPanel close={() => setLegalOpen(false)} /></Suspense> : null}
    {accountOpen ? <AccountPanel identity={identity} close={() => setAccountOpen(false)} apply={applyAuthenticatedState} notify={notify} /> : null}
    {friendsOpen ? <FriendsPanel identity={identity} social={social} setSocial={setSocial} close={() => setFriendsOpen(false)} notify={notify} /> : null}
    {editingGuest ? <EditGuestPanel identity={identity} progress={progress} cosmetics={cosmetics} close={() => setEditingGuest(false)} save={saveGuestProfile} /> : null}
    {matchLobby.incoming[0] ? <MatchInvitationPanel invitation={matchLobby.incoming[0]} busy={matchBusy} accept={() => void answerInvitation(matchLobby.incoming[0].id, 'accept')} decline={() => void answerInvitation(matchLobby.incoming[0].id, 'decline')} /> : null}
    {outgoingInvitation || realtimeSearch ? <div className="mm-live-activities">
      {outgoingInvitation ? <MatchWaitingPanel invitation={outgoingInvitation} busy={matchBusy} cancel={() => void cancelInvitation(outgoingInvitation.id)} /> : null}
      {realtimeSearch ? <NormalSearchPanel busy={matchBusy} cancel={() => void stopNormalSearch('realtime')} /> : null}
    </div> : null}
    {toast ? <div className="mm-toast" role="status">{toast}</div> : null}
  </main>
}
