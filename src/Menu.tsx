import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import './menu.css'
import {
  clearGoogleAuthIssue, consumePasswordRecovery, currentGoogleAuthIssue, subscribePasswordRecovery, updateServerProfile, type AuthResponse,
} from './auth'
import type { GoogleAuthIssue } from './googleAuthCallback'
import { startAdaptivePolling } from './adaptivePolling'
import { loadPlayerCosmetics, type PlayerCosmetics } from './cosmetics'
import {
  cancelMatchInvitation, cancelNormalSearch, createInstantMatch, EMPTY_MATCH_LOBBY, loadMatchLobby,
  respondToMatchInvitation, searchNormalMatch, type MatchLobbyState, type MatchPace,
} from './matches'
import { loadPlayerIdentity, type GuestIdentity } from './playerIdentity'
import { loadPlayerProgress, type PlayerProgress } from './playerProgress'
import { EMPTY_SOCIAL_STATE, loadSocialState, registerSocialProfile, type SocialState } from './social'
import { AccountPanel } from './menu/AccountPanel'
import { AppHeader, BottomNav } from './menu/MenuChrome'
import { FriendsPanel } from './menu/FriendsPanel'
import { HomePage } from './menu/HomePage'
import { MatchInvitationPanel, MatchWaitingPanel, NormalSearchPanel } from './menu/MatchActivityPanels'
import { PlayPage } from './menu/PlayPage'
import { EditGuestPanel, ProfilePage, QuickMenu, RankingPage } from './menu/ProfilePanels'
import { SettingsPanel } from './menu/SettingsPanel'
import type { MenuAppProps, MenuPage, Theme } from './menu/types'

export type { MenuPage } from './menu/types'

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

export function MenuApp({ onStartSolo, onStartMatch }: MenuAppProps) {
  const [page, setPage] = useState<MenuPage>(() => {
    const hash = location.hash.slice(1)
    return hash === 'jouer' ? 'play' : hash === 'classement' ? 'ranking' : hash === 'profil' ? 'profile' : hash === 'epicerie' ? 'shop' : 'home'
  })
  const [quickMenu, setQuickMenu] = useState(false)
  const [settings, setSettings] = useState(false)
  const [legalOpen, setLegalOpen] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
  const [googleAuthIssue, setGoogleAuthIssue] = useState<GoogleAuthIssue | null>(currentGoogleAuthIssue)
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

  useEffect(() => {
    const syncIdentity = (event: Event) => {
      const next = (event as CustomEvent<GuestIdentity>).detail
      if (!next?.playerId) return
      setIdentity(next)
      setProgress(loadPlayerProgress(next.playerId))
      setCosmetics(loadPlayerCosmetics(next.playerId))
    }
    window.addEventListener('motman:identity', syncIdentity)
    return () => window.removeEventListener('motman:identity', syncIdentity)
  }, [])

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
    const polling = startAdaptivePolling({
      task: () => sync(false),
      delay: visibility => visibility === 'hidden' ? 20_000 : 5_000,
      immediate: false,
    })
    return () => { active = false; polling.stop() }
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
    const polling = startAdaptivePolling({
      task: sync,
      delay: visibility => visibility === 'hidden' ? pendingSearch ? 5_000 : 15_000 : pendingSearch ? 900 : 2_500,
    })
    return () => { active = false; polling.stop() }
  }, [identity.playerId, onStartMatch, pendingSearch])

  const notify = useCallback((message: string) => {
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current)
    setToast(message)
    toastTimer.current = window.setTimeout(() => {
      setToast(null)
      toastTimer.current = null
    }, 2350)
  }, [])

  useEffect(() => {
    if (!googleAuthIssue) return
    setAccountOpen(true)
    notify(googleAuthIssue.message)
  }, [googleAuthIssue, notify])

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
    {accountOpen ? <AccountPanel identity={identity} close={() => setAccountOpen(false)} apply={applyAuthenticatedState} notify={notify} googleAuthIssue={googleAuthIssue} dismissGoogleAuthIssue={() => { clearGoogleAuthIssue(); setGoogleAuthIssue(null) }} /> : null}
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
