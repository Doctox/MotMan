import { useState, type FormEvent } from 'react'
import { ArrowLeft, Ban, Check, Copy, Shield, UserMinus, UserPlus, Users, X } from 'lucide-react'
import { shortPlayerId, type GuestIdentity } from '../playerIdentity'
import { reportPlayer, respondToFriendRequest, sendFriendRequest, updateFriend, type SocialState, type SocialUser } from '../social'
import { useDialogFocus } from '../useDialogFocus'
import { SocialPortrait, presenceLabel } from './MenuChrome'

export function FriendsPanel({ identity, social, setSocial, close, notify }: {
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
