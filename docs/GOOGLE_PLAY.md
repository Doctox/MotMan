# Préparation Google Play de MotMan

## État technique

- Identifiant Android : `com.motman.game`.
- `compileSdk` et `targetSdk` : API 36.
- Format de publication : Android App Bundle (`.aab`).
- Sauvegarde Android désactivée : le compte Supabase reste la source de vérité
  pour la progression et les achats.
- Suppression du compte disponible dans l'application et publiquement sur
  `https://doctox.github.io/MotMan/legal/suppression-compte.html`.
- Confidentialité publique :
  `https://doctox.github.io/MotMan/legal/confidentialite.html`.
- Icône adaptative, icône monochrome Android 13 et splash MotMan présents.

## Construire le bundle

Créer une clé d'upload dans Android Studio ou avec `keytool`, puis conserver le
fichier hors du dépôt. Exposer uniquement pendant la compilation :

```powershell
$env:MOTMAN_KEYSTORE_PATH='C:\chemin\motman-upload.jks'
$env:MOTMAN_KEYSTORE_PASSWORD='...'
$env:MOTMAN_KEY_ALIAS='motman-upload'
$env:MOTMAN_KEY_PASSWORD='...'
npm run mobile:aab
```

Le bundle est produit sous
`android/app/build/outputs/bundle/release/app-release.aab`. L'inscription à
Play App Signing se fait ensuite dans la Play Console lors du premier envoi.
Ne jamais commiter le keystore ou ses mots de passe.

## Firebase et suivi des crashs

Crashlytics est activé automatiquement lorsque
`android/app/google-services.json` est présent. Ajouter l'application Android
`com.motman.game` au projet Firebase MotMan, télécharger ce fichier puis lancer
une version candidate sur un appareil. Un premier crash de test contrôlé doit
être envoyé avant publication pour vérifier le tableau Crashlytics. Le fichier
`google-services.json` reste hors Git.

## Sécurité des données

Préparer les déclarations suivantes dans la Play Console, puis les comparer une
dernière fois au comportement de la version candidate :

- informations de compte : adresse e-mail, identifiant utilisateur et pseudo ;
- activité dans l'application : progression, scores, parties et interactions ;
- relations sociales : amis, invitations, blocages et signalements ;
- identifiant d'appareil : jeton de notification FCM lorsque l'autorisation est
  accordée ;
- diagnostics : crashs, ANR et informations techniques via Crashlytics une fois
  celui-ci activé ;
- finalités : fonctionnement du jeu, synchronisation, sécurité, modération,
  notifications et amélioration des grilles ;
- chiffrement en transit : oui ;
- suppression des données : oui, dans l'application et via la page publique.

Supabase, Cloudflare Turnstile et Firebase agissent comme prestataires
techniques. Vérifier dans le formulaire si Google les considère comme
« prestataires de service » plutôt que comme partage à des tiers selon la
configuration finale.

## Contenu, âge et monétisation

- Public annoncé : à partir de 7 ans, avec accord parental applicable aux
  comptes et achats des mineurs.
- Questionnaire IARC : jeu de mots, multijoueur en ligne, pseudos modérés, pas
  de violence, sexe, drogue, langage grossier ni chat libre.
- Achats intégrés : les plumes seront payantes et le panier contient des objets
  aléatoires. Déclarer explicitement **Achats intégrés avec objets aléatoires**
  et afficher les probabilités avant chaque ouverture.
- Activer l'authentification Google Play pour les achats et prévoir un contrôle
  parental. Ne pas présenter la monnaie virtuelle comme de l'argent réel.

La classification finale est attribuée par l'IARC après le questionnaire ; ne
pas écrire manuellement un classement PEGI dans la fiche avant ce résultat.

## Fiche de boutique

À produire sur la version candidate stable :

- icône 512 × 512 sans masque ajouté ;
- bannière 1 024 × 500 ;
- au moins deux captures de téléphone ;
- captures tablette 7 et 10 pouces si ces appareils restent pris en charge ;
- description courte, description complète et e-mail de support ;
- lien confidentialité et lien suppression du compte ;
- accès de test pour l'équipe de validation si une connexion bloque une partie
  du contenu.

## Contrôles avant envoi

1. `npm run test:ci`
2. `npm run mobile:aab`
3. Installer le bundle depuis une piste de test interne.
4. Tester compte invité, Google, suppression, achat de test, notifications,
   mode hors-ligne/reconnexion et deux téléphones en multijoueur.
5. Vérifier Crashlytics et les ANR dans la Play Console après le test fermé.
