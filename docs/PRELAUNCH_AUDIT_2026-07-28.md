# Audit avant publication Google Play — 28 juillet 2026

## Verdict

MotMan est techniquement assez stable pour préparer un **test fermé Android**.
Il n'est pas encore prêt pour une publication publique payante.

## Contrôles validés

- `npm run test:ci` :
  - 104 tests unitaires réussis ;
  - catalogue v20 en 7×8 validé ;
  - build TypeScript/Vite réussi ;
  - budgets de performance respectés ;
  - quatre pages légales présentes ;
  - 23 scénarios E2E réussis sur Chromium et WebKit, 5 ignorés.
- `npm audit --omit=dev` : aucune vulnérabilité connue.
- Android :
  - `compileSdk` et `targetSdk` 36 ;
  - tests unitaires release réussis ;
  - lint release réussi ;
  - bundle release généré et signé manuellement avec la clé d'envoi MotMan ;
  - sauvegarde Android et trafic HTTP non chiffré désactivés.
- Supabase :
  - Edge Functions actives et protégées par JWT ;
  - secret serveur Firebase `FIREBASE_SERVICE_ACCOUNT_JSON` configuré ;
  - Realtime limité aux participants des matchs ;
  - tâches de nettoyage des invités et matchs actifs ;
  - catalogues serveur exclusivement en 7×8.
- La version GitHub Pages et les pages légales publiques répondent correctement.

## Actions restantes avant un test fermé

1. Importer le bundle signé `android/app/release/app-release.aab` dans une piste
   de test interne Google Play et activer Play App Signing.
2. Installer cette version depuis Google Play sur deux téléphones.
3. Tester Google, suppression de compte, notifications push, reconnexion et
   parties illimitées avant d'ouvrir le test fermé.

La signature automatique par les variables `MOTMAN_*` reste facultative pour
les prochaines compilations : Android Studio produit déjà un bundle signé
valide.
Les exceptions propriétaire `ESSUIE`, `SEDUIT` et `EPOUSA` ont été confirmées
le 28 juillet 2026. Les 29 grilles locales sont désormais jouables et alignées
avec les 29 grilles actives du serveur.

## Bloqueurs avant une publication publique payante

1. Implémenter Google Play Billing et valider les achats côté serveur avant de
   vendre des plumes.
2. Afficher les probabilités des paniers aléatoires à proximité immédiate de
   l'achat et de l'ouverture.
3. Choisir définitivement l'audience :
   - 16 ans et plus, cohérent avec la cible annoncée 16–45 ans ; ou
   - 7 ans et plus, avec toutes les obligations Google Play Families.
4. Finaliser Data Safety, IARC, la politique d'âge et les accès de validation.
5. Préparer la bannière 1 024×500, les captures téléphone/tablette et les textes
   de la fiche Play Store.
6. Faire relire les documents légaux, qui sont encore présentés comme des
   documents bêta/prépublication.
7. Si le compte Play est un compte personnel récent, terminer le test fermé
   requis avec 12 testeurs inscrits pendant 14 jours consécutifs.

## Points non bloquants à traiter

- La suite Python historique du générateur contient encore des tests obsolètes
  liés aux anciens formats et contrats éditoriaux. Le runtime et la chaîne de
  publication actuelle passent leurs tests, mais cette dette doit être archivée
  ou remise à niveau.
- 26 grilles jouables suffisent pour un test fermé, mais restent légères pour
  une sortie publique. Continuer à enrichir le catalogue avant la production.
- Les notifications sont codées et Firebase est configuré côté Android et
  serveur. Leur validation réelle sur deux appareils reste à effectuer.

## Garde-fous ajoutés pendant l'audit

- `npm run audit:play` contrôle la configuration Android, les pages légales,
  Firebase, la signature et le bundle candidat.
- `npm run mobile:aab` refuse désormais un candidat Play sans Firebase ou
  signature, sauf options de diagnostic explicites.
- GitHub Actions exécute l'audit des dépendances, l'audit Play statique et une
  vérification Android séparée.

## Ordre recommandé

1. Importer puis installer le `.aab` signé sur une piste interne.
2. Tester deux téléphones, Google, suppression de compte, push, reconnexion et
   parties illimitées.
3. Ouvrir le test fermé.
4. Pendant ce test, finaliser l'audience, la monétisation, les formulaires et les
   visuels de la fiche.
