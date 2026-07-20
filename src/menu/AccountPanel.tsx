import { useState, type FormEvent } from 'react'
import { AlertTriangle, Trash2, User, X } from 'lucide-react'
import { assetUrl } from '../assetUrl'
import {
  authenticateWithGoogle, createPlayerAccount, deletePlayerAccount, finishPlayerAccount,
  loginPlayerAccount, logoutPlayerAccount, recoverPlayerAccount, type AuthResponse,
} from '../auth'
import type { GuestIdentity } from '../playerIdentity'
import { loadPlayerCosmetics } from '../cosmetics'
import { loadPlayerProgress } from '../playerProgress'
import { useDialogFocus } from '../useDialogFocus'

type AccountMode = 'create' | 'login' | 'recover'

export function AccountPanel({ identity, close, apply, notify }: {
  identity: GuestIdentity
  close: () => void
  apply: (response: AuthResponse) => void
  notify: (message: string) => void
}) {
  const [mode, setMode] = useState<AccountMode>('create')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [deleteConfirming, setDeleteConfirming] = useState(false)
  const [deletePhrase, setDeletePhrase] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const dialogRef = useDialogFocus<HTMLFormElement>(close)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true); setError(null)
    try {
      if (deleteConfirming) {
        const response = await deletePlayerAccount(deletePhrase)
        apply(response)
        notify('Compte et données supprimés · nouveau profil invité')
        close()
        return
      }
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

  const beginDeletion = () => {
    setError(null)
    setDeletePhrase('')
    setDeleteConfirming(true)
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
      <header><div><small>{deleteConfirming ? 'Compte et données' : 'Progression sécurisée'}</small><h2>{deleteConfirming ? 'Supprimer le compte' : identity.accountType === 'account' ? 'Votre compte' : mode === 'create' ? 'Créer mon compte' : mode === 'login' ? 'Me connecter' : 'Retrouver mon compte'}</h2></div><button type="button" onClick={close} aria-label="Fermer"><X /></button></header>
      {deleteConfirming ? <>
        <div className="mm-account-delete-warning"><AlertTriangle /><div><strong>Cette action est définitive</strong><p>Le profil, la progression, les plumes, la collection, les amis et les parties associées seront supprimés.</p></div></div>
        <label htmlFor="account-delete-confirmation">Écrivez SUPPRIMER pour confirmer</label>
        <input id="account-delete-confirmation" value={deletePhrase} autoComplete="off" autoCapitalize="characters" spellCheck={false} onChange={event => setDeletePhrase(event.target.value.toUpperCase())} />
        {error ? <p className="mm-account-error" role="alert">{error}</p> : null}
        <button className="mm-account-delete-confirm" type="submit" disabled={busy || deletePhrase !== 'SUPPRIMER'}><Trash2 />{busy ? 'Suppression…' : 'Supprimer définitivement'}</button>
        <button className="mm-account-delete-cancel" type="button" disabled={busy} onClick={() => setDeleteConfirming(false)}>Annuler</button>
        <a className="mm-account-delete-help" href={assetUrl('/legal/suppression-compte.html')} target="_blank" rel="noreferrer">Demander la suppression hors de l’application</a>
      </> : <>
        <button className="mm-google-auth" type="button" disabled={busy} onClick={() => void google()}><span aria-hidden="true">G</span>{identity.accountType === 'account' ? 'Lier mon compte Google' : 'Continuer avec Google'}</button>
        <div className="mm-account-divider"><span>ou</span></div>
        {identity.accountType === 'account' ? <>
        <div className="mm-account-current"><User /><span><strong>{identity.displayName}</strong><small>Synchronisé sur Android, Apple et PC</small></span></div>
        <label htmlFor="account-password">Définir ou changer le mot de passe</label>
        <input id="account-password" type="password" minLength={10} maxLength={128} value={password} autoComplete="new-password" onChange={event => setPassword(event.target.value)} />
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
        <input id="account-email" type="email" required value={email} autoComplete="email" onChange={event => setEmail(event.target.value)} />
        {mode === 'create' ? <p>Votre profil invité sera conservé. Un lien protégera le compte avant de choisir son mot de passe.</p> : null}
        {mode === 'login' ? <><label htmlFor="account-login-password">Mot de passe</label><input id="account-login-password" type="password" required minLength={10} maxLength={128} value={password} autoComplete="current-password" onChange={event => setPassword(event.target.value)} /></> : null}
        {mode === 'recover' ? <p>Nous enverrons un lien sécurisé pour choisir un nouveau mot de passe.</p> : null}
        {error ? <p className="mm-account-error" role="alert">{error}</p> : null}
        <button className="mm-save-guest" type="submit" disabled={busy || !email.trim() || mode === 'login' && password.length < 10}>{busy ? 'Patientez…' : mode === 'create' ? 'Protéger ce profil' : mode === 'login' ? 'Se connecter' : 'Envoyer le lien'}</button>
        </>}
        <button className="mm-account-delete-entry" type="button" disabled={busy} onClick={beginDeletion}><Trash2 /><span>Supprimer {identity.accountType === 'account' ? 'mon compte' : 'ce profil invité'}</span></button>
      </>}
    </form>
  </div>
}
