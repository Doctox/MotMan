import { Download } from 'lucide-react'
import type { RequiredAppUpdate } from './appUpdate'

export function RequiredAppUpdateScreen({ update }: { update: RequiredAppUpdate }) {
  return <main className="app-update-required" role="alert" aria-labelledby="app-update-title">
    <div className="app-update-card">
      <span className="app-update-icon" aria-hidden="true"><Download /></span>
      <p className="app-update-kicker">Nouvelle version disponible</p>
      <h1 id="app-update-title">MotMan doit être mis à jour</h1>
      <p>
        Cette version n’est plus compatible avec les parties en ligne.
        Mettez l’application à jour pour continuer à jouer.
      </p>
      <a href={update.storeUrl} target="_blank" rel="noreferrer">
        Mettre à jour sur Google Play
      </a>
      <small>Version requise : {update.latestVersionName}</small>
    </div>
  </main>
}
