# Veille Tie Break

Veille géopolitique automatisée pour **Tie Break**, revendeur officiel Nike Tennis à Nice (dossier M2 AMOS ACE, module Sport et géopolitique).

**Question de veille :** dans quelle mesure l'exposition géopolitique et médiatique de Nike et de ses athlètes crée-t-elle des risques et des opportunités pour les ventes de Tie Break d'ici 2028 ?

## Fonctionnement

- `scripts/fetch.py` interroge **Google Actualités** (flux RSS, français et anglais) et l'API **GDELT** pour 5 axes :
  - E1 : Nike et la puissance américaine (guerre commerciale, boycotts)
  - E2 : Production et routes d'approvisionnement (Asie, droits de douane, mer Rouge)
  - E3 : Athlètes Nike et nouvelle géographie du tennis (Arabie saoudite, sportswashing)
  - T4 : Performances et polémiques des joueurs
  - T5 : Distribution Nike et marché du tennis
- Chaque article reçoit une **fiabilité** (A à D, selon la source) et un **score de signal** (mots comme boycott, droits de douane, retard, blessure…).
- `.github/workflows/veille.yml` lance la collecte **toutes les 2 heures** et enregistre le résultat dans `data/veille.json`.
- Le site (`index.html`) affiche le tableau des axes, le fil filtrable, les articles retenus (avec note et export CSV), les 20 sources de référence et la méthode.

## Modifier les mots-clés

Les requêtes sont en haut de `scripts/fetch.py` (dictionnaires `AXES` et `GDELT_QUERIES`). Après modification, la collecte se relance automatiquement.

## Lancer la collecte à la main

Onglet **Actions** → **Collecte de la veille** → **Run workflow**.
