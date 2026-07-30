import React from 'react'
import ReactDOM from 'react-dom/client'
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
root.render(<main className="app-loading" role="status"><span>Ouverture de MotMan…</span></main>)

void Promise.all([import('./auth'), import('./App'), import('./appUpdate')]).then(async ([auth, app, update]) => {
  const requiredUpdate = await update.checkRequiredAppUpdate().catch(() => null)
  if (requiredUpdate) {
    const RequiredAppUpdate = (await import('./RequiredAppUpdate')).RequiredAppUpdateScreen
    root.render(<RequiredAppUpdate update={requiredUpdate} />)
    return
  }
  await auth.bootstrapPlayerSession()
  const App = app.App
  root.render(<React.StrictMode><App initialRequiredUpdate={requiredUpdate} /></React.StrictMode>)
  if (nativeRuntime) {
    void import('./nativePushNotifications')
      .then(module => module.initializeNativePushNotifications())
      .catch(error => console.error('Initialisation des notifications impossible', error))
  }
}).catch(reason => {
  const message = reason instanceof Error ? reason.message : 'Connexion à MotMan impossible.'
  root.render(<main className="app-loading app-loading-error" role="alert"><strong>MotMan est momentanément indisponible</strong><span>{message}</span><button type="button" onClick={() => location.reload()}>Réessayer</button></main>)
})
