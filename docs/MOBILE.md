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

## Prérequis de compilation

- Android : Android Studio, SDK Android 35 et JDK 21.
- iOS : macOS, Xcode et CocoaPods.

La machine Windows de développement possède le SDK Android 35, mais son Android
Studio actuel embarque encore Java 17. Installer un JDK 21 ou mettre Android
Studio à jour suffit pour produire l’APK. Le projet iOS peut être synchronisé
sous Windows mais doit être compilé et signé sur un Mac.

## Avant publication

1. Remplacer l’identifiant provisoire si le nom de domaine final impose un autre
   identifiant, avant toute signature de production.
2. Générer les icônes, le splash screen et les captures de boutique définitifs.
3. Renseigner l’identité légale et le contact de l’éditeur dans les documents.
4. Tester Google, e-mail, liens profonds et récupération sur les deux plateformes.
5. Dans Google Play Console, renseigner comme URL de suppression du compte :
   `https://doctox.github.io/MotMan/legal/suppression-compte.html`.
6. Vérifier la suppression depuis Paramètres → Compte avec un compte de test :
   progression, collection, amis, parties et sessions doivent disparaître.
7. Créer les certificats, profils de signature et fiches Play Store/App Store.
