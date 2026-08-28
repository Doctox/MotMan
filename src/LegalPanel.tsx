import { useState } from 'react'
import { BookOpen, FileText, Scale, ShieldCheck, X } from 'lucide-react'
import { useDialogFocus } from './useDialogFocus'
import { assetUrl } from './assetUrl'

type LegalTab = 'privacy' | 'terms' | 'credits'

export function LegalPanel({ close }: { close: () => void }) {
  const [tab, setTab] = useState<LegalTab>('privacy')
  const dialogRef = useDialogFocus<HTMLElement>(close)
  return <div className="mm-modal-layer mm-legal-layer" role="presentation" onMouseDown={event => event.target === event.currentTarget && close()}>
    <section ref={dialogRef} className="mm-legal-panel" role="dialog" aria-modal="true" aria-label="Informations légales" tabIndex={-1}>
      <header><div><small>MotMan · version bêta</small><h2>Informations</h2></div><button type="button" onClick={close} aria-label="Fermer"><X /></button></header>
      <div className="mm-legal-tabs" role="tablist" aria-label="Documents légaux">
        <button type="button" role="tab" aria-selected={tab === 'privacy'} className={tab === 'privacy' ? 'active' : ''} onClick={() => setTab('privacy')}><ShieldCheck />Confidentialité</button>
        <button type="button" role="tab" aria-selected={tab === 'terms'} className={tab === 'terms' ? 'active' : ''} onClick={() => setTab('terms')}><Scale />Conditions</button>
        <button type="button" role="tab" aria-selected={tab === 'credits'} className={tab === 'credits' ? 'active' : ''} onClick={() => setTab('credits')}><BookOpen />Crédits</button>
      </div>
      <div className="mm-legal-scroll">
        {tab === 'privacy' ? <article>
          <h3>Politique de confidentialité</h3><p className="mm-legal-version">Version du 17 août 2026</p>
          <h4>Données utilisées</h4><p>MotMan traite les informations nécessaires au compte et au jeu : adresse e-mail lorsque vous créez un compte, pseudo, apparence du profil, progression, collection, parties, scores, amis, avis de grille, éventuels signalements et jeton technique de notification si vous les autorisez. En cas de plantage, un rapport technique est aussi transmis : modèle de l’appareil, version du système, identifiant technique et trace de l’erreur. Il ne contient ni le contenu de vos parties, ni vos messages.</p>
          <h4>Pourquoi</h4><p>Ces données servent à authentifier les joueurs, synchroniser leur progression, organiser les parties, prévenir les abus, répondre aux signalements, diagnostiquer les pannes et améliorer la qualité des grilles.</p>
          <h4>Stockage et partage</h4><p>Les données en ligne sont hébergées par Supabase, dans un centre de données situé en France. Cloudflare Turnstile protège la création des comptes invités contre les robots et les abus. Firebase Cloud Messaging, service de Google, achemine les notifications de tours et d’invitations vers les appareils qui les autorisent. Firebase Crashlytics, également de Google, reçoit les rapports de plantage. La connexion facultative par compte Google s’appuie sur Google Sign-In. L’appareil conserve aussi un cache local pour les préférences et la continuité de jeu. MotMan ne vend pas les données, n’affiche aucune publicité et ne transmet pas les profils à des annonceurs.</p>
          <h4>Durée et droits</h4><p>Les informations sont conservées pendant la durée nécessaire au fonctionnement du compte, à la sécurité et aux obligations applicables. Les comptes invités non liés et inactifs depuis 30 jours sont supprimés automatiquement. Vous pouvez supprimer immédiatement votre compte depuis Paramètres → Compte, ou demander sa suppression hors de l’application.</p>
          <a className="mm-legal-document" href={assetUrl('/legal/suppression-compte.html')} target="_blank" rel="noreferrer"><FileText />Supprimer un compte MotMan</a>
          <h4>Responsable</h4><p>Le responsable du traitement est Jean-Marie PEETERS, éditeur indépendant de MotMan. Contact : <a href="mailto:contact@doctox.fr">contact@doctox.fr</a>.</p>
          <h4>Jeunes joueurs</h4><p>MotMan s’adresse aux joueurs de 16 ans et plus et n’est pas destiné aux enfants. Aucun contenu ni service n’y est proposé à destination des mineurs de moins de 16 ans.</p>
        </article> : null}
        {tab === 'terms' ? <article>
          <h3>Conditions d’utilisation</h3><p className="mm-legal-version">Version bêta du 18 juillet 2026</p>
          <h4>Le service</h4><p>MotMan est un jeu de mots fléchés solo et multijoueur actuellement en développement. Des interruptions, ajustements de règles ou réinitialisations exceptionnelles peuvent survenir pendant la phase de test.</p>
          <h4>Public et compte</h4><p>MotMan s’adresse aux joueurs de 16 ans et plus et n’est pas destiné aux enfants. Chaque joueur doit protéger son compte et choisir un pseudo approprié.</p>
          <h4>Comportement</h4><p>Le harcèlement, les contenus haineux, sexuels ou discriminatoires, la triche et l’exploitation volontaire de bugs peuvent entraîner une restriction ou une suppression du compte.</p>
          <h4>Objets virtuels</h4><p>Les plumes, avatars, cadres, animations et titres sont des éléments virtuels du jeu. Ils n’ont aucune valeur monétaire, ne sont pas échangeables contre de l’argent et peuvent être rééquilibrés pour préserver l’expérience de jeu.</p>
          <h4>Propriété intellectuelle</h4><p>La direction artistique, le code, les textes originaux et l’organisation du jeu appartiennent à leurs titulaires respectifs. Les ressources tierces restent soumises aux licences indiquées dans les crédits.</p>
          <h4>Disponibilité et contact</h4><p>MotMan cherche à fournir un service fiable, mais aucune disponibilité permanente n’est garantie pendant la bêta. Éditeur : Jean-Marie PEETERS, indépendant. Contact : <a href="mailto:contact@doctox.fr">contact@doctox.fr</a>.</p>
        </article> : null}
        {tab === 'credits' ? <article>
          <h3>Crédits et licences</h3>
          <h4>Création</h4><p>Concept, direction artistique, sélection éditoriale et développement : Jean-Marie PEETERS, projet indépendant MotMan.</p>
          <h4>Typographies</h4><p>DM Sans et Playfair Display sont auto-hébergées et distribuées sous licence SIL Open Font License 1.1. Les textes complets des licences sont inclus avec l’application.</p>
          <h4>Illustrations d’indices</h4><p>Une partie des pictogrammes provient de Twemoji, sous licence CC BY 4.0. Les crédits détaillés restent associés aux indices concernés dans le catalogue éditorial.</p>
          <h4>Ressources lexicales</h4><p>Le travail éditorial s’appuie notamment sur Lexique, des ressources lexicales ouvertes et des références de mots fléchés citées dans le corpus de recherche. Les définitions publiées sont relues ou réécrites pour MotMan.</p>
          <h4>Logiciels libres</h4><p>MotMan utilise notamment React, Vite, Lucide, Supabase et Capacitor selon leurs licences respectives. Les fichiers de licence des polices et les attributions des images sont conservés dans le paquet de l’application.</p>
          <a className="mm-legal-document" href={assetUrl('/legal/credits.html')} target="_blank" rel="noreferrer"><FileText />Ouvrir la version détaillée</a>
        </article> : null}
      </div>
    </section>
  </div>
}
