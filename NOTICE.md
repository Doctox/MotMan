# Corpus de mots fléchés

Le générateur ne consomme plus de définitions de dictionnaire, de relations
synonymiques automatiques ni de définitions reformulées. Le fichier
`src/data/crossword.corpus.json` contient uniquement des couples
définition-réponse provenant de grilles de mots fléchés.

- Architecture de référence (CWDB) : https://github.com/tommyiaqunisi/Webcrow
- Étude WebCrow française : https://arxiv.org/abs/2311.15626
- Première source française : https://github.com/ychalier-rlv/mots-croises/tree/main/data
- Publication d'origine indiquée par cette source : https://jeux.ouest-france.fr/jeux-de-lettres/mots-fleches/
- Deuxième source et parseur de recherche : https://github.com/AlexandreEDMOND/flechebench
- Grilles publiques Le Parisien/RCI : https://static.rcijeux.fr/drupal_game/leparisien/
- Fréquence servant uniquement à classer la difficulté : https://github.com/rspeer/wordfreq

Les définitions sont conservées mot pour mot. La ponctuation et la casse peuvent
être normalisées pour l'affichage, mais aucun terme n'est ajouté ou remplacé.
Le corpus français WebCrow décrit dans l'étude n'est pas présent dans son dépôt
public ; son intégration reste prévue si un accès est obtenu.

Sources complémentaires étudiées, mais non encore fusionnées au catalogue :

- Cruciverbe annonce plus de 529 000 définitions de mots croisés. Un export ou
  un accord d'accès en masse doit être obtenu avant intégration :
  https://cruciverbe.fr/definitions
- Le Dictionnaire des francophones publie une grande partie de ses données en
  open data via SPARQL et GraphQL. Il servira à valider le sens et le registre,
  jamais à transformer automatiquement une définition longue en indice :
  https://www.dictionnairedesfrancophones.org/sparql
- OpenLexicon/Lexique pourra enrichir le classement par fréquence, concrétude
  et âge d'acquisition, sans fournir de définition de jeu :
  https://www.lexique.org/

Les marques et interfaces d’autres jeux éventuellement étudiées comme références ne sont pas incluses dans le projet.

Les indices-images placés dans `public/assets/clues/twemoji` proviennent de
Twemoji et sont distribués sous licence CC BY 4.0.

- Twemoji : https://github.com/jdecked/twemoji
- Licence graphique : https://creativecommons.org/licenses/by/4.0/
