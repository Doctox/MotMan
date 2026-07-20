import { useState, type ReactNode } from 'react'
import { BarChart3, ChevronRight, Feather, Gamepad2, Home, Pencil, Shield, ShoppingBasket, Trophy, User, X } from 'lucide-react'
import { CosmeticPortrait } from '../CosmeticPortrait'
import { getAnimation, getAvatar, getFrame, type PlayerCosmetics } from '../cosmetics'
import { PLAYER_NAME_MAX_LENGTH, validatePlayerName } from '../playerNamePolicy'
import { shortPlayerId, type GuestIdentity } from '../playerIdentity'
import { experienceGoalForLevel, MAX_PLAYER_LEVEL, type PlayerProgress } from '../playerProgress'
import { useDialogFocus } from '../useDialogFocus'
import { RankProgress } from './MenuChrome'
import type { MenuPage } from './types'

const frenchNumber = new Intl.NumberFormat('fr-FR')

export function RankingPage({ identity, progress, cosmetics }: { identity: GuestIdentity; progress: PlayerProgress; cosmetics: PlayerCosmetics }) {
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

export function ProfilePage({ identity, progress, cosmetics, edit, openShop, openAccount }: { identity: GuestIdentity; progress: PlayerProgress; cosmetics: PlayerCosmetics; edit: () => void; openShop: () => void; openAccount: () => void }) {
  const xpGoal = experienceGoalForLevel(progress.level)
  const xpPercent = progress.level >= MAX_PLAYER_LEVEL ? 100 : Math.min(100, progress.xp / xpGoal * 100)
  const equippedTitle = progress.titles.find(title => title.id === progress.equippedTitleId)
  return <div className="mm-page mm-profile-page">
    <section className="mm-profile-hero"><CosmeticPortrait avatarId={cosmetics.equippedAvatarId} frameId={cosmetics.equippedFrameId} animationId={cosmetics.equippedAnimationId} alt="Votre avatar" /><div><h1>{identity.displayName}</h1>{equippedTitle ? <small className="mm-equipped-title">{equippedTitle.name}</small> : null}<button type="button" onClick={edit}><Pencil />Modifier</button></div></section>
    <section className="mm-level"><div><BarChart3 /><strong>Niveau {progress.level}</strong><span>{progress.level >= MAX_PLAYER_LEVEL ? 'Niveau maximum' : `Niveau ${progress.level + 1}`}</span></div><i className="guest-progress"><b style={{ width: `${xpPercent}%` }} /></i><p>{progress.level >= MAX_PLAYER_LEVEL ? <strong>Niveau maximum atteint</strong> : <><strong>{progress.xp}</strong> / {xpGoal} XP</>}</p></section>
    <button type="button" className="mm-grocery-entry" onClick={openShop}>
      <span className="mm-grocery-basket"><ShoppingBasket /></span>
      <span><small>Collection & trouvailles</small><strong>L’Épicerie</strong></span>
      <b><Feather />{frenchNumber.format(cosmetics.plumes)}</b><ChevronRight />
    </button>
    <section className="mm-stats"><div><Trophy /><strong>{progress.wins}</strong><span>Victoires</span></div><i /><div><Shield /><strong>{progress.losses}</strong><span>Défaites</span></div></section>
    <button type="button" className="mm-account" onClick={openAccount}><User /><span><strong>{identity.accountType === 'account' ? 'Compte synchronisé' : 'Compte invité'}</strong><small>Code ami {identity.friendCode ?? shortPlayerId(identity.playerId)}</small></span><b>{identity.accountType === 'account' ? 'Gérer' : 'Créer un compte'}</b><ChevronRight /></button>
  </div>
}

export function QuickMenu({ page, navigate, close }: { page: MenuPage; navigate: (page: MenuPage) => void; close: () => void }) {
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

export function EditGuestPanel({ identity, progress, cosmetics, close, save }: {
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
      <input id="guest-display-name" value={displayName} maxLength={PLAYER_NAME_MAX_LENGTH} autoComplete="nickname" aria-invalid={!nameValidation.valid} aria-describedby="guest-display-name-help" onChange={event => setDisplayName(event.target.value)} />
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

