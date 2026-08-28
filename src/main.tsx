import React from 'react'
import ReactDOM from 'react-dom/client'
import './tokens.css'
import './base.css'
import { isNativeRuntime } from './nativeRuntime'
import { initializeSensoryPreferences } from './sensoryPreferences'

initializeSensoryPreferences()

const nativeRuntime = isNativeRuntime()
document.documentElement.classList.toggle('native-runtime', nativeRuntime)

if (nativeRuntime) {
  void import('./nativeAuthBridge').then(module => module.initializeNativeAuthBridge())
}

const root = ReactDOM.createRoot(document.getElementById('root')!)

// L'ouverture dépend du réseau : chargement des modules, vérification de version,
// puis bootstrap de la session. Le 28/08/2026, une panne serveur a rendu la
// dernière étape muette et l'écran est resté figé sur « Ouverture de MotMan… »
// sans barre, sans message, sans issue. Un joueur dans une zone mal couverte
// vivrait exactement la même chose sans qu'aucun serveur ne soit en panne.
//
// On rend donc l'attente lisible : une barre qui bouge dès la première seconde,
// puis, au bout de OUVERTURE_LENTE_MS, l'aveu que c'est anormal et un bouton
// pour reprendre la main. On ne coupe pas l'ouverture pour autant : si le
// serveur répond à la douzième seconde, la partie se lance normalement.
const OUVERTURE_LENTE_MS = 7_000

function renderOuverture(lente: boolean) {
  root.render(
    <main className="app-loading" role="status" aria-live="polite">
      <span>Ouverture de MotMan…</span>
      <div className="app-loading-bar" aria-hidden="true"><i /></div>
      {lente ? <>
        <small>Le serveur met plus de temps que d’habitude.</small>
        <button type="button" onClick={() => location.reload()}>Réessayer</button>
      </> : null}
    </main>,
  )
}

renderOuverture(false)
let avisLenteur: ReturnType<typeof setTimeout> | undefined = setTimeout(() => renderOuverture(true), OUVERTURE_LENTE_MS)

function ouvertureTerminee() {
  if (avisLenteur !== undefined) clearTimeout(avisLenteur)
  avisLenteur = undefined
}

void Promise.all([import('./auth'), import('./App'), import('./appUpdate')]).then(async ([auth, app, update]) => {
  const requiredUpdate = await update.checkRequiredAppUpdate().catch(() => null)
  if (requiredUpdate) {
    ouvertureTerminee()
    const RequiredAppUpdate = (await import('./RequiredAppUpdate')).RequiredAppUpdateScreen
    root.render(<RequiredAppUpdate update={requiredUpdate} />)
    return
  }
  await auth.bootstrapPlayerSession()
  ouvertureTerminee()
  const App = app.App
  root.render(<React.StrictMode><App initialRequiredUpdate={requiredUpdate} /></React.StrictMode>)
  if (nativeRuntime) {
    void import('./nativePushNotifications')
      .then(module => module.initializeNativePushNotifications())
      .catch(error => console.error('Initialisation des notifications impossible', error))
  }
}).catch(reason => {
  ouvertureTerminee()
  const message = reason instanceof Error ? reason.message : 'Connexion à MotMan impossible.'
  root.render(<main className="app-loading app-loading-error" role="alert"><strong>MotMan est momentanément indisponible</strong><span>{message}</span><button type="button" onClick={() => location.reload()}>Réessayer</button></main>)
})
