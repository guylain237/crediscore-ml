# CrediScore — Développement de la solution IA

**Projet de certification — Architecte en IA (Mastère 2)**
**Auteur :** Tagne Guylain Florian

Scoring prédictif de risque de défaut à l'octroi de crédit à la consommation.
Ce dépôt est le **dépôt n°1** exigé par le Bloc 4 : développement de la solution IA
(préparation des données, entraînement, explicabilité, tests d'équité, évaluation).

> Le dépôt n°2 — infrastructure, pipelines de données et CI/CD — est ici :
> [crediscore-mlops](https://github.com/guylain237/crediscore-mlops)

## Problème métier

Prédire, à partir des seules informations connues au moment de la demande, la
probabilité qu'un client fasse défaut sur son crédit, afin de **maximiser le taux
d'acceptation sous contrainte d'un taux de défaut plafonné** fixé par la direction
des risques.

- **Entrée :** 122 variables de la demande + variables agrégées des historiques
  (bureau de crédit, crédits et paiements antérieurs) — 8 sources, ~58 M de lignes.
- **Sortie :** probabilité de défaut ∈ [0, 1], convertie en décision par un seuil
  piloté par une fonction de **coût métier** (un défaut coûte le capital prêté,
  un bon client refusé ne coûte qu'un manque à gagner).
- **Nature :** classification binaire supervisée, classes déséquilibrées (~8 % de défauts).

## Contraintes structurantes

| Contrainte | Conséquence technique |
|---|---|
| Décision en quelques secondes au point de vente | Variables lourdes précalculées (feature store, dépôt n°2) |
| Tout refus doit être motivé (art. 22 RGPD) | Modèle explicable : LightGBM + SHAP, pas de deep learning opaque |
| Non-discrimination (AI Act — système à haut risque) | Variables sensibles exclues du modèle et réservées à l'audit d'équité |

## Structure du dépôt

```
├── notebooks/          # EDA et analyses exploratoires
├── src/
│   ├── data/           # Chargement et validation des 8 sources
│   ├── features/       # Agrégations des tables filles (bureau, previous, installments…)
│   ├── models/         # Entraînement LightGBM, calibration, seuil coût métier
│   ├── explain/        # Explicabilité SHAP (globale + locale par dossier)
│   └── fairness/       # Tests d'équité : parité démographique, égalité des chances
├── tests/              # Tests unitaires + garde-fou "variables sensibles exclues"
├── configs/            # Hyperparamètres, seuils, listes de variables
└── docs/               # Profil des données, journal des décisions
```

## Données

Jeu de données public **Home Credit Default Risk** (Kaggle), traité comme l'export
des trois systèmes sources de l'établissement fictif CrediScore (souscription,
cœur de gestion crédit, bureau de crédit externe).

Les données ne sont **pas versionnées** dans ce dépôt (volumétrie et bonnes
pratiques). Placer les 8 CSV dans `input/` à la racine (voir `docs/data_profile.md`).

## Installation

Le projet s'exécute **exclusivement dans un environnement virtuel dédié** — jamais
sur le Python global ni sur une distribution Anaconda (voir décision D-004 dans
[`docs/decisions.md`](docs/decisions.md)).

```powershell
python -m venv .venv
.venv\Scripts\activate                  # le prompt doit afficher (.venv)
python -m pip install -r requirements.txt
```

Vérification (le test échoue si Anaconda ou le Python global est actif) :

```powershell
pytest tests\test_environment.py -q
```

Deux fichiers de dépendances, aux rôles distincts :

| Fichier | Rôle |
|---|---|
| `requirements.txt` | Contraintes minimales lisibles (`pandas>=2.2`) — ce qu'on installe |
| `requirements.lock.txt` | Versions exactes constatées (`pip freeze`) — ce qui rend un résultat reproductible et ce que reprennent les images Docker |

Si `activate` est bloqué par Windows (fichiers marqués « provenant d'Internet »
sous OneDrive) :

```powershell
Get-ChildItem .venv -Recurse -File | Unblock-File
```

## Utilisation

```powershell
python src\data\profile_raw.py      # profilage des 8 sources   -> docs/data_profile.md
python src\data\profile_joins.py    # jointures et intégrité    -> docs/schema_jointures.md
pytest                              # tests unitaires + garde-fou variables sensibles
```

## Documentation

Tout chiffre cité dans ces documents est **mesuré par script sur l'intégralité
des données**, jamais estimé.

| Document | Contenu | Produit par |
|---|---|---|
| [`docs/data_profile.md`](docs/data_profile.md) | volumétrie, clés, cible, valeurs manquantes | `src/data/profile_raw.py` |
| [`docs/schema_jointures.md`](docs/schema_jointures.md) | modèle relationnel, intégrité référentielle, couverture au grain dossier, colonnes temporelles | `src/data/profile_joins.py` |
| [`docs/strategie_decoupage.md`](docs/strategie_decoupage.md) | protocole train / validation / test, métriques, règles anti-fuite | rédigé |
| [`docs/plan_features.md`](docs/plan_features.md) | variables à construire par source, traitements, conventions | rédigé |
| [`docs/decisions.md`](docs/decisions.md) | journal des décisions d'architecte | rédigé |
