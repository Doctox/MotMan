import React from 'react'
import ReactDOM from 'react-dom/client'
import './base.css'
import { isNativeRuntime } from './nativeRuntime'

if (isNativeRuntime()) {
  void import('./nativeAuthBridge').then(module => module.initializeNativeAuthBridge())
}

const root = ReactDOM.createRoot(document.getElementById('root')!)
root.render(<main className="app-loading" role="status"><span>Ouverture de MotMan…</span></main>)

void Promise.all([import('./auth'), import('./App')]).then(async ([auth, app]) => {
  await auth.bootstrapPlayerSession()
  const App = app.App
  root.render(<React.StrictMode><App /></React.StrictMode>)
}).catch(reason => {
  const message = reason instanceof Error ? reason.message : 'Connexion à MotMan impossible.'
  root.render(<main className="app-loading app-loading-error" role="alert"><strong>MotMan est momentanément indisponible</strong><span>{message}</span><button type="button" onClick={() => location.reload()}>Réessayer</button></main>)
})
