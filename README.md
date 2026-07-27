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

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```
