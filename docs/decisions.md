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

> **Correctif du 16/08/2026 — à lire avec la décision.** Cette décision décrivait
> un contrôle qui **n'existait pas** : `tests/test_no_sensitive_features.py` était
> absent du dépôt et aucune CI ne tournait. L'écart a été constaté lors de la
> rédaction du plan de gouvernance, et corrigé le jour même : module
> `src/fairness/contract.py` (avec `exiger_conformite()` qui **interrompt**
> l'entraînement) et 14 assertions de test. La décision décrivait une intention ;
> elle décrit désormais un état. Cet écart est conservé au journal plutôt
> qu'effacé : un journal de décisions qu'on réécrit ne vaut rien.

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

## D-005 — 05/08/2026 — Découpage stratifié aléatoire, et non temporel

- **Contexte :** le plan de projet prévoyait un découpage temporel « si
  possible ». Le profilage des jointures a mesuré les 14 colonnes temporelles des
  8 sources : toutes sont des décalages **relatifs** à la date de la demande
  courante, laquelle n'est jamais fournie. Aucune colonne texte n'est convertible
  en date absolue.
- **Options :** simuler une temporalité en ordonnant sur `DAYS_DECISION` ou
  `MONTHS_BALANCE` ; renoncer au découpage temporel et le documenter ; changer de
  jeu de données.
- **Choix :** découpage **aléatoire stratifié sur `TARGET`** en 60/20/20
  (184 507 / 61 502 / 61 502 dossiers), au grain `SK_ID_CURR`, jeu de test scellé
  et ouvert une seule fois. Validation croisée stratifiée à 5 plis sur le seul
  jeu d'entraînement.
- **Raison :** ordonner sur un décalage relatif produirait un faux *out-of-time* —
  deux dossiers avec le même `DAYS_DECISION` peuvent être séparés de plusieurs
  années. Mieux vaut une limite assumée qu'une rigueur simulée. La stratification
  est imposée par le déséquilibre (8,07 % de défauts).
- **Contrôle compensatoire :** la résistance à la dérive, non mesurable hors
  ligne, est reportée en production — détection de dérive (PSI/KS) sur les
  entrées et les scores, réentraînement **déclenché par la dérive** et non par le
  calendrier. Détail dans `docs/strategie_decoupage.md`.

## D-006 — 05/08/2026 — Réduction du socle applicatif sur preuve de redondance

- **Contexte :** `application_train` compte 122 colonnes, dont 14 indicateurs de
  logement déclinés en trois versions (`_AVG`, `_MODE`, `_MEDI`).
- **Choix :** retrait des versions `_MODE` et `_MEDI` numériques — **28 colonnes**
  — après mesure de leurs corrélations internes, comprises entre **0,973 et
  0,997**. Et traitement de la sentinelle `DAYS_EMPLOYED = 365243` (18,0 % des
  dossiers) : remplacement par `NaN` **assorti** d'un indicateur binaire
  `DAYS_EMPLOYED_ANORMAL`.
- **Raison :** trois mesures du même objet répartissent l'importance SHAP entre
  trois jumelles et rendent l'explication illisible, sans apporter de signal. La
  sentinelle, elle, n'est pas une mesure mais un code : laissée telle quelle, elle
  déplace tous les seuils de coupure des arbres ; simplement effacée, elle
  détruirait un signal concernant un dossier sur cinq.
- **Note :** le taux de nuls n'a **pas** servi de critère d'élimination —
  `EXT_SOURCE_1` manque dans 56,4 % des dossiers et reste le troisième prédicteur
  du jeu.

## D-007 — 05/08/2026 — Aucune imputation, encodage catégoriel natif

- **Contexte :** couverture mesurée au grain dossier très inégale selon les
  sources : 94,6 % pour `PREV_*`, mais 30,0 % pour `BB_*` et 25,3 % pour `CC_*`.
- **Options :** imputation par la médiane ; imputation par modèle ; aucune
  imputation, en s'appuyant sur le traitement natif des `NaN` par LightGBM.
- **Choix :** **aucune imputation**, complétée par des indicateurs binaires de
  présence par famille (`A_HISTORIQUE_BUREAU`, `A_CARTE_CREDIT`…). Variables
  catégorielles traitées nativement par LightGBM ; encodage par la cible
  **écarté**, y compris pour `ORGANIZATION_TYPE` et ses 58 modalités.
- **Raison :** une absence d'historique n'est pas une valeur nulle — c'est le
  profil du primo-emprunteur, une information de risque à part entière. Imputer
  reviendrait à affirmer une valeur inconnue. Quant au *target encoding*, il fait
  fuiter la cible dans les variables et exige un dispositif hors-pli rigoureux
  pour un gain non démontré face au traitement natif : un risque de fuite pour un
  gain incertain est un mauvais échange.

## D-008 — 05/08/2026 — Chiffrer le prix de la conformité par un modèle témoin

- **Contexte :** `DAYS_BIRTH` est la **quatrième variable la plus corrélée** à la
  cible (|r| = 0,078) et se trouve exclue au titre de D-003, comme `CODE_GENDER`,
  `NAME_FAMILY_STATUS` et toute variable qui en dérive.
- **Choix :** entraîner un **modèle témoin** incluant les variables sensibles,
  comparer son AUC à celui du modèle conforme, et consigner l'écart dans MLflow.
  Ce modèle témoin n'est **jamais déployé** ni exposé.
- **Raison :** la conformité a un coût de performance ; le mesurer permet de le
  défendre plutôt que de le subir. Un jury attend d'un architecte qu'il connaisse
  le prix de ses contraintes, pas qu'il prétende qu'elles sont gratuites. Le
  chiffre alimentera directement la note d'équité du Bloc 1.

## D-009 — 16/08/2026 — Un plan de gouvernance opposable, pas déclaratif

- **Contexte :** le Bloc 1 est intégralement documentaire. Le risque n'est pas de
  produire trop peu de texte, mais d'en produire un que le projet ne suit pas —
  un jury vérifie la cohérence entre ce qui est écrit et ce que contient le dépôt.
  Le cas D-003 l'a démontré : un contrôle annoncé mais absent.
- **Options :** un document de gouvernance descriptif et générique ; un document
  adossé au code ; deux documents séparés sans lien.
- **Choix :** un plan de gouvernance dont chaque engagement porte un **identifiant
  citable** — politiques `P-1` à `P-9`, contrôles techniques `C-1` à `C-12` — avec
  pour chaque contrôle un **artefact et une date**. Une **matrice de traçabilité**
  relie exigence réglementaire → politique → contrôle → preuve vérifiable. Toute
  entrée future de ce journal doit citer la politique qu'elle applique.
- **Raison :** la gouvernance n'a de valeur que si elle contraint. Des identifiants
  stables permettent au code, aux pipelines et aux décisions de s'y référer ; des
  dates transforment une intention en engagement dont le non-respect se voit. Un
  contrôle en retard devient une non-conformité **déclarée**, ce qui est
  défendable — au contraire d'un contrôle inventé.

## D-010 — 16/08/2026 — L'égalité des chances comme critère principal d'équité

- **Contexte :** les taux de défaut mesurés diffèrent réellement selon les groupes :
  **7,00 % chez les femmes contre 10,14 % chez les hommes**, et de **12,29 % (18-25 ans)
  à 3,66 % (65 ans et plus)** — un rapport de 1 à 3,4.
- **Options :** parité démographique comme critère bloquant ; égalité des chances
  comme critère bloquant ; seuils de décision différenciés par groupe.
- **Choix :** **égalité des chances** (et odds égalisées, et calibration par
  groupe) comme critères d'arrêt ; **parité démographique publiée mais non
  bloquante** ; **seuils par groupe formellement exclus**. Les seuils numériques
  sont **figés avant toute mesure** et ne peuvent évoluer que par décision unanime
  du comité d'équité.
- **Raison :** imposer des taux d'acceptation identiques quand les risques
  diffèrent réellement conduirait soit à accepter des dossiers plus risqués, soit
  à refuser des demandeurs solvables — une discrimination en sens inverse.
  L'égalité des chances mesure le tort concret : une personne solvable injustement
  refusée. Surtout, **appliquer un seuil différent selon le genre serait une
  discrimination directe**, prohibée, là où une discrimination indirecte peut être
  justifiée par un objectif légitime : corriger l'une par l'autre est
  juridiquement régressif, quel que soit le gain sur les métriques.
- **Garde-fou méthodologique :** figer les seuils avant la mesure interdit
  l'ajustement rétrospectif, qui consiste à décréter acceptable ce que l'on a
  obtenu.
