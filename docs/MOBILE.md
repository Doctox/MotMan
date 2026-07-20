# MotMan sur Android et iOS

MotMan utilise Capacitor 7 avec l’identifiant provisoire `com.motman.game`.
Les projets natifs sont conservés dans `android/` et `ios/` ; le jeu React reste
la source unique de l’interface et des règles.

## Commandes

- `npm run mobile:sync` construit le Web puis synchronise Android et iOS.
- `npm run mobile:android` ouvre le projet Android après synchronisation.
- `npm run mobile:ios` ouvre le projet iOS après synchronisation.
- `npm run mobile:doctor` contrôle les prérequis locaux.

## Authentification

Google, la confirmation d’e-mail et la récupération de compte reviennent vers
`com.motman.game://auth/callback`. Cette adresse doit être ajoutée aux URL de
redirection autorisées dans Supabase avant un test natif de l’authentification.
Le code utilise PKCE et ouvre le fournisseur dans le navigateur système.

## Notifications de tours et d'invitations

Le client natif utilise Firebase Cloud Messaging via Capacitor. Les notifications
ouvrent directement la partie concernée, ou la page Jouer lorsqu'une invitation
n'a pas encore créé de partie. Le serveur envoie trois événements : nouveau tour
en temps illimité, invitation d'un ami et invitation acceptée.

Configuration Android à effectuer une seule fois :

1. Ajouter l'application Android `com.motman.game` au projet Firebase MotMan.
2. Placer le fichier téléchargé `google-services.json` dans `android/app/`.
3. Générer une clé de compte de service Firebase dans un dossier extérieur au
   dépôt. Ne jamais ajouter cette clé à Git.
4. Charger son contenu JSON dans le secret Supabase
   `FIREBASE_SERVICE_ACCOUNT_JSON`, puis redéployer `match-api`.
5. Installer une nouvelle version de l'application et accepter la permission de
   notification lors du premier lancement.

Pour iOS, activer ultérieurement Push Notifications et Background Modes dans
Xcode, puis relier une clé APNs au projet Firebase.

## Prérequis de compilation

- Android : Android Studio, SDK Android 36 et JDK 21.
- iOS : macOS, Xcode et CocoaPods.

La machine Windows de développement utilise le JDK 21 d'Android Studio. Gradle
peut installer automatiquement le SDK Android 36 si sa licence est acceptée.
Le projet iOS peut être synchronisé sous Windows mais doit être
compilé et signé sur un Mac.

## Avant publication

1. Remplacer l’identifiant provisoire si le nom de domaine final impose un autre
   identifiant, avant toute signature de production.
2. Les icônes et le splash sont générés avec `npm run mobile:assets`. Produire
   les captures de boutique sur la version candidate.
3. Renseigner l’identité légale et le contact de l’éditeur dans les documents.
4. Tester Google, e-mail, liens profonds et récupération sur les deux plateformes.
5. Dans Google Play Console, renseigner comme URL de suppression du compte :
   `https://doctox.github.io/MotMan/legal/suppression-compte.html`.
6. Vérifier la suppression depuis Paramètres → Compte avec un compte de test :
   progression, collection, amis, parties et sessions doivent disparaître.
7. Créer les certificats, profils de signature et fiches Play Store/App Store.

La procédure complète Google Play, les variables de signature et les réponses à
préparer dans la Console sont documentées dans `docs/GOOGLE_PLAY.md`.
