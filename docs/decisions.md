# Journal des décisions d'architecte — CrediScore (solution IA)

Chaque décision est notée au moment où elle est prise : contexte, options, choix, raison.
C'est la matière première des questions/réponses du jury.

---

## D-001 — 27/07/2026 — Deux dépôts GitHub publics distincts

- **Contexte :** le Bloc 4 exige deux dépôts distincts (développement IA / CI-CD).
- **Options :** monorepo avec dossiers ; deux dépôts privés ; deux dépôts publics.
- **Choix :** deux dépôts publics — `crediscore-ml` et `crediscore-mlops`.
- **Raison :** exigence explicite du référentiel ; publics pour que le jury accède
  sans friction ; aucune donnée personnelle réelle n'y sera versionnée (jeu public
  anonymisé, non commité).

## D-002 — 27/07/2026 — Les données ne sont jamais versionnées dans git

- **Contexte :** 8 CSV, ~2,7 Go décompressés, ~58 M de lignes.
- **Options :** commit direct ; Git LFS ; exclusion + zones de stockage.
- **Choix :** exclusion (`.gitignore`), données servies par le data lake (S3
  zones raw/clean/curated — dépôt mlops) ; le versionnage des données passe par
  le hachage des snapshots référencé dans MLflow.
- **Raison :** bonnes pratiques (git ≠ stockage de données), coût LFS injustifié,
  et cohérence avec l'architecture cible où la donnée vit dans le data lake.

## D-003 — 27/07/2026 — Variables sensibles contractualisées dès le jour 1

- **Contexte :** AI Act (système à haut risque) + art. 22 RGPD : non-discrimination
  à démontrer, pas à déclarer.
- **Choix :** liste des variables interdites versionnée (`configs/sensitive_features.yaml`)
  et testée automatiquement en CI (`tests/test_no_sensitive_features.py`) — le build
  échoue si une variable sensible entre dans les features du modèle.
- **Raison :** transforme une exigence réglementaire en garde-fou technique
  vérifiable et démontrable au jury.

## D-004 — 28/07/2026 — Environnement Python : un venv dédié par dépôt, jamais le Python global

- **Contexte :** poste Windows avec plusieurs Python (Anaconda, système) ; risque
  d'installer ou d'exécuter silencieusement au mauvais endroit.
- **Options :** environnement Anaconda partagé ; conda env dédié ; venv par dépôt.
- **Choix :** un environnement virtuel `.venv` à la racine de chaque dépôt
  (`python -m venv .venv`), alimenté exclusivement par le `requirements.txt` du
  dépôt ; toute commande (`python`, `pip`, `pytest`, `jupyter`) passe par
  `.venv\Scripts\python.exe`. Les images Docker (entraînement, API) réinstallent
  les mêmes `requirements.txt`, garantissant l'identité poste/production.
- **Raison :** isolation stricte des dépendances, reproductibilité vérifiable par
  le jury (`requirements.txt` = source de vérité unique), et cohérence avec les
  conteneurs déployés. Remplace la décision initiale « Anaconda pour l'exploration ».
